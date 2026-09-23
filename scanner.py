import os
import sys
import re
import html
import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from openai import OpenAI
from supabase import create_client

TARGET_HOURLY_RATE = 35
SMART_SEARCH_QUERIES = [
    "amazon product images",
    "ecommerce product retouching",
    "product photo retouching photoshop",
    "product image compositing",
    "AI image photoshop",
    "AI product photography",
    "interior photo editing photoshop",
    "architectural photo retouching",
    "real estate photo editing",
    "high end photo retouching"
]
SMART_SEARCH_PER_QUERY = int(os.getenv("SMART_SEARCH_PER_QUERY", "20"))
AI_ANALYZE_TOP = int(os.getenv("AI_ANALYZE_TOP", "25"))
OPPORTUNITY_THRESHOLD = int(os.getenv("OPPORTUNITY_THRESHOLD", "80"))
KYIV_TZ = ZoneInfo("Europe/Kyiv")
SCAN_HOURS = {8, 11, 14, 17, 20}

# Incremental scanner settings.
# Normal scans prioritize jobs we have never seen before.
# The 20:00 Kyiv run also performs a recovery pass over older jobs.
RECOVERY_SCAN_HOUR = 20
RECOVERY_CANDIDATES = int(os.getenv("RECOVERY_CANDIDATES", "8"))
NEW_JOB_ANALYZE_LIMIT = int(os.getenv("NEW_JOB_ANALYZE_LIMIT", str(AI_ANALYZE_TOP)))

STRONG_KEYWORDS = [
    "photoshop",
    "retouch",
    "retouching",
    "photo editing",
    "image editing",
    "product image",
    "product images",
    "product photo",
    "product photography",
    "e-commerce",
    "ecommerce",
    "amazon",
    "listing image",
    "listing images",
    "lifestyle image",
    "lifestyle images",
    "compositing",
    "composite",
    "background replacement",
    "background removal",
    "ai image",
    "ai images",
    "generative ai",
    "ai photography",
    "interior",
    "architectural",
    "architecture",
    "real estate",
    "lightroom",
]


# =====================================================
# RELEVANCE FILTER v4
# =====================================================
# Goal: keep image-editing / retouching opportunities and reject adjacent
# disciplines that only happen to mention Photoshop, AI, ecommerce, etc.

RELEVANCE_KEYWORDS = [
    "amazon listing", "amazon product", "amazon images", "amazon image",
    "a+ content", "e-commerce", "ecommerce", "product image", "product images",
    "product photo", "product photos", "product retouch", "product retouching",
    "product editing", "listing image", "listing images", "lifestyle image",
    "lifestyle images", "packshot", "pack shot", "photo retouch", "photo retouching",
    "high-end retouch", "high end retouch", "photo editing", "image editing",
    "photoshop", "compositing", "composite", "background replacement",
    "background removal", "image manipulation", "photo manipulation", "lightroom",
    "ai image", "ai images", "ai photography", "ai product photography",
    "generative ai", "ai + photoshop", "ai photoshop", "photorealistic ai",
    "architectural photo", "architectural retouch", "architecture retouch",
    "interior photo", "interior retouch", "real estate photo", "real estate editing",
    "virtual staging", "portrait retouch", "portrait retouching", "beauty retouch",
    "beauty retouching", "skin retouch",
]

GENERIC_VISUAL_KEYWORDS = [
    "retouch", "retouching", "photoshop", "photo editor", "photo editing",
    "image editor", "image editing", "compositing", "lightroom",
]

# These roles are outside this scanner's photo/image-editing lane.  A job can
# survive only when its TITLE also contains an explicit editing/retouching signal.
OFF_TARGET_TITLE_KEYWORDS = [
    "web designer", "web developer", "website designer", "website developer",
    "shopify designer", "shopify developer", "wordpress", "frontend", "front-end",
    "backend", "back-end", "full stack", "full-stack", "ui/ux", "ux/ui",
    "ui designer", "ux designer", "graphic designer", "graphic design",
    "visual content creator", "creative designer", "brand designer", "branding designer",
    "logo designer", "logo design", "illustrator", "illustration",
    "social media", "social media manager", "social media marketing", "meta ads",
    "facebook ads", "google ads", "digital marketing", "marketing manager", "seo",
    "email marketing", "copywriter", "copywriting", "content writer",
    "video editor", "video editing", "video creator", "video producer",
    "motion designer", "motion graphics", "animation", "animator", "youtube editor",
    "thumbnail designer", "thumbnail design", "3d artist", "3d designer",
    "3d developer", "software developer", "mobile app developer",
]

# Explicit TITLE signals showing that the actual deliverable is image editing.
TITLE_EDITING_SIGNALS = [
    "retouch", "retouching", "photo edit", "photo editor", "image edit", "image editor",
    "product image", "product photo retouch", "product retouch", "photoshop retouch",
    "photoshop editing", "photoshop compositing", "photo compositing", "image compositing",
    "background replacement", "background removal", "color correction", "colour correction",
    "lightroom edit", "architectural retouch", "interior retouch", "real estate photo edit",
    "portrait retouch", "beauty retouch", "skin retouch", "ai image", "ai product image",
]

CORE_PHOTO_SIGNALS = [
    "retouch", "retouching", "photo retouch", "photo editing", "photo editor",
    "image editing", "image editor", "product image", "product retouch", "amazon listing",
    "amazon product", "listing image", "lifestyle image", "photoshop compositing",
    "photo compositing", "image compositing", "background replacement", "background removal",
    "ai image", "ai product", "architectural retouch", "interior retouch",
    "real estate editing", "portrait retouch", "beauty retouch", "skin retouch",
]

# Photography-only jobs are intentionally excluded from this scanner unless the
# title clearly asks for editing/retouching/compositing as well.
PHOTOGRAPHY_ONLY_TITLE_KEYWORDS = [
    "photographer", "photography", "photo shoot", "photoshoot", "studio shoot",
    "event photographer", "wedding photographer", "product photographer",
]

RELEVANCE_MIN_SCORE = int(os.getenv("RELEVANCE_MIN_SCORE", "6"))


def job_search_text(job):
    return (
        str(job.get("title") or "")
        + " "
        + str(job.get("description") or "")
        + " "
        + " ".join(job.get("skills") or [])
    ).lower()


def relevance_score(job):
    text = job_search_text(job)
    title = str(job.get("title") or "").lower()

    strong_matches = [k for k in RELEVANCE_KEYWORDS if k in text]
    generic_matches = [k for k in GENERIC_VISUAL_KEYWORDS if k in text]
    core_matches = [k for k in CORE_PHOTO_SIGNALS if k in text]
    title_edit_matches = [k for k in TITLE_EDITING_SIGNALS if k in title]
    off_target_matches = [k for k in OFF_TARGET_TITLE_KEYWORDS if k in title]
    photography_only = [k for k in PHOTOGRAPHY_ONLY_TITLE_KEYWORDS if k in title]

    score = min(len(strong_matches) * 3, 18) + min(len(generic_matches), 3)

    if core_matches:
        score += 5
    if title_edit_matches:
        score += 6
    if off_target_matches:
        score -= 18
    if photography_only and not title_edit_matches:
        score -= 15

    # Broad ecommerce/AI mentions are not enough by themselves.
    if not core_matches and not title_edit_matches:
        score -= 6

    return score


def is_relevant_job(job):
    title = str(job.get("title") or "").lower()
    text = job_search_text(job)

    title_edit_matches = [k for k in TITLE_EDITING_SIGNALS if k in title]
    off_target_matches = [k for k in OFF_TARGET_TITLE_KEYWORDS if k in title]
    photography_only = [k for k in PHOTOGRAPHY_ONLY_TITLE_KEYWORDS if k in title]
    core_matches = [k for k in CORE_PHOTO_SIGNALS if k in text]

    # v4 hard gate: adjacent professions do not pass just because their
    # descriptions mention Photoshop, AI, Amazon or ecommerce.
    if off_target_matches and not title_edit_matches:
        return False

    # Exclude jobs whose primary deliverable is taking photographs rather than editing them.
    if photography_only and not title_edit_matches:
        return False

    # Require at least one real image-editing/retouching signal somewhere in the job.
    if not core_matches and not title_edit_matches:
        return False

    return relevance_score(job) >= RELEVANCE_MIN_SCORE


# =====================================================
# TARGET FIT FILTER v5.1
# =====================================================
# Stage 2 after broad relevance: only spend full AI analysis on jobs that
# clearly fit one of the freelancer's commercial image-editing lanes.
TARGET_LANES = {
    "amazon_ecommerce": [
        "amazon listing", "amazon product", "amazon image", "amazon images",
        "a+ content", "listing image", "listing images", "ecommerce product image",
        "e-commerce product image", "product listing image", "lifestyle image",
        "lifestyle images", "packshot", "pack shot",
    ],
    "product_retouching": [
        "product retouch", "product retouching", "product photo retouch",
        "product image editing", "product photo editing", "photo retouch",
        "high-end retouch", "high end retouch", "background replacement",
        "background removal", "color correction", "colour correction",
    ],
    "product_compositing_ai": [
        "product compositing", "product composite", "photoshop compositing",
        "photo compositing", "image compositing", "ai product image",
        "ai product photography", "ai + photoshop", "ai photoshop",
        "product image manipulation",
    ],
    "architecture_interior": [
        "architectural photo", "architectural retouch", "architecture retouch",
        "interior photo editing", "interior retouch", "real estate photo",
        "real estate editing", "virtual staging",
    ],
    "portrait_beauty": [
        "portrait retouch", "portrait retouching", "beauty retouch",
        "beauty retouching", "skin retouch", "headshot retouch",
        "wedding retouch", "wedding photo retouch",
    ],
}

# These are strong indicators that the actual deliverable belongs to another
# discipline. They are rejected even if the description casually mentions
# Photoshop/AI, unless a target-lane phrase is explicit in the title.
TARGET_FIT_BLOCKERS = [
    "kdp", "book interior", "book cover", "paperback", "hardcover",
    "vector recreation", "vector illustration", "vector art",
    "photoshop tutor", "photoshop teacher", "photoshop instructor",
    "3d architect", "3d architecture", "3d modeling", "3d modelling",
    "ai character", "character creation", "character design",
    "video creation", "video creator", "video editor", "video editing",
    "short videos", "reels", "tiktok video", "youtube video",
    "fashion designer", "textile designer", "print designer",
]

TARGET_TITLE_SIGNALS = sorted({
    phrase
    for phrases in TARGET_LANES.values()
    for phrase in phrases
})

# v5.1: marketplace/platform words are context, not proof of image work.
# A generic Amazon/e-commerce/Shopify role must also contain an explicit
# image/retouching/compositing deliverable before it can reach AI analysis.
GENERIC_COMMERCE_ROLE_SIGNALS = [
    "virtual assistant", "ecommerce virtual assistant", "e-commerce virtual assistant",
    "amazon virtual assistant", "shopify virtual assistant", "store manager",
    "ecommerce manager", "e-commerce manager", "amazon manager", "shopify manager",
    "listing specialist", "product listing specialist", "marketplace specialist",
    "product uploader", "listing uploader", "catalog manager", "catalog specialist",
]

IMAGE_DELIVERABLE_SIGNALS = [
    "image", "images", "photo", "photos", "photography", "retouch", "retouching",
    "photoshop", "compositing", "composite", "background removal",
    "background replacement", "color correction", "colour correction",
    "packshot", "pack shot", "lifestyle image", "listing image", "a+ content",
]


def target_fit_details(job):
    title = str(job.get("title") or "").lower()
    text = job_search_text(job)

    lane_hits = {}
    for lane, phrases in TARGET_LANES.items():
        hits = [phrase for phrase in phrases if phrase in text]
        if hits:
            lane_hits[lane] = hits

    title_hits = [phrase for phrase in TARGET_TITLE_SIGNALS if phrase in title]
    blockers = [phrase for phrase in TARGET_FIT_BLOCKERS if phrase in title]
    generic_commerce_role = any(
        phrase in title for phrase in GENERIC_COMMERCE_ROLE_SIGNALS
    )
    title_has_image_deliverable = any(
        phrase in title for phrase in IMAGE_DELIVERABLE_SIGNALS
    )

    # Require a genuine target lane. Description/skills can establish fit, but
    # title evidence gets a substantial bonus because it reflects the primary deliverable.
    score = 0
    for hits in lane_hits.values():
        score += min(12, 4 * len(hits))
    score += min(18, 6 * len(title_hits))

    if blockers and not title_hits:
        score -= 30

    best_lane = None
    if lane_hits:
        best_lane = max(lane_hits, key=lambda lane: len(lane_hits[lane]))

    return {
        "score": score,
        "lane": best_lane,
        "lane_hits": lane_hits,
        "title_hits": title_hits,
        "blockers": blockers,
        "generic_commerce_role": generic_commerce_role,
        "title_has_image_deliverable": title_has_image_deliverable,
    }


def is_target_fit_job(job):
    details = target_fit_details(job)
    job["target_fit_score"] = details["score"]
    job["target_lane"] = details["lane"]

    if details["blockers"] and not details["title_hits"]:
        return False

    # v5.1: Amazon/e-commerce/Shopify operational roles are not image jobs just
    # because their descriptions mention listings, lifestyle images or A+ content.
    # The title itself must identify an image/photo/retouching deliverable.
    if (
        details["generic_commerce_role"]
        and not details["title_has_image_deliverable"]
    ):
        return False

    # At least one commercial target lane must be present.
    if not details["lane_hits"]:
        return False

    return details["score"] >= 4


UPWORK_TOKEN_URL = "https://www.upwork.com/api/v3/oauth2/token"
UPWORK_GRAPHQL_URL = "https://api.upwork.com/graphql"

def required_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

OPENAI_API_KEY = required_env("OPENAI_API_KEY")
SUPABASE_URL = required_env("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = required_env("SUPABASE_SERVICE_ROLE_KEY")
UPWORK_CLIENT_ID = required_env("UPWORK_CLIENT_ID")
UPWORK_CLIENT_SECRET = required_env("UPWORK_CLIENT_SECRET")
TELEGRAM_BOT_TOKEN = required_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = required_env("TELEGRAM_CHAT_ID")

openai_client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

_current_access_token = None

def get_saved_tokens():
    response = (
        supabase.table("app_tokens")
        .select("access_token,refresh_token")
        .eq("id", "upwork")
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        raise RuntimeError("No Upwork OAuth token found in Supabase. Connect Upwork once in the Streamlit app first.")
    return rows[0]

def save_tokens(access_token, refresh_token):
    supabase.table("app_tokens").upsert({
        "id": "upwork",
        "access_token": access_token,
        "refresh_token": refresh_token
    }).execute()

def refresh_upwork_access_token():
    global _current_access_token
    tokens = get_saved_tokens()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("Stored Upwork refresh token is empty.")
    response = requests.post(
        UPWORK_TOKEN_URL,
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "client_id": UPWORK_CLIENT_ID,
            "client_secret": UPWORK_CLIENT_SECRET,
            "refresh_token": refresh_token
        },
        timeout=30
    )
    response.raise_for_status()
    payload = response.json()
    access_token = payload.get("access_token")
    new_refresh = payload.get("refresh_token") or refresh_token
    if not access_token:
        raise RuntimeError("Upwork token refresh did not return access_token.")
    save_tokens(access_token, new_refresh)
    _current_access_token = access_token
    return access_token

def upwork_graphql(query, variables=None):
    global _current_access_token
    if not _current_access_token:
        _current_access_token = refresh_upwork_access_token()
    def _send(token):
        return requests.post(
            UPWORK_GRAPHQL_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": query, "variables": variables or {}},
            timeout=30
        )
    response = _send(_current_access_token)
    if response.status_code == 401:
        _current_access_token = refresh_upwork_access_token()
        response = _send(_current_access_token)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(str(payload["errors"]))
    return payload.get("data", {})

def clean_value(value):

    if value is None:
        return "Unknown"

    value = str(value).strip()

    if not value:
        return "Unknown"

    return value

def extract_number(
    text,
    label
):

    pattern = (
        rf"{re.escape(label)}:\s*(\d+)"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    value = int(
        match.group(1)
    )

    return max(
        0,
        min(100, value)
    )

def extract_text_value(
    text,
    label
):

    pattern = (
        rf"{re.escape(label)}:"
        rf"\s*(.+)"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if match:
        return match.group(1).strip()

    return ""

def extract_section(
    text,
    section_name,
    next_section=None
):

    if next_section:

        pattern = (
            rf"{re.escape(section_name)}:\s*(.*?)"
            rf"(?={re.escape(next_section)}:)"
        )

    else:

        pattern = (
            rf"{re.escape(section_name)}:\s*(.*)"
        )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE | re.DOTALL
    )

    if match:
        return match.group(1).strip()

    return ""

def safe_score(
    value,
    fallback=50
):

    if value is None:
        return fallback

    return max(
        0,
        min(100, value)
    )

def money_number(money):

    if not money:
        return None

    value = money.get(
        "displayValue"
    )

    if value is None:
        return None

    try:

        return float(
            str(value)
            .replace(",", "")
            .replace("$", "")
            .strip()
        )

    except Exception:

        return None

def money_display(money):

    if not money:
        return ""

    value = money.get(
        "displayValue"
    )

    currency = money.get(
        "currency"
    )

    if value in [
        None,
        ""
    ]:
        return ""

    try:

        number = float(
            str(value)
            .replace(",", "")
            .replace("$", "")
        )

        if number == 0:
            return ""

        formatted = (
            f"{number:,.2f}"
            .rstrip("0")
            .rstrip(".")
        )

    except Exception:

        formatted = str(
            value
        )

    if currency:

        return (
            f"${formatted} "
            f"{currency}"
        )

    return (
        f"${formatted}"
    )

def calculate_opportunity_score(
    skill_match,
    client_quality,
    budget_quality,
    competition_score,
    win_probability,
    deal_breaker=False
):

    skill_match = safe_score(
        skill_match,
        50
    )

    client_quality = safe_score(
        client_quality,
        50
    )

    budget_quality = safe_score(
        budget_quality,
        45
    )

    competition_score = safe_score(
        competition_score,
        50
    )

    win_probability = safe_score(
        win_probability,
        50
    )

    score = round(
        skill_match * 0.25
        + client_quality * 0.20
        + budget_quality * 0.20
        + competition_score * 0.15
        + win_probability * 0.20
    )


    # Terrible budget should never become APPLY

    if budget_quality <= 15:

        score = min(
            score,
            59
        )

    elif budget_quality <= 30:

        score = min(
            score,
            69
        )


    # Serious deal breaker

    if deal_breaker:

        score = min(
            score,
            59
        )


    # Very low win probability

    if win_probability < 35:

        score = min(
            score,
            64
        )


    return score

def decision_from_score(
    score
):

    if score >= 90:
        return "🔥 APPLY NOW"

    if score >= 80:
        return "🟢 APPLY"

    if score >= 65:
        return "🟡 MAYBE"

    return "🔴 SKIP"

def build_analysis_prompt(job):

    return f"""
You are a senior Upwork business opportunity analyst.

Your goal is NOT merely to decide whether the freelancer
can technically perform the job.

Your goal is to determine whether applying is a smart use
of this freelancer's time and Upwork Connects.

=====================================================
FREELANCER PROFILE
=====================================================

Positioning:

- Amazon Listing Images Expert
- High-End Photo Retoucher
- Photoshop Expert
- AI Image Specialist
- Product Image Specialist
- E-commerce Image Specialist

Profile strength:

- Top Rated
- 100% Job Success
- 5-star work history
- experienced freelancer
- strong completed-job history

Strongest skills:

- Amazon listing images
- e-commerce product imagery
- product retouching
- high-end Photoshop
- AI + Photoshop
- photorealistic AI compositing
- product replacement
- lifestyle product integration
- background replacement
- preserving exact product geometry
- texture and material preservation
- interior manipulation
- architectural photo editing
- portrait retouching
- AI artifact correction
- consistent image series

=====================================================
BUSINESS PRIORITIES
=====================================================

Strongly prioritize:

1. Amazon / e-commerce product imagery
2. AI + Photoshop projects
3. Product/lifestyle compositing
4. High-end photo retouching
5. Interior / architectural manipulation
6. Recurring image production
7. Agencies
8. Established companies
9. Long-term clients

Prefer:

- clients with proven Upwork spending
- repeat-work potential
- professional briefs
- quality-sensitive projects
- realistic budgets
- low/moderate competition
- jobs where photographic realism matters

Penalize:

- extremely low budgets
- unrealistic workload
- commodity Photoshop work
- excessive unpaid tests
- unclear scope
- impossible deadlines
- very high competition
- clients already interviewing many people
- price-driven jobs

=====================================================
PRICING
=====================================================

Freelancer pricing baseline:

${TARGET_HOURLY_RATE}/hour is the BASELINE MINIMUM sustainable rate,
NOT the default recommended rate for every job.

The recommended bid must reflect:
- specialization required
- project complexity
- commercial value
- degree of manual Photoshop work
- need for realism / product preservation
- client quality
- urgency
- likelihood of revisions
- whether the work is commodity editing or specialized high-end work

Use this practical pricing ladder as guidance:

Simple / routine retouching:
$35-$40/hr

Commercial or product retouching:
$40-$45/hr

AI + Photoshop compositing:
$40-$50/hr

High-end fashion / luxury product compositing:
$45-$55/hr

Very specialized, high-value or technically difficult work:
$50+/hr when justified.

IMPORTANT:
Do not recommend $35/hr automatically just because the client
did not specify a budget.

If the job says:
Hourly — budget not specified

then estimate a fair bid from the complexity and specialization.
For high-end compositing, handbag preservation, realistic hand/object
contact, shadows, reflections, product geometry, or luxury/fashion work,
a bid around $45-$55/hr may be appropriate.

If the client's stated hourly ceiling is below the freelancer's
appropriate rate:
- do NOT automatically lower the recommended bid to fit the client
- reduce BUDGET QUALITY
- reduce OPPORTUNITY SCORE if necessary
- explain that the client's range may not support the freelancer's level

Examples:

$15-$35/hr + simple retouching:
$35/hr can be reasonable.

$15-$35/hr + advanced high-end compositing:
the job may be underpriced; recommend a realistic rate and lower
Budget Quality if the client ceiling does not support it.

$25-$50/hr + complex AI/Photoshop compositing:
good budget; recommended bid may be $45-$50/hr.

For FIXED jobs:

Estimate realistic scope, likely hours, complexity, and revision risk,
then recommend a project price.

Do NOT mechanically calculate every fixed job as $35 × hours.

Example:

71 precision image edits for $100
should have Budget Quality approximately 0-10
and normally be a deal breaker.

=====================================================
SCORING
=====================================================

SKILL MATCH:
0-100

Judge only how closely the job matches
the freelancer's strongest skills.


CLIENT QUALITY:
0-100

Consider:

- lifetime spending
- hires
- Upwork history
- rating
- professionalism
- brief quality
- repeat-work potential


BUDGET QUALITY:
0-100

Consider:

- hourly range
- fixed budget
- workload
- complexity
- freelancer seniority


COMPETITION SCORE:
0-100

100 = very favorable.
0 = very unfavorable.

Consider applicants, interviews, invites
and job age when available.


WIN PROBABILITY:
0-100

Estimate how likely THIS freelancer
is to stand out and win.

Consider:

- specialization
- Top Rated
- 100% JSS
- portfolio relevance
- exact client problem
- AI + Photoshop advantage
- competition
- pricing compatibility


DEAL BREAKER:

YES only for a serious reason not to apply.

Examples:

- absurdly low fixed budget
- unrealistic workload/budget mismatch
- huge unpaid test
- impossible deadline
- obvious problematic scope

Do NOT mark YES merely because the job
is not perfect.

=====================================================
CATEGORY
=====================================================

Choose exactly ONE:

Amazon
Product Retouching
AI + Photoshop
Interior / Architecture
Portrait
Other

Use Portrait only when people/portrait/beauty work
is clearly the primary focus.

=====================================================
JOB
=====================================================

TITLE:
{clean_value(job.get("title"))}

DESCRIPTION:
{clean_value(job.get("description"))}

BUDGET:
{clean_value(job.get("budget"))}

APPLICANTS:
{clean_value(job.get("proposals"))}

INTERVIEWING:
{clean_value(job.get("interviewing"))}

INVITES:
{clean_value(job.get("invites"))}

POSTED:
{clean_value(job.get("posted"))}

PROJECT LENGTH:
{clean_value(job.get("project_length"))}

EXPERIENCE LEVEL:
{clean_value(job.get("experience_level"))}

SKILLS:
{clean_value(", ".join(job.get("skills", [])))}

=====================================================
CLIENT
=====================================================

SPENT:
{clean_value(job.get("client_spent"))}

HIRES:
{clean_value(job.get("client_hires"))}

RATING:
{clean_value(job.get("client_rating"))}

LOCATION:
{clean_value(job.get("client_location"))}

MEMBER SINCE:
{clean_value(job.get("member_since"))}

=====================================================
RETURN EXACTLY THIS FORMAT
=====================================================

CATEGORY: category

SKILL MATCH: X/100

CLIENT QUALITY: X/100

BUDGET QUALITY: X/100

COMPETITION SCORE: X/100

WIN PROBABILITY: X/100

DEAL BREAKER: YES or NO

WHY YOU CAN WIN:
- reason
- reason
- reason

WHY THIS JOB IS ATTRACTIVE:
- reason
- reason

RISKS:
- risk
- risk

RECOMMENDED BID:
One concise recommendation only.

The recommendation must be based on the project's actual complexity
and value, not simply the $35/hr baseline.

Examples:
Recommended: $38-$40/hr for routine retouching.

Recommended: $45-$50/hr for high-end AI + Photoshop compositing.

Recommended: $50-$55/hr for luxury/fashion product compositing when justified.

Recommended: $600-$800 fixed for a clearly scoped project.

PORTFOLIO TO SHOW:
1. example
2. example
3. example

APPLICATION STRATEGY:
- recommendation
- recommendation
- recommendation

PROPOSAL:
Write a personalized Upwork cover letter using this structure and tone:

Hi,

Your project caught my eye because [specific detail showing genuine interest].

I've done very similar work — here's [INSERT RELEVANT PORTFOLIO LINK].
The brief was [one concise sentence describing a comparable type of work],
and the result was [one concise sentence describing the outcome].

For your project, I'd approach it by [brief creative/technical direction tailored to this exact job].

PRICING SENTENCE:
- If the job is clearly fixed-price, include:
  "I've scoped this as fixed-price so there are no surprises."
- If the job is hourly, include one concise sentence that reflects the RECOMMENDED BID,
  for example:
  "Based on the scope, I'd suggest starting at $45/hr."
- Never claim fixed-price for an hourly job.
- Never invent a client name. If the client's name is unknown, use "Hi,".

Happy to share more examples. What's the best way to connect?

Andrew

IMPORTANT:
- Keep the proposal natural, concise and confident.
- Approximately 100-140 words.
- Do not begin with "I am excited to apply."
- Do not invent portfolio links.
- Keep the exact placeholder:
  [INSERT RELEVANT PORTFOLIO LINK]
- Tailor the specific-detail sentence, similar-work sentence and approach sentence
  to the actual job description.
"""

def analyze_job_with_ai(job):

    prompt = build_analysis_prompt(
        job
    )

    response = (
        openai_client
        .responses
        .create(
            model="gpt-5-mini",
            input=prompt
        )
    )

    analysis = response.output_text


    skill_match = extract_number(
        analysis,
        "SKILL MATCH"
    )

    client_quality = extract_number(
        analysis,
        "CLIENT QUALITY"
    )

    budget_quality = extract_number(
        analysis,
        "BUDGET QUALITY"
    )

    competition_score = extract_number(
        analysis,
        "COMPETITION SCORE"
    )

    win_probability = extract_number(
        analysis,
        "WIN PROBABILITY"
    )


    deal_breaker_text = (
        extract_text_value(
            analysis,
            "DEAL BREAKER"
        )
        .upper()
    )

    deal_breaker = (
        deal_breaker_text
        .startswith("YES")
    )


    opportunity_score = (
        calculate_opportunity_score(
            skill_match,
            client_quality,
            budget_quality,
            competition_score,
            win_probability,
            deal_breaker
        )
    )


    decision = (
        decision_from_score(
            opportunity_score
        )
    )


    category = (
        extract_text_value(
            analysis,
            "CATEGORY"
        )
    )


    recommended_bid = (
        extract_section(
            analysis,
            "RECOMMENDED BID",
            "PORTFOLIO TO SHOW"
        )
    )


    proposal = (
        extract_section(
            analysis,
            "PROPOSAL"
        )
    )


    return {

        "job":
            job,

        "analysis":
            analysis,

        "opportunity_score":
            opportunity_score,

        "decision":
            decision,

        "skill_match":
            skill_match,

        "client_quality":
            client_quality,

        "budget_quality":
            budget_quality,

        "competition_score":
            competition_score,

        "win_probability":
            win_probability,

        "deal_breaker":
            deal_breaker,

        "category":
            category,

        "recommended_bid":
            recommended_bid,

        "proposal":
            proposal
    }

def search_upwork_jobs(
    search_expression,
    first=20
):

    query = """
    query SearchJobs(
        $filter: MarketplaceJobPostingsSearchFilter
    ) {
        marketplaceJobPostingsSearch(
            marketPlaceJobFilter: $filter
            searchType: USER_JOBS_SEARCH
            sortAttributes: [
                { field: RECENCY }
            ]
        ) {
            totalCount

            edges {
                node {
                    id
                    title
                    description
                    ciphertext

                    amount {
                        displayValue
                        currency
                    }

                    hourlyBudgetType

                    hourlyBudgetMin {
                        displayValue
                        currency
                    }

                    hourlyBudgetMax {
                        displayValue
                        currency
                    }

                    durationLabel
                    engagement
                    experienceLevel

                    totalApplicants
                    applied
                    enterprise
                    premium

                    createdDateTime
                    publishedDateTime

                    skills {
                        name
                        prettyName
                    }

                    client {
                        totalHires
                        totalPostedJobs
                        totalReviews
                        totalFeedback
                        verificationStatus
                        memberSinceDateTime
                        hasFinancialPrivacy

                        totalSpent {
                            displayValue
                            currency
                        }

                        location {
                            city
                            country
                            timezone
                        }
                    }
                }
            }
        }
    }
    """


    variables = {
        "filter": {

            "searchExpression_eq":
                search_expression,

            "pagination_eq": {
                "after":
                    "0",

                "first":
                    first
            }
        }
    }


    data = upwork_graphql(
        query,
        variables
    )


    result = (
        data.get(
            "marketplaceJobPostingsSearch",
            {}
        )
    )


    return (
        result.get(
            "totalCount",
            0
        ),
        result.get(
            "edges",
            []
        )
    )

def smart_search_upwork_jobs(
    queries=None,
    first_per_query=SMART_SEARCH_PER_QUERY
):

    queries = queries or SMART_SEARCH_QUERIES

    unique_nodes = {}
    errors = []

    for search_expression in queries:

        try:

            _, edges = search_upwork_jobs(
                search_expression,
                first_per_query
            )

            for edge in edges:

                node = (
                    edge.get("node")
                    or {}
                )

                job_id = node.get("id")

                # Prefer the Upwork job ID for deduplication.
                # Fall back to a title+description fingerprint.
                if job_id:

                    dedupe_key = str(job_id)

                else:

                    dedupe_key = (
                        str(node.get("title", "")).strip().lower()
                        + "|"
                        + str(node.get("description", ""))[:300].strip().lower()
                    )

                if dedupe_key not in unique_nodes:

                    unique_nodes[dedupe_key] = node

        except Exception as e:

            errors.append(
                f"{search_expression}: {e}"
            )

    jobs = []
    relevance_filtered_out = 0
    target_fit_filtered_out = 0

    for node in unique_nodes.values():

        job = format_upwork_job(node)

        job["relevance_score"] = relevance_score(
            job
        )

        # Stage 1: broad photo/image-editing relevance.
        if not is_relevant_job(job):
            relevance_filtered_out += 1
            continue

        # Stage 2 (v5.1): commercial target fit. This prevents generic Photoshop,
        # AI, video, 3D, book-design and tutoring jobs from consuming AI analysis.
        if not is_target_fit_job(job):
            target_fit_filtered_out += 1
            continue

        job["quick_fit"] = calculate_quick_fit(
            job
        )

        jobs.append(job)

    jobs = sorted(
        jobs,
        key=lambda x: (
            x.get("quick_fit", 0),
            x.get("relevance_score", 0)
        ),
        reverse=True
    )

    print(
        f"Relevance filter: kept {len(jobs) + target_fit_filtered_out} jobs; "
        f"removed {relevance_filtered_out} unrelated jobs."
    )
    print(
        f"Target Fit v5.1: kept {len(jobs)} jobs; "
        f"removed {target_fit_filtered_out} adjacent/off-target jobs."
    )

    return jobs, errors

def parse_budget(node):

    hourly_min = money_number(
        node.get(
            "hourlyBudgetMin"
        )
    )

    hourly_max = money_number(
        node.get(
            "hourlyBudgetMax"
        )
    )

    fixed_amount = money_number(
        node.get(
            "amount"
        )
    )

    hourly_type = node.get(
        "hourlyBudgetType"
    )


    # HOURLY WITH RANGE

    if (
        hourly_min
        and hourly_min > 0
    ) or (
        hourly_max
        and hourly_max > 0
    ):

        if (
            hourly_min
            and hourly_max
        ):

            text = (
                f"${hourly_min:g}"
                f"-${hourly_max:g}/hr"
            )

        elif hourly_max:

            text = (
                f"Up to "
                f"${hourly_max:g}/hr"
            )

        else:

            text = (
                f"${hourly_min:g}/hr"
            )


        return {
            "type":
                "hourly",

            "text":
                text,

            "hourly_min":
                hourly_min,

            "hourly_max":
                hourly_max,

            "fixed":
                None
        }


    # HOURLY WITHOUT BUDGET

    if hourly_type == "NOT_PROVIDED":

        return {
            "type":
                "hourly",

            "text":
                "Hourly — budget not specified",

            "hourly_min":
                None,

            "hourly_max":
                None,

            "fixed":
                None
        }


    # FIXED

    if (
        fixed_amount
        and fixed_amount > 0
    ):

        return {
            "type":
                "fixed",

            "text":
                f"${fixed_amount:g} fixed",

            "hourly_min":
                None,

            "hourly_max":
                None,

            "fixed":
                fixed_amount
        }


    return {
        "type":
            "unknown",

        "text":
            "Budget not specified",

        "hourly_min":
            None,

        "hourly_max":
            None,

        "fixed":
            None
    }

def format_upwork_job(node):

    client = (
        node.get(
            "client"
        )
        or {}
    )

    location = (
        client.get(
            "location"
        )
        or {}
    )

    budget_info = (
        parse_budget(
            node
        )
    )


    location_parts = [
        location.get(
            "city"
        ),
        location.get(
            "country"
        )
    ]


    location_text = ", ".join([
        x
        for x in location_parts
        if x
    ])


    skills = []


    for skill in (
        node.get(
            "skills"
        )
        or []
    ):

        name = (
            skill.get(
                "prettyName"
            )
            or
            skill.get(
                "name"
            )
        )

        if name:

            skills.append(
                name
            )


    return {

        "id":
            node.get(
                "id",
                ""
            ),

        "title":
            node.get(
                "title",
                ""
            ),

        "description":
            node.get(
                "description",
                ""
            ),

        "ciphertext":
            node.get(
                "ciphertext",
                ""
            ),

        "url":
            (
                "https://www.upwork.com/jobs/"
                + str(node.get("ciphertext", ""))
            )
            if node.get("ciphertext")
            else "",

        "budget":
            budget_info[
                "text"
            ],

        "budget_type":
            budget_info[
                "type"
            ],

        "hourly_min":
            budget_info[
                "hourly_min"
            ],

        "hourly_max":
            budget_info[
                "hourly_max"
            ],

        "fixed_budget":
            budget_info[
                "fixed"
            ],

        "proposals":
            node.get(
                "totalApplicants"
            ),

        "interviewing":
            "",

        "invites":
            "",

        "unanswered_invites":
            "",

        "posted":
            node.get(
                "publishedDateTime",
                ""
            ),

        "project_length":
            node.get(
                "durationLabel",
                ""
            ),

        "client_spent":
            money_display(
                client.get(
                    "totalSpent"
                )
            ),

        "client_spent_number":
            money_number(
                client.get(
                    "totalSpent"
                )
            ),

        "client_hires":
            client.get(
                "totalHires"
            ),

        "client_jobs":
            client.get(
                "totalPostedJobs"
            ),

        "client_reviews":
            client.get(
                "totalReviews"
            ),

        "client_rating":
            client.get(
                "totalFeedback"
            ),

        "payment_verified":
            (
                client.get(
                    "verificationStatus"
                )
                == "VERIFIED"
            ),

        "client_location":
            location_text,

        "active_hires":
            "",

        "hours_billed":
            "",

        "member_since":
            client.get(
                "memberSinceDateTime",
                ""
            ),

        "skills":
            skills,

        "experience_level":
            node.get(
                "experienceLevel",
                ""
            ),

        "enterprise":
            node.get(
                "enterprise",
                False
            ),

        "premium":
            node.get(
                "premium",
                False
            )
    }

def calculate_quick_fit(job):

    score = 0


    text = (
        (
            job.get(
                "title",
                ""
            )
            + " "
            + job.get(
                "description",
                ""
            )
            + " "
            + " ".join(
                job.get(
                    "skills",
                    []
                )
            )
        )
        .lower()
    )


    # SKILLS

    matches = sum(
        1
        for keyword
        in STRONG_KEYWORDS
        if keyword in text
    )


    score += min(
        matches * 8,
        40
    )


    # BUDGET

    if (
        job.get(
            "budget_type"
        )
        == "hourly"
    ):

        hourly_max = (
            job.get(
                "hourly_max"
            )
        )


        if hourly_max is None:

            score += 10

        elif hourly_max >= 50:

            score += 25

        elif hourly_max >= TARGET_HOURLY_RATE:

            score += 20

        elif hourly_max >= 30:

            score += 12

        elif hourly_max >= 25:

            score += 5

        else:

            score -= 15


    elif (
        job.get(
            "budget_type"
        )
        == "fixed"
    ):

        fixed = (
            job.get(
                "fixed_budget"
            )
        )


        if fixed is None:

            score += 5

        elif fixed >= 1000:

            score += 25

        elif fixed >= 500:

            score += 20

        elif fixed >= 250:

            score += 12

        elif fixed >= 100:

            score += 5

        else:

            score -= 10


    else:

        score += 5


    # CLIENT

    spent = (
        job.get(
            "client_spent_number"
        )
        or 0
    )

    hires = (
        job.get(
            "client_hires"
        )
        or 0
    )


    if spent >= 50000:

        score += 12

    elif spent >= 10000:

        score += 10

    elif spent >= 1000:

        score += 7

    elif spent > 0:

        score += 3


    if hires >= 20:

        score += 8

    elif hires >= 5:

        score += 5

    elif hires >= 1:

        score += 2


    # COMPETITION

    applicants = (
        job.get(
            "proposals"
        )
    )


    if applicants is None:

        score += 5

    else:

        try:

            applicants = int(
                applicants
            )


            if applicants <= 5:

                score += 15

            elif applicants <= 10:

                score += 12

            elif applicants <= 20:

                score += 8

            elif applicants <= 30:

                score += 3

            elif applicants >= 50:

                score -= 10


        except Exception:

            score += 5


    if job.get(
        "payment_verified"
    ):

        score += 5


    return max(
        0,
        min(100, score)
    )


def parse_job_posted_datetime(job):
    value = job.get("posted")

    if not value:
        return None

    try:
        raw = str(value).strip()

        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        dt = datetime.fromisoformat(raw)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        return None


def job_age_hours(job):
    posted = parse_job_posted_datetime(job)

    if posted is None:
        return 999.0

    age = (
        datetime.now(timezone.utc) - posted
    ).total_seconds() / 3600.0

    return max(0.0, age)


def freshness_score(job):
    """
    Fresh jobs receive priority before expensive AI analysis.
    """
    age = job_age_hours(job)

    if age <= 0.5:
        return 100
    if age <= 1:
        return 95
    if age <= 2:
        return 90
    if age <= 4:
        return 80
    if age <= 8:
        return 60
    if age <= 12:
        return 40
    if age <= 24:
        return 20
    return 5


def pre_score(job):
    """
    Cheap deterministic score used only to decide which jobs deserve
    full AI analysis first.

    45% relevance + 30% freshness + 15% client quality
    + 10% competition.
    """
    relevance = max(
        0,
        min(
            100,
            float(job.get("relevance_score") or 0) * 10
        )
    )

    freshness = freshness_score(job)

    client_quality = 50.0

    if job.get("payment_verified"):
        client_quality += 15

    try:
        spent = float(job.get("client_spent_raw") or 0)
        if spent >= 10000:
            client_quality += 20
        elif spent >= 1000:
            client_quality += 10
    except Exception:
        pass

    try:
        hires = float(job.get("client_hires") or 0)
        if hires >= 10:
            client_quality += 15
        elif hires >= 3:
            client_quality += 8
    except Exception:
        pass

    client_quality = min(100, client_quality)

    competition = 70.0

    try:
        applicants = float(job.get("proposals") or 0)
        if applicants <= 5:
            competition = 100
        elif applicants <= 10:
            competition = 90
        elif applicants <= 20:
            competition = 75
        elif applicants <= 30:
            competition = 55
        elif applicants <= 50:
            competition = 35
        else:
            competition = 15
    except Exception:
        pass

    return round(
        relevance * 0.45
        + freshness * 0.30
        + client_quality * 0.15
        + competition * 0.10,
        1
    )


def state_key(job):
    return alert_key(job)


def load_scan_states(job_keys):
    """
    Load previously seen jobs in one query.
    """
    if not job_keys:
        return {}

    response = (
        supabase.table("job_scan_state")
        .select(
            "upwork_job_id,first_seen_at,first_analyzed_at,"
            "alerted_at,last_seen_at,posted_at,pre_score,"
            "last_opportunity_score"
        )
        .in_("upwork_job_id", job_keys)
        .execute()
    )

    return {
        row["upwork_job_id"]: row
        for row in (response.data or [])
    }


def upsert_seen_state(job, score, existing=None):
    now_iso = datetime.now(timezone.utc).isoformat()
    key = state_key(job)

    payload = {
        "upwork_job_id": key,
        "job_url": job.get("url") or "",
        "job_title": job.get("title") or "",
        "last_seen_at": now_iso,
        "posted_at": job.get("posted"),
        "pre_score": float(score),
    }

    if not existing:
        payload["first_seen_at"] = now_iso

    supabase.table("job_scan_state").upsert(
        payload,
        on_conflict="upwork_job_id"
    ).execute()


def mark_analyzed_state(job, result):
    supabase.table("job_scan_state").upsert(
        {
            "upwork_job_id": state_key(job),
            "job_url": job.get("url") or "",
            "job_title": job.get("title") or "",
            "first_analyzed_at": datetime.now(timezone.utc).isoformat(),
            "last_opportunity_score": int(
                result.get("opportunity_score") or 0
            ),
        },
        on_conflict="upwork_job_id"
    ).execute()


def mark_alerted_state(job):
    supabase.table("job_scan_state").upsert(
        {
            "upwork_job_id": state_key(job),
            "alerted_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="upwork_job_id"
    ).execute()


def choose_incremental_candidates(jobs, states, now):
    """
    Normal scans:
      - analyze NEW jobs first
      - freshness is part of the pre-score

    20:00 recovery scan:
      - also retry a small number of previously seen but never analyzed jobs
        so promising jobs cannot remain permanently buried below Top N.
    """
    new_jobs = []
    recovery_jobs = []

    for job in jobs:
        key = state_key(job)
        state = states.get(key)
        job["freshness_score"] = freshness_score(job)
        job["pre_score"] = pre_score(job)

        if not state:
            new_jobs.append(job)
        elif not state.get("first_analyzed_at"):
            recovery_jobs.append(job)

    new_jobs.sort(
        key=lambda j: (
            j.get("pre_score", 0),
            j.get("freshness_score", 0),
            j.get("quick_fit", 0),
        ),
        reverse=True,
    )

    recovery_jobs.sort(
        key=lambda j: (
            j.get("pre_score", 0),
            j.get("quick_fit", 0),
        ),
        reverse=True,
    )

    candidates = new_jobs[:NEW_JOB_ANALYZE_LIMIT]

    if now.hour == RECOVERY_SCAN_HOUR or os.getenv("FORCE_RECOVERY", "0") == "1":
        remaining = max(
            0,
            AI_ANALYZE_TOP - len(candidates)
        )

        recovery_limit = min(
            RECOVERY_CANDIDATES,
            remaining
        )

        candidates.extend(
            recovery_jobs[:recovery_limit]
        )

    return candidates, new_jobs, recovery_jobs


def scheduled_slot_now(force=False):
    """
    Return the current Kyiv time and scanner slot key.

    Automatic runs execute only at 08:00, 11:00, 14:00, 17:00 and 20:00
    in the Europe/Kyiv timezone.

    Manual runs can bypass the schedule with:
        python scanner.py --force

    FORCE_RUN=1 is also supported as a fallback.
    """
    now = datetime.now(KYIV_TZ)

    force_run = (
        force
        or "--force" in sys.argv
        or os.getenv("FORCE_RUN", "0") == "1"
    )

    if force_run:
        return now, f"manual-{now:%Y%m%d-%H%M%S}"

    if now.hour not in SCAN_HOURS:
        return now, None

    return now, f"{now:%Y%m%d}-{now.hour:02d}"

def already_ran(slot_key):
    response = (
        supabase.table("scanner_runs")
        .select("slot_key")
        .eq("slot_key", slot_key)
        .limit(1)
        .execute()
    )
    return bool(response.data)

def mark_run(slot_key, jobs_found=0, alerts_sent=0):
    supabase.table("scanner_runs").upsert({
        "slot_key": slot_key,
        "jobs_found": jobs_found,
        "alerts_sent": alerts_sent
    }).execute()

def alert_key(job):
    if job.get("id"):
        return str(job["id"])
    raw = (job.get("url") or "") + "|" + (job.get("title") or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def was_alerted(job):
    key = alert_key(job)
    response = (
        supabase.table("job_alerts")
        .select("upwork_job_id")
        .eq("upwork_job_id", key)
        .limit(1)
        .execute()
    )
    return bool(response.data)

def save_alert(job, result):
    supabase.table("job_alerts").upsert({
        "upwork_job_id": alert_key(job),
        "job_url": job.get("url") or "",
        "job_title": job.get("title") or "",
        "opportunity_score": int(result.get("opportunity_score") or 0),
        "decision": result.get("decision") or ""
    }).execute()

def telegram_send(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=30
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(str(payload))

def format_alert(result):
    job = result["job"]

    title = html.escape(job.get("title") or "Untitled job")
    budget = html.escape(str(job.get("budget") or "Unknown"))

    applicants = job.get("proposals")
    applicants = "Unknown" if applicants is None else str(applicants)

    spent = html.escape(str(job.get("client_spent") or "Unknown"))

    hires = job.get("client_hires")
    hires = "Unknown" if hires is None else str(hires)

    bid = html.escape(str(result.get("recommended_bid") or "—"))
    category = html.escape(str(result.get("category") or "—"))
    decision = html.escape(str(result.get("decision") or "—"))

    score = int(result.get("opportunity_score") or 0)
    win = int(result.get("win_probability") or 0)

    url = html.escape(job.get("url") or "")

    why = extract_section(
        result.get("analysis") or "",
        "WHY YOU CAN WIN",
        "WHY THIS JOB IS ATTRACTIVE"
    )
    why = html.escape(
        why[:500] if why else "Strong fit based on the AI analysis."
    )

    proposal = (
        result.get("proposal")
        or extract_section(
            result.get("analysis") or "",
            "PROPOSAL"
        )
        or ""
    ).strip()

    if not proposal:
        proposal = (
            "Hi,\n\n"
            "Your project caught my eye because the scope aligns closely "
            "with the kind of image work I handle.\n\n"
            "I've done very similar work — here's "
            "[INSERT RELEVANT PORTFOLIO LINK].\n\n"
            "Happy to share more examples. What's the best way to connect?\n\n"
            "Andrew"
        )

    proposal = html.escape(proposal)

    lines = [
        f"🔥 <b>UPWORK OPPORTUNITY — {score}/100</b>",
        f"<b>{title}</b>",
        "",
        f"💰 Budget: {budget}",
        f"👥 Applicants: {applicants}",
        f"💳 Client spent: {spent}",
        f"✅ Client hires: {hires}",
        f"🎯 Win probability: {win}/100",
        f"💵 Recommended bid: {bid}",
        f"🧩 Category: {category}",
        f"📌 Decision: {decision}",
        "",
        f"<b>Why you can win:</b> {why}",
        "",
        "<b>✉️ COVER LETTER</b>",
        "",
        proposal,
    ]

    if url:
        lines += [
            "",
            f'<a href="{url}">🚀 Open on Upwork</a>'
        ]

    return "\n".join(lines)

def main():
    force_run = (
        "--force" in sys.argv
        or os.getenv("FORCE_RUN", "0") == "1"
    )

    now, slot_key = scheduled_slot_now(
        force=force_run
    )

    if force_run:
        print(
            f"[{now.isoformat()}] Manual FORCE scan requested."
        )

    if slot_key is None:
        print(
            f"[{now.isoformat()}] "
            "Not a scheduled Kyiv scan hour; exiting."
        )
        return 0
    if not slot_key.startswith("manual-") and already_ran(slot_key):
        print(f"Slot {slot_key} already completed; exiting.")
        return 0

    # Refresh once at the beginning so the rotating refresh token stays active.
    refresh_upwork_access_token()

    jobs, errors = smart_search_upwork_jobs(first_per_query=SMART_SEARCH_PER_QUERY)
    if errors:
        print("Search warnings:")
        for err in errors:
            print(" -", err)

    job_keys = [
        state_key(job)
        for job in jobs
    ]

    states = load_scan_states(
        job_keys
    )

    # Record first_seen_at / last_seen_at / pre_score for every relevant job.
    for job in jobs:
        score = pre_score(job)
        job["freshness_score"] = freshness_score(job)
        job["pre_score"] = score

        try:
            upsert_seen_state(
                job,
                score,
                states.get(state_key(job))
            )
        except Exception as exc:
            print(
                f"State save warning for {job.get('title')}: {exc}"
            )

    candidates, new_jobs, recovery_jobs = choose_incremental_candidates(
        jobs,
        states,
        now
    )

    print(
        f"Found {len(jobs)} relevant unique jobs; "
        f"{len(new_jobs)} NEW; "
        f"{len(recovery_jobs)} previously seen but not analyzed."
    )

    if now.hour == RECOVERY_SCAN_HOUR and not force_run:
        print(
            f"20:00 recovery scan enabled; "
            f"analyzing up to {RECOVERY_CANDIDATES} older missed candidates "
            f"in addition to new jobs."
        )

    print(
        f"Full AI analysis candidates: {len(candidates)}."
    )

    strong = []
    analyzed_results = []

    for i, job in enumerate(candidates, start=1):
        try:
            print(
                f"Analyzing {i}/{len(candidates)} "
                f"[age={job_age_hours(job):.1f}h, "
                f"fresh={job.get('freshness_score')}, "
                f"pre={job.get('pre_score')}]: "
                f"{job.get('title')}"
            )

            result = analyze_job_with_ai(job)
            analyzed_results.append(result)

            print(
                "  DIAGNOSTIC | "
                f"Opportunity={int(result.get('opportunity_score') or 0)}/100 | "
                f"Skill={int(result.get('skill_match') or 0)}/100 | "
                f"Client={int(result.get('client_quality') or 0)}/100 | "
                f"Budget={int(result.get('budget_quality') or 0)}/100 | "
                f"Competition={int(result.get('competition_score') or 0)}/100 | "
                f"Win={int(result.get('win_probability') or 0)}/100 | "
                f"Decision={result.get('decision') or '—'}"
            )

            try:
                mark_analyzed_state(
                    job,
                    result
                )
            except Exception as exc:
                print(
                    f"Analysis state warning for {job.get('title')}: {exc}"
                )

            if int(
                result.get("opportunity_score") or 0
            ) >= OPPORTUNITY_THRESHOLD:
                strong.append(result)

        except Exception as exc:
            print(
                f"AI analysis failed for {job.get('title')}: {exc}"
            )

    if analyzed_results:
        scores = [int(r.get("opportunity_score") or 0) for r in analyzed_results]
        print("")
        print("=== DIAGNOSTIC SCORE SUMMARY ===")
        print(f"Analyzed successfully: {len(scores)}")
        print(f"80+: {sum(s >= 80 for s in scores)}")
        print(f"75-79: {sum(75 <= s <= 79 for s in scores)}")
        print(f"70-74: {sum(70 <= s <= 74 for s in scores)}")
        print(f"<70: {sum(s < 70 for s in scores)}")
        print(f"Highest score: {max(scores)}/100")
        print(f"Average score: {sum(scores) / len(scores):.1f}/100")
        print("================================")
    else:
        print("Diagnostic summary: no jobs were successfully AI-analyzed.")

    new_alerts = [r for r in strong if not was_alerted(r["job"])]
    new_alerts.sort(key=lambda r: r.get("opportunity_score", 0), reverse=True)

    sent = 0
    for result in new_alerts:
        telegram_send(format_alert(result))
        save_alert(result["job"], result)
        mark_alerted_state(result["job"])
        sent += 1

    mark_run(slot_key, jobs_found=len(jobs), alerts_sent=sent)
    print(f"Strong jobs: {len(strong)}; new Telegram alerts sent: {sent}.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"SCANNER FAILED: {exc}", file=sys.stderr)
        raise

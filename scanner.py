import os
import sys
import re
import html
import hashlib
from datetime import datetime
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
AI_ANALYZE_TOP = int(os.getenv("AI_ANALYZE_TOP", "15"))
OPPORTUNITY_THRESHOLD = int(os.getenv("OPPORTUNITY_THRESHOLD", "80"))
KYIV_TZ = ZoneInfo("Europe/Kyiv")
SCAN_HOURS = {8, 12, 16, 20}

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
# RELEVANCE FILTER
# =====================================================

RELEVANCE_KEYWORDS = [
    "amazon listing",
    "amazon product",
    "amazon images",
    "amazon image",
    "a+ content",
    "e-commerce",
    "ecommerce",
    "product image",
    "product images",
    "product photo",
    "product photos",
    "product photography",
    "product retouch",
    "product retouching",
    "product editing",
    "listing image",
    "listing images",
    "lifestyle image",
    "lifestyle images",
    "packshot",
    "pack shot",
    "photo retouch",
    "photo retouching",
    "high-end retouch",
    "high end retouch",
    "photo editing",
    "image editing",
    "photoshop",
    "compositing",
    "composite",
    "background replacement",
    "background removal",
    "image manipulation",
    "photo manipulation",
    "lightroom",
    "ai image",
    "ai images",
    "ai photography",
    "ai product photography",
    "generative ai",
    "ai + photoshop",
    "ai photoshop",
    "photorealistic ai",
    "architectural photo",
    "architectural photography",
    "architectural retouch",
    "architecture retouch",
    "interior photo",
    "interior photography",
    "interior retouch",
    "real estate photo",
    "real estate photography",
    "real estate editing",
    "virtual staging",
    "portrait retouch",
    "portrait retouching",
    "beauty retouch",
    "beauty retouching",
    "skin retouch",
]

GENERIC_VISUAL_KEYWORDS = [
    "retouch",
    "retouching",
    "photoshop",
    "photo editor",
    "photo editing",
    "image editor",
    "image editing",
    "photographer",
    "photography",
    "compositing",
    "lightroom",
]

NEGATIVE_KEYWORDS = [
    "web developer",
    "web development",
    "shopify developer",
    "wordpress developer",
    "frontend developer",
    "front-end developer",
    "backend developer",
    "back-end developer",
    "full stack developer",
    "full-stack developer",
    "ui/ux",
    "ux/ui",
    "ui designer",
    "ux designer",
    "logo design",
    "logo designer",
    "brand identity",
    "branding designer",
    "illustrator",
    "illustration",
    "social media manager",
    "social media marketing",
    "meta ads",
    "facebook ads",
    "google ads",
    "seo",
    "email marketing",
    "copywriter",
    "copywriting",
    "content writer",
    "video editor",
    "video editing",
    "motion graphics",
    "animation",
    "3d developer",
    "software developer",
    "mobile app developer",
]

RELEVANCE_MIN_SCORE = int(
    os.getenv("RELEVANCE_MIN_SCORE", "3")
)


def job_search_text(job):
    return (
        (
            str(job.get("title") or "")
            + " "
            + str(job.get("description") or "")
            + " "
            + " ".join(job.get("skills") or [])
        )
        .lower()
    )


def relevance_score(job):
    text = job_search_text(job)

    strong_matches = [
        keyword
        for keyword in RELEVANCE_KEYWORDS
        if keyword in text
    ]

    generic_matches = [
        keyword
        for keyword in GENERIC_VISUAL_KEYWORDS
        if keyword in text
    ]

    negative_matches = [
        keyword
        for keyword in NEGATIVE_KEYWORDS
        if keyword in text
    ]

    score = 0
    score += min(len(strong_matches) * 3, 15)
    score += min(len(generic_matches), 3)

    if negative_matches and not strong_matches:
        score -= 8

    if not strong_matches and any(
        bad in text
        for bad in [
            "developer",
            "development",
            "seo",
            "marketing",
            "ads",
            "copywriter",
            "copywriting",
        ]
    ):
        score -= 4

    return score


def is_relevant_job(job):
    return relevance_score(job) >= RELEVANCE_MIN_SCORE


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
Write a personalized Upwork proposal
of approximately 100-140 words.

Never begin with:
"I am excited to apply."

Start with the client's actual problem.

Sound natural, concise and confident.
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
    filtered_out = 0

    for node in unique_nodes.values():

        job = format_upwork_job(node)

        job["relevance_score"] = relevance_score(
            job
        )

        if not is_relevant_job(job):
            filtered_out += 1
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
        f"Relevance filter: kept {len(jobs)} jobs; "
        f"removed {filtered_out} unrelated jobs."
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

def scheduled_slot_now(force=False):
    """
    Return the current Kyiv time and scanner slot key.

    Automatic runs execute only at 08:00, 12:00, 16:00 and 20:00
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
    why = extract_section(result.get("analysis") or "", "WHY YOU CAN WIN", "WHY THIS JOB IS ATTRACTIVE")
    why = html.escape(why[:450] if why else "Strong fit based on the AI analysis.")
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
        f"<b>Why you can win:</b> {why}"
    ]
    if url:
        lines += ["", f'<a href="{url}">🚀 Open on Upwork</a>']
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

    candidates = jobs[:AI_ANALYZE_TOP]
    print(f"Found {len(jobs)} relevant unique jobs; analyzing top {len(candidates)}.")

    strong = []
    for i, job in enumerate(candidates, start=1):
        try:
            print(f"Analyzing {i}/{len(candidates)}: {job.get('title')}")
            result = analyze_job_with_ai(job)
            if int(result.get("opportunity_score") or 0) >= OPPORTUNITY_THRESHOLD:
                strong.append(result)
        except Exception as exc:
            print(f"AI analysis failed for {job.get('title')}: {exc}")

    new_alerts = [r for r in strong if not was_alerted(r["job"])]
    new_alerts.sort(key=lambda r: r.get("opportunity_score", 0), reverse=True)

    sent = 0
    for result in new_alerts:
        telegram_send(format_alert(result))
        save_alert(result["job"], result)
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

import streamlit as st
import re
import requests
from urllib.parse import urlencode
from openai import OpenAI
from supabase import create_client


# =====================================================
# SETTINGS
# =====================================================

st.set_page_config(
    page_title="Upwork Opportunity Assistant",
    page_icon="🎯",
    layout="wide"
)

TARGET_HOURLY_RATE = 35

# =====================================================
# SMART SEARCH SETTINGS
# =====================================================

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

SMART_SEARCH_PER_QUERY = 20

UPWORK_AUTH_URL = (
    "https://www.upwork.com/"
    "ab/account-security/oauth2/authorize"
)

UPWORK_TOKEN_URL = (
    "https://www.upwork.com/api/v3/oauth2/token"
)

UPWORK_GRAPHQL_URL = (
    "https://api.upwork.com/graphql"
)


# =====================================================
# CLIENTS
# =====================================================

openai_client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)


# =====================================================
# UPWORK SETTINGS
# =====================================================

upwork_api_enabled = st.secrets.get(
    "UPWORK_API_ENABLED",
    False
)

upwork_client_id = st.secrets.get(
    "UPWORK_CLIENT_ID",
    ""
)

upwork_client_secret = st.secrets.get(
    "UPWORK_CLIENT_SECRET",
    ""
)

upwork_redirect_uri = st.secrets.get(
    "UPWORK_REDIRECT_URI",
    ""
)


# =====================================================
# HELPERS
# =====================================================

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


def clear_analysis_state():

    keys = [
        "analysis",
        "opportunity_score",
        "decision",
        "skill_match",
        "client_quality",
        "budget_quality",
        "competition_score",
        "win_probability",
        "category",
        "proposal",
        "recommended_bid",
        "deal_breaker"
    ]

    for key in keys:

        st.session_state.pop(
            key,
            None
        )


def job_state_key(
    job,
    index=None
):

    job_id = job.get(
        "id"
    )

    if job_id:
        return str(
            job_id
        )

    title = job.get(
        "title",
        "job"
    )

    return (
        f"{index}_{title}"
    )


# =====================================================
# MONEY HELPERS
# =====================================================

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


# =====================================================
# OPPORTUNITY SCORE
# =====================================================

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


# =====================================================
# AI PROMPT
# =====================================================

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

Freelancer target sustainable hourly rate:

${TARGET_HOURLY_RATE}/hour

For HOURLY jobs:

Do NOT judge the job by the lowest number
in the client's hourly range.

Instead determine whether the freelancer can reasonably
bid around ${TARGET_HOURLY_RATE}/hour.

Examples:

$15-$35/hr:
reasonable because freelancer can bid $35/hr.

$25-$50/hr:
good budget.

$10-$25/hr:
weak budget because the freelancer's target rate
does not fit.

For FIXED jobs:

Compare realistic workload against the fixed budget.

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

Example:
Recommended: $35/hr.

or:
Recommended: $600-$800 fixed.

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


# =====================================================
# RUN AI ANALYSIS
# =====================================================

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


# =====================================================
# LOAD ANALYSIS INTO MAIN ANALYZER
# =====================================================

def load_analysis_into_session(
    result
):

    job = result[
        "job"
    ]

    fields = {
        "analysis":
            result.get(
                "analysis"
            ),

        "opportunity_score":
            result.get(
                "opportunity_score"
            ),

        "decision":
            result.get(
                "decision"
            ),

        "skill_match":
            result.get(
                "skill_match"
            ),

        "client_quality":
            result.get(
                "client_quality"
            ),

        "budget_quality":
            result.get(
                "budget_quality"
            ),

        "competition_score":
            result.get(
                "competition_score"
            ),

        "win_probability":
            result.get(
                "win_probability"
            ),

        "category":
            result.get(
                "category"
            ),

        "recommended_bid":
            result.get(
                "recommended_bid"
            ),

        "proposal":
            result.get(
                "proposal"
            ),

        "deal_breaker":
            result.get(
                "deal_breaker"
            ),

        "job_title":
            job.get(
                "title",
                ""
            ),

        "job_url":
            job.get(
                "url",
                ""
            ),

        "job_description":
            job.get(
                "description",
                ""
            )
    }


    for key, value in fields.items():

        st.session_state[
            key
        ] = value


# =====================================================
# UPWORK OAUTH
# =====================================================

def build_upwork_auth_url():

    params = {
        "response_type":
            "code",

        "client_id":
            upwork_client_id,

        "redirect_uri":
            upwork_redirect_uri
    }

    return (
        UPWORK_AUTH_URL
        + "?"
        + urlencode(params)
    )


def exchange_upwork_code(
    code
):

    response = requests.post(
        UPWORK_TOKEN_URL,
        headers={
            "Accept":
                "application/json",

            "Content-Type":
                "application/x-www-form-urlencoded"
        },
        data={
            "grant_type":
                "authorization_code",

            "client_id":
                upwork_client_id,

            "client_secret":
                upwork_client_secret,

            "code":
                code,

            "redirect_uri":
                upwork_redirect_uri
        },
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# =====================================================
# OAUTH CALLBACK
# =====================================================

if upwork_api_enabled:

    oauth_code = (
        st.query_params.get(
            "code"
        )
    )

    if (
        oauth_code
        and
        "UPWORK_ACCESS_TOKEN"
        not in st.session_state
    ):

        try:

            token_data = (
                exchange_upwork_code(
                    oauth_code
                )
            )

            st.session_state[
                "UPWORK_ACCESS_TOKEN"
            ] = token_data.get(
                "access_token"
            )

            st.session_state[
                "UPWORK_REFRESH_TOKEN"
            ] = token_data.get(
                "refresh_token"
            )

            st.query_params.clear()

            st.rerun()

        except Exception as e:

            st.error(
                "Upwork authorization failed."
            )

            st.code(
                str(e)
            )


# =====================================================
# GRAPHQL
# =====================================================

def upwork_graphql(
    query,
    variables=None
):

    token = (
        st.session_state.get(
            "UPWORK_ACCESS_TOKEN"
        )
    )

    if not token:

        raise Exception(
            "Upwork is not connected."
        )


    response = requests.post(
        UPWORK_GRAPHQL_URL,
        headers={
            "Authorization":
                f"Bearer {token}",

            "Content-Type":
                "application/json"
        },
        json={
            "query":
                query,

            "variables":
                variables or {}
        },
        timeout=30
    )


    response.raise_for_status()

    payload = response.json()


    if payload.get(
        "errors"
    ):

        raise Exception(
            str(
                payload[
                    "errors"
                ]
            )
        )


    return payload.get(
        "data",
        {}
    )


# =====================================================
# SEARCH UPWORK
# =====================================================

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


# =====================================================
# SMART SEARCH
# =====================================================

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

    for node in unique_nodes.values():

        job = format_upwork_job(node)

        job["quick_fit"] = calculate_quick_fit(
            job
        )

        jobs.append(job)

    jobs = sorted(
        jobs,
        key=lambda x: x.get("quick_fit", 0),
        reverse=True
    )

    return jobs, errors


# =====================================================
# BUDGET PARSING
# =====================================================

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


# =====================================================
# FORMAT UPWORK JOB
# =====================================================

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

        "url":
            "",

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


# =====================================================
# QUICK FIT
# =====================================================

STRONG_KEYWORDS = [
    "photoshop",
    "retouch",
    "retouching",
    "photo editing",
    "image editing",
    "image enhancement",
    "photo manipulation",
    "product image",
    "product photography",
    "e-commerce",
    "ecommerce",
    "amazon",
    "listing image",
    "lifestyle image",
    "compositing",
    "composite",
    "background replacement",
    "image manipulation",
    "ai image",
    "ai-generated",
    "generative ai",
    "interior",
    "architecture",
    "architectural",
    "real estate",
    "lightroom"
]


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


def quick_fit_label(score):

    if score >= 75:
        return "🔥 Strong"

    if score >= 55:
        return "🟢 Good"

    if score >= 40:
        return "🟡 Review"

    return "🔴 Weak"


# =====================================================
# PREFILL MAIN ANALYZER
# MUST RUN BEFORE WIDGETS ARE CREATED
# =====================================================

if st.session_state.get(
    "load_job_into_analyzer"
):

    selected_job = (
        st.session_state.get(
            "selected_job",
            {}
        )
    )


    mappings = {

        "job_title_input":
            "title",

        "job_url_input":
            "url",

        "job_description_input":
            "description",

        "budget_input":
            "budget",

        "proposals_input":
            "proposals",

        "interviewing_input":
            "interviewing",

        "invites_input":
            "invites",

        "unanswered_invites_input":
            "unanswered_invites",

        "posted_input":
            "posted",

        "client_spent_input":
            "client_spent",

        "client_hires_input":
            "client_hires",

        "client_rating_input":
            "client_rating",

        "client_location_input":
            "client_location",

        "active_hires_input":
            "active_hires",

        "hours_billed_input":
            "hours_billed",

        "member_since_input":
            "member_since",

        "project_length_input":
            "project_length"
    }


    for session_key, job_key in mappings.items():

        value = selected_job.get(
            job_key,
            ""
        )

        if value is None:

            value = ""

        st.session_state[
            session_key
        ] = str(
            value
        )


    st.session_state[
        "load_job_into_analyzer"
    ] = False


# =====================================================
# LOAD PREVIOUSLY GENERATED ANALYSIS
# =====================================================

if st.session_state.get(
    "pending_analysis_result"
):

    pending_result = (
        st.session_state.pop(
            "pending_analysis_result"
        )
    )


    load_analysis_into_session(
        pending_result
    )


# =====================================================
# HEADER
# =====================================================

st.title(
    "🎯 Upwork Opportunity Assistant"
)

st.caption(
    "Find the Upwork opportunities that are actually worth applying to."
)


# =====================================================
# SIDEBAR
# =====================================================

with st.sidebar:

    st.header(
        "🔗 Upwork API"
    )


    if not upwork_api_enabled:

        st.warning(
            "API disabled"
        )


    elif st.session_state.get(
        "UPWORK_ACCESS_TOKEN"
    ):

        st.success(
            "✅ Upwork connected"
        )


        if st.button(
            "Disconnect Upwork",
            use_container_width=True
        ):

            st.session_state.pop(
                "UPWORK_ACCESS_TOKEN",
                None
            )

            st.session_state.pop(
                "UPWORK_REFRESH_TOKEN",
                None
            )

            st.rerun()


    else:

        st.info(
            "🔑 API ready"
        )


        st.link_button(
            "Connect Upwork",
            build_upwork_auth_url(),
            use_container_width=True
        )


    st.divider()


    st.markdown(
        "### 💵 Pricing"
    )


    st.metric(
        "Target hourly rate",
        f"${TARGET_HOURLY_RATE}/hr"
    )


    st.divider()


    st.markdown(
        "### 🎯 Workflow"
    )


    st.write("""
    1. Smart Search across your niches
    2. Remove duplicates
    3. Quick Fit removes noise
    4. AI analyzes Top 15
    5. Daily Best keeps score ≥80
    6. Decide APPLY / SKIP
    7. Generate proposal
    8. Save & track results
    """)


# =====================================================
# TABS
# =====================================================

tab1, tab2, tab3 = st.tabs([
    "🎯 Analyze Job",
    "🔎 Find Jobs",
    "📊 Job History"
])


# =====================================================
# TAB 1 — ANALYZE JOB
# =====================================================

with tab1:

    if st.session_state.get(
        "selected_job_loaded_message"
    ):

        st.success(
            "✅ Job and AI analysis loaded."
        )

        st.session_state[
            "selected_job_loaded_message"
        ] = False


    st.subheader(
        "Job Information"
    )


    col1, col2 = st.columns(
        [2, 1]
    )


    with col1:

        job_title = st.text_input(
            "Job title",
            key="job_title_input"
        )


        job_url = st.text_input(
            "Upwork URL",
            key="job_url_input"
        )


        job_description = st.text_area(
            "Job description",
            height=420,
            key="job_description_input"
        )


    with col2:

        st.markdown(
            "### 💰 Budget & Competition"
        )


        budget = st.text_input(
            "Budget / Hourly Rate",
            key="budget_input"
        )


        proposals = st.text_input(
            "Applicants",
            key="proposals_input"
        )


        interviewing = st.text_input(
            "Interviewing",
            key="interviewing_input"
        )


        invites = st.text_input(
            "Invites sent",
            key="invites_input"
        )


        unanswered_invites = (
            st.text_input(
                "Unanswered invites",
                key="unanswered_invites_input"
            )
        )


        posted = st.text_input(
            "Posted",
            key="posted_input"
        )


    st.divider()


    st.markdown(
        "### 👤 Client Information"
    )


    c1, c2, c3, c4 = st.columns(4)


    with c1:

        client_spent = st.text_input(
            "Client total spent",
            key="client_spent_input"
        )


    with c2:

        client_hires = st.text_input(
            "Client hires",
            key="client_hires_input"
        )


    with c3:

        client_rating = st.text_input(
            "Client rating",
            key="client_rating_input"
        )


    with c4:

        client_location = st.text_input(
            "Client location",
            key="client_location_input"
        )


    c5, c6, c7, c8 = st.columns(4)


    with c5:

        client_active_hires = (
            st.text_input(
                "Active hires",
                key="active_hires_input"
            )
        )


    with c6:

        client_hours = st.text_input(
            "Hours billed",
            key="hours_billed_input"
        )


    with c7:

        client_member_since = (
            st.text_input(
                "Member since",
                key="member_since_input"
            )
        )


    with c8:

        project_length = st.text_input(
            "Project length",
            key="project_length_input"
        )


    st.info(
        f"Target hourly rate: "
        f"${TARGET_HOURLY_RATE}/hr."
    )


    # =================================================
    # MANUAL ANALYZE
    # =================================================

    if st.button(
        "🚀 Analyze Job",
        type="primary",
        use_container_width=True
    ):

        if not job_description.strip():

            st.warning(
                "Job description is missing."
            )


        else:

            manual_job = {

                "title":
                    job_title,

                "url":
                    job_url,

                "description":
                    job_description,

                "budget":
                    budget,

                "proposals":
                    proposals,

                "interviewing":
                    interviewing,

                "invites":
                    invites,

                "posted":
                    posted,

                "project_length":
                    project_length,

                "client_spent":
                    client_spent,

                "client_hires":
                    client_hires,

                "client_rating":
                    client_rating,

                "client_location":
                    client_location,

                "member_since":
                    client_member_since,

                "experience_level":
                    "",

                "skills":
                    []
            }


            with st.spinner(
                "Analyzing opportunity..."
            ):

                try:

                    result = (
                        analyze_job_with_ai(
                            manual_job
                        )
                    )

                    load_analysis_into_session(
                        result
                    )


                except Exception as e:

                    st.error(
                        "AI analysis failed."
                    )

                    st.code(
                        str(e)
                    )


    # =================================================
    # DISPLAY MAIN ANALYSIS
    # =================================================

    if "analysis" in st.session_state:

        st.divider()


        st.subheader(
            "📈 Opportunity Overview"
        )


        score = (
            st.session_state.get(
                "opportunity_score"
            )
        )

        decision = (
            st.session_state.get(
                "decision"
            )
        )


        o1, o2 = st.columns(
            [2, 1]
        )


        o1.metric(
            "Opportunity Score",
            f"{score}/100"
        )


        with o2:

            st.markdown(
                "### Decision"
            )

            st.markdown(
                f"## {decision}"
            )


        st.write(
            "**Category:**",
            st.session_state.get(
                "category",
                ""
            )
        )


        c1, c2, c3 = st.columns(3)


        c1.metric(
            "Skill Match",
            f"{st.session_state.get('skill_match')}/100"
        )


        c2.metric(
            "Client Quality",
            f"{st.session_state.get('client_quality')}/100"
        )


        c3.metric(
            "Budget Quality",
            f"{st.session_state.get('budget_quality')}/100"
        )


        c4, c5 = st.columns(2)


        c4.metric(
            "Competition",
            f"{st.session_state.get('competition_score')}/100"
        )


        c5.metric(
            "Win Probability",
            f"{st.session_state.get('win_probability')}/100"
        )


        if st.session_state.get(
            "recommended_bid"
        ):

            st.info(
                "💵 "
                + st.session_state[
                    "recommended_bid"
                ]
            )


        st.divider()


        st.subheader(
            "🤖 Detailed Analysis"
        )


        st.markdown(
            st.session_state[
                "analysis"
            ]
        )


        # =================================================
        # SAVE
        # =================================================

        st.divider()


        st.subheader(
            "💾 Save to Job History"
        )


        status = st.selectbox(
            "Current status",
            [
                "Not applied",
                "Applied",
                "Interview",
                "Hired",
                "Rejected"
            ]
        )


        contract_value = st.number_input(
            "Contract value ($)",
            min_value=0.0,
            value=0.0,
            step=50.0
        )


        if st.button(
            "Save to History",
            use_container_width=True
        ):

            try:

                data = {

                    "job_title":
                        st.session_state.get(
                            "job_title"
                        ),

                    "job_url":
                        st.session_state.get(
                            "job_url"
                        ),

                    "job_description":
                        st.session_state.get(
                            "job_description"
                        ),

                    "opportunity_score":
                        st.session_state.get(
                            "opportunity_score"
                        ),

                    "skill_match":
                        st.session_state.get(
                            "skill_match"
                        ),

                    "client_quality":
                        st.session_state.get(
                            "client_quality"
                        ),

                    "budget_quality":
                        st.session_state.get(
                            "budget_quality"
                        ),

                    "competition_score":
                        st.session_state.get(
                            "competition_score"
                        ),

                    "win_probability":
                        st.session_state.get(
                            "win_probability"
                        ),

                    "decision":
                        st.session_state.get(
                            "decision"
                        ),

                    "category":
                        st.session_state.get(
                            "category"
                        ),

                    "status":
                        status,

                    "proposal":
                        st.session_state.get(
                            "proposal"
                        ),

                    "contract_value":
                        contract_value
                }


                (
                    supabase
                    .table(
                        "jobs"
                    )
                    .insert(
                        data
                    )
                    .execute()
                )


                st.success(
                    "✅ Job saved!"
                )


            except Exception as e:

                st.error(
                    "Could not save job."
                )

                st.code(
                    str(e)
                )


# =====================================================
# TAB 2 — FIND JOBS
# =====================================================

with tab2:

    st.subheader(
        "🔎 Find Jobs"
    )


    if not st.session_state.get(
        "UPWORK_ACCESS_TOKEN"
    ):

        st.warning(
            "Connect Upwork first."
        )


    else:

        st.success(
            "🟢 LIVE Upwork marketplace search"
        )


        search_mode = st.radio(
            "Search mode",
            [
                "🔥 Smart Search for Me",
                "🔎 Manual Search"
            ],
            horizontal=True
        )


        if search_mode == "🔎 Manual Search":

            s1, s2 = st.columns(
                [4, 1]
            )

            with s1:

                search_expression = st.text_input(
                    "Search Upwork",
                    value="photo editing retouching"
                )

            with s2:

                results_count = st.selectbox(
                    "Results",
                    [
                        10,
                        20,
                        50
                    ],
                    index=1
                )

            search_button_label = "🔎 Search Upwork"

        else:

            st.info(
                "Smart Search checks your strongest niches, "
                "combines the results, removes duplicates and "
                "ranks them with Quick Fit before AI analysis."
            )

            with st.expander(
                "Search niches"
            ):

                for query_text in SMART_SEARCH_QUERIES:

                    st.write(
                        "•",
                        query_text
                    )

            search_button_label = "🔥 Find Best Jobs for Me"


        # =================================================
        # SEARCH
        # =================================================

        if st.button(
            search_button_label,
            type="primary",
            use_container_width=True
        ):

            with st.spinner(
                "Searching Upwork..."
            ):

                try:

                    if search_mode == "🔥 Smart Search for Me":

                        live_jobs, smart_errors = (
                            smart_search_upwork_jobs()
                        )

                        st.session_state[
                            "live_jobs"
                        ] = live_jobs

                        st.session_state[
                            "live_total_count"
                        ] = len(
                            live_jobs
                        )

                        st.session_state[
                            "search_mode_used"
                        ] = "smart"

                        if smart_errors:

                            st.warning(
                                "Some search niches could not be loaded, "
                                "but the available results were kept."
                            )

                    else:

                        if not search_expression.strip():

                            st.warning(
                                "Enter a search phrase."
                            )

                            st.stop()

                        total_count, edges = (
                            search_upwork_jobs(
                                search_expression,
                                results_count
                            )
                        )

                        live_jobs = []

                        for edge in edges:

                            node = (
                                edge.get("node")
                                or {}
                            )

                            job = format_upwork_job(
                                node
                            )

                            job["quick_fit"] = (
                                calculate_quick_fit(
                                    job
                                )
                            )

                            live_jobs.append(
                                job
                            )

                        live_jobs = sorted(
                            live_jobs,
                            key=lambda x: x["quick_fit"],
                            reverse=True
                        )

                        st.session_state[
                            "live_jobs"
                        ] = live_jobs

                        st.session_state[
                            "live_total_count"
                        ] = total_count

                        st.session_state[
                            "search_mode_used"
                        ] = "manual"


                    # Clear old AI results after every new search

                    st.session_state.pop(
                        "top_job_analyses",
                        None
                    )

                    st.session_state[
                        "single_job_analyses"
                    ] = {}

                    st.success(
                        f"✅ Loaded {len(st.session_state.get('live_jobs', []))} "
                        "unique jobs."
                    )

                except Exception as e:

                    st.error(
                        "Upwork search failed."
                    )

                    st.code(
                        str(e)
                    )


        live_jobs = (
            st.session_state.get(
                "live_jobs",
                []
            )
        )


        # =================================================
        # FILTERS
        # =================================================

        if live_jobs:

            st.divider()


            st.markdown(
                "### 🎚️ Quick Filter"
            )


            f1, f2, f3 = st.columns(3)


            with f1:

                minimum_quick_fit = (
                    st.slider(
                        "Minimum Quick Fit",
                        0,
                        100,
                        40,
                        5
                    )
                )


            with f2:

                hide_low_hourly = (
                    st.checkbox(
                        "Hide hourly jobs under $25/hr",
                        value=True
                    )
                )


            with f3:

                max_applicants = (
                    st.selectbox(
                        "Maximum applicants",
                        [
                            "Any",
                            10,
                            20,
                            30,
                            50
                        ],
                        index=2
                    )
                )


            filtered_jobs = []


            for job in live_jobs:

                if (
                    job[
                        "quick_fit"
                    ]
                    <
                    minimum_quick_fit
                ):

                    continue


                if hide_low_hourly:

                    if (
                        job.get(
                            "budget_type"
                        )
                        == "hourly"
                    ):

                        max_rate = (
                            job.get(
                                "hourly_max"
                            )
                        )


                        if (
                            max_rate
                            is not None
                            and
                            max_rate < 25
                        ):

                            continue


                if (
                    max_applicants
                    != "Any"
                ):

                    applicants = (
                        job.get(
                            "proposals"
                        )
                    )


                    if applicants is not None:

                        try:

                            if (
                                int(
                                    applicants
                                )
                                >
                                int(
                                    max_applicants
                                )
                            ):

                                continue


                        except Exception:

                            pass


                filtered_jobs.append(
                    job
                )


            # =================================================
            # SUMMARY
            # =================================================

            st.divider()


            m1, m2, m3 = st.columns(3)


            if st.session_state.get(
                "search_mode_used"
            ) == "smart":

                first_metric_label = (
                    "Unique jobs found"
                )

            else:

                first_metric_label = (
                    "Upwork matches"
                )


            m1.metric(
                first_metric_label,
                st.session_state.get(
                    "live_total_count",
                    0
                )
            )


            m2.metric(
                "Loaded",
                len(
                    live_jobs
                )
            )


            m3.metric(
                "Worth reviewing",
                len(
                    filtered_jobs
                )
            )


            st.caption(
                "Quick Fit is a free local pre-filter. "
                "Opportunity Score uses AI."
            )


            # =================================================
            # ANALYZE TOP JOBS
            # =================================================

            st.divider()


            st.markdown(
                "## 🧠 AI Opportunity Ranking"
            )


            ai1, ai2 = st.columns(
                [1, 3]
            )


            with ai1:

                analyze_top_n = (
                    st.selectbox(
                        "Analyze top",
                        [
                            3,
                            5,
                            10,
                            15
                        ],
                        index=3
                    )
                )


            with ai2:

                st.info(
                    "AI will analyze the strongest "
                    "Quick Fit jobs and calculate "
                    "their Opportunity Score."
                )


            strong_opportunity_threshold = st.slider(
                "Minimum Opportunity Score for Daily Best Jobs",
                min_value=65,
                max_value=95,
                value=80,
                step=1,
                help=(
                    "Only AI-analyzed jobs at or above this score "
                    "will be shown in Daily Best Jobs."
                )
            )


            if st.button(
                "🧠 Analyze Top Jobs",
                type="primary",
                use_container_width=True
            ):

                jobs_to_analyze = (
                    filtered_jobs[
                        :analyze_top_n
                    ]
                )


                if not jobs_to_analyze:

                    st.warning(
                        "No jobs available after filtering."
                    )


                else:

                    progress = st.progress(
                        0
                    )

                    status_text = st.empty()

                    analyzed_jobs = []


                    for i, job in enumerate(
                        jobs_to_analyze
                    ):

                        status_text.write(
                            f"Analyzing "
                            f"{i + 1}/"
                            f"{len(jobs_to_analyze)}: "
                            f"{job['title']}"
                        )


                        try:

                            result = (
                                analyze_job_with_ai(
                                    job
                                )
                            )


                            analyzed_jobs.append(
                                result
                            )


                            single_key = (
                                job_state_key(
                                    job,
                                    i
                                )
                            )


                            if (
                                "single_job_analyses"
                                not in
                                st.session_state
                            ):

                                st.session_state[
                                    "single_job_analyses"
                                ] = {}


                            st.session_state[
                                "single_job_analyses"
                            ][
                                single_key
                            ] = result


                        except Exception as e:

                            st.warning(
                                f"Could not analyze: "
                                f"{job['title']}"
                            )

                            st.caption(
                                str(e)
                            )


                        progress.progress(
                            (
                                i + 1
                            )
                            /
                            len(
                                jobs_to_analyze
                            )
                        )


                    analyzed_jobs = sorted(
                        analyzed_jobs,
                        key=lambda x:
                            x[
                                "opportunity_score"
                            ],
                        reverse=True
                    )


                    st.session_state[
                        "top_job_analyses"
                    ] = analyzed_jobs


                    progress.empty()

                    status_text.empty()


                    st.success(
                        "✅ AI ranking complete!"
                    )


            # =================================================
            # TOP AI RESULTS
            # =================================================

            top_results = (
                st.session_state.get(
                    "top_job_analyses",
                    []
                )
            )


            if top_results:

                st.divider()


                strong_results = [
                    result
                    for result in top_results
                    if result.get(
                        "opportunity_score",
                        0
                    ) >= strong_opportunity_threshold
                ]


                st.markdown(
                    "## 🔥 Daily Best Jobs"
                )


                if strong_results:

                    st.success(
                        f"{len(strong_results)} strong opportunity"
                        f"{'y' if len(strong_results) == 1 else 'ies'} "
                        f"found with Opportunity Score ≥ "
                        f"{strong_opportunity_threshold}."
                    )

                    st.caption(
                        "Review these first. Lower-scoring AI analyses "
                        "are hidden from this shortlist."
                    )

                else:

                    best_score = max(
                        [
                            result.get(
                                "opportunity_score",
                                0
                            )
                            for result in top_results
                        ],
                        default=0
                    )

                    st.warning(
                        "No strong opportunities right now — "
                        "don't spend Connects."
                    )

                    st.caption(
                        f"Best analyzed job: {best_score}/100. "
                        f"Your Daily Best threshold is "
                        f"{strong_opportunity_threshold}/100."
                    )


                for rank, result in enumerate(
                    strong_results,
                    start=1
                ):

                    job = result[
                        "job"
                    ]


                    with st.container(
                        border=True
                    ):

                        r1, r2, r3 = st.columns(
                            [5, 1.3, 1.5]
                        )


                        with r1:

                            st.markdown(
                                f"### #{rank} "
                                f"{job['title']}"
                            )


                            info1, info2 = (
                                st.columns(2)
                            )


                            with info1:

                                st.write(
                                    "**Budget:**",
                                    job.get(
                                        "budget"
                                    )
                                    or
                                    "Unknown"
                                )


                                st.write(
                                    "**Applicants:**",
                                    job.get(
                                        "proposals"
                                    )
                                    if
                                    job.get(
                                        "proposals"
                                    )
                                    is not None
                                    else
                                    "Unknown"
                                )


                            with info2:

                                st.write(
                                    "**Client spent:**",
                                    job.get(
                                        "client_spent"
                                    )
                                    or
                                    "Unknown"
                                )


                                st.write(
                                    "**Client hires:**",
                                    job.get(
                                        "client_hires"
                                    )
                                    if
                                    job.get(
                                        "client_hires"
                                    )
                                    is not None
                                    else
                                    "Unknown"
                                )


                            st.write(
                                "**Category:**",
                                result.get(
                                    "category"
                                )
                            )


                            if result.get(
                                "recommended_bid"
                            ):

                                st.write(
                                    "**Recommended bid:**",
                                    result[
                                        "recommended_bid"
                                    ]
                                )


                        with r2:

                            st.metric(
                                "Opportunity",
                                (
                                    f"{result['opportunity_score']}"
                                    f"/100"
                                )
                            )


                            st.write(
                                result[
                                    "decision"
                                ]
                            )


                            st.caption(
                                f"Quick Fit: "
                                f"{job.get('quick_fit', 0)}/100"
                            )


                        with r3:

                            if st.button(
                                "📄 Open Full Analysis",
                                key=(
                                    f"open_top_"
                                    f"{rank}_"
                                    f"{job_state_key(job)}"
                                ),
                                use_container_width=True
                            ):

                                st.session_state[
                                    "selected_job"
                                ] = job


                                st.session_state[
                                    "load_job_into_analyzer"
                                ] = True


                                st.session_state[
                                    "pending_analysis_result"
                                ] = result


                                st.session_state[
                                    "selected_job_loaded_message"
                                ] = True


                                st.rerun()


            # =================================================
            # QUICK FIT RESULTS
            # =================================================

            st.divider()


            st.markdown(
                "## 📋 Quick Fit Results"
            )


            single_analyses = (
                st.session_state.setdefault(
                    "single_job_analyses",
                    {}
                )
            )


            if not filtered_jobs:

                st.info(
                    "No jobs match the current filters."
                )


            for index, job in enumerate(
                filtered_jobs
            ):

                current_key = (
                    job_state_key(
                        job,
                        index
                    )
                )


                with st.container(
                    border=True
                ):

                    c1, c2, c3 = st.columns(
                        [5, 1.2, 1.3]
                    )


                    # -----------------------------------------
                    # JOB INFORMATION
                    # -----------------------------------------

                    with c1:

                        st.subheader(
                            job[
                                "title"
                            ]
                        )


                        info1, info2 = (
                            st.columns(2)
                        )


                        with info1:

                            st.write(
                                "**Budget:**",
                                job.get(
                                    "budget"
                                )
                                or
                                "Unknown"
                            )


                            st.write(
                                "**Applicants:**",
                                job.get(
                                    "proposals"
                                )
                                if
                                job.get(
                                    "proposals"
                                )
                                is not None
                                else
                                "Unknown"
                            )


                            if job.get(
                                "experience_level"
                            ):

                                st.write(
                                    "**Experience:**",
                                    job[
                                        "experience_level"
                                    ]
                                )


                        with info2:

                            st.write(
                                "**Client spent:**",
                                job.get(
                                    "client_spent"
                                )
                                or
                                "Unknown"
                            )


                            st.write(
                                "**Client hires:**",
                                job.get(
                                    "client_hires"
                                )
                                if
                                job.get(
                                    "client_hires"
                                )
                                is not None
                                else
                                "Unknown"
                            )


                            st.write(
                                "**Client rating:**",
                                job.get(
                                    "client_rating"
                                )
                                if
                                job.get(
                                    "client_rating"
                                )
                                is not None
                                else
                                "Unknown"
                            )


                        if job.get(
                            "skills"
                        ):

                            st.caption(
                                "Skills: "
                                + ", ".join(
                                    job[
                                        "skills"
                                    ][:10]
                                )
                            )


                        description = (
                            job.get(
                                "description"
                            )
                            or ""
                        )


                        if len(
                            description
                        ) > 350:

                            description = (
                                description[
                                    :350
                                ]
                                + "..."
                            )


                        st.write(
                            description
                        )


                    # -----------------------------------------
                    # QUICK FIT
                    # -----------------------------------------

                    with c2:

                        st.metric(
                            "Quick Fit",
                            (
                                f"{job['quick_fit']}"
                                f"/100"
                            )
                        )


                        st.write(
                            quick_fit_label(
                                job[
                                    "quick_fit"
                                ]
                            )
                        )


                    # -----------------------------------------
                    # ANALYZE BUTTON
                    # -----------------------------------------

                    with c3:

                        if st.button(
                            "🎯 Analyze",
                            key=(
                                f"single_analyze_"
                                f"{current_key}"
                            ),
                            type="secondary",
                            use_container_width=True
                        ):

                            with st.spinner(
                                "AI is analyzing this job..."
                            ):

                                try:

                                    single_result = (
                                        analyze_job_with_ai(
                                            job
                                        )
                                    )


                                    st.session_state[
                                        "single_job_analyses"
                                    ][
                                        current_key
                                    ] = single_result


                                    single_analyses[
                                        current_key
                                    ] = single_result


                                except Exception as e:

                                    st.error(
                                        "AI analysis failed."
                                    )

                                    st.code(
                                        str(e)
                                    )


                    # =================================================
                    # INLINE AI RESULT
                    # =================================================

                    current_result = (
                        st.session_state.get(
                            "single_job_analyses",
                            {}
                        ).get(
                            current_key
                        )
                    )


                    if current_result:

                        st.divider()


                        st.markdown(
                            "### 🤖 AI Opportunity Analysis"
                        )


                        a1, a2, a3, a4 = (
                            st.columns(
                                [1, 1, 1.5, 1.5]
                            )
                        )


                        with a1:

                            st.metric(
                                "Opportunity",
                                (
                                    f"{current_result['opportunity_score']}"
                                    f"/100"
                                )
                            )


                        with a2:

                            st.metric(
                                "Win Probability",
                                (
                                    f"{current_result['win_probability']}"
                                    f"/100"
                                )
                            )


                        with a3:

                            st.markdown(
                                "#### Decision"
                            )

                            st.markdown(
                                f"### "
                                f"{current_result['decision']}"
                            )


                        with a4:

                            if current_result.get(
                                "recommended_bid"
                            ):

                                st.markdown(
                                    "**Recommended bid**"
                                )

                                st.write(
                                    current_result[
                                        "recommended_bid"
                                    ]
                                )


                        b1, b2, b3 = (
                            st.columns(3)
                        )


                        b1.metric(
                            "Skill Match",
                            (
                                f"{current_result['skill_match']}"
                                f"/100"
                            )
                        )


                        b2.metric(
                            "Client Quality",
                            (
                                f"{current_result['client_quality']}"
                                f"/100"
                            )
                        )


                        b3.metric(
                            "Budget Quality",
                            (
                                f"{current_result['budget_quality']}"
                                f"/100"
                            )
                        )


                        st.write(
                            "**Category:**",
                            current_result.get(
                                "category"
                            )
                        )


                        open_col1, open_col2 = (
                            st.columns(
                                [1, 3]
                            )
                        )


                        with open_col1:

                            if st.button(
                                "📄 Open Full Analysis",
                                key=(
                                    f"open_single_"
                                    f"{current_key}"
                                ),
                                use_container_width=True
                            ):

                                st.session_state[
                                    "selected_job"
                                ] = job


                                st.session_state[
                                    "load_job_into_analyzer"
                                ] = True


                                st.session_state[
                                    "pending_analysis_result"
                                ] = current_result


                                st.session_state[
                                    "selected_job_loaded_message"
                                ] = True


                                st.rerun()


                        with open_col2:

                            st.caption(
                                "Full Analysis includes risks, "
                                "portfolio recommendations, "
                                "application strategy and proposal."
                            )


# =====================================================
# TAB 3 — JOB HISTORY
# =====================================================

with tab3:

    st.subheader(
        "📊 Job History"
    )


    try:

        response = (
            supabase
            .table(
                "jobs"
            )
            .select(
                "*"
            )
            .order(
                "created_at",
                desc=True
            )
            .execute()
        )


        jobs = response.data


        if not jobs:

            st.info(
                "No jobs saved yet."
            )


        else:

            total_jobs = len(
                jobs
            )


            applied = len([
                j
                for j in jobs
                if j.get(
                    "status"
                )
                in [
                    "Applied",
                    "Interview",
                    "Hired"
                ]
            ])


            interviews = len([
                j
                for j in jobs
                if j.get(
                    "status"
                )
                in [
                    "Interview",
                    "Hired"
                ]
            ])


            hired = len([
                j
                for j in jobs
                if j.get(
                    "status"
                )
                ==
                "Hired"
            ])


            total_revenue = sum([
                float(
                    j.get(
                        "contract_value"
                    )
                    or 0
                )
                for j in jobs
                if j.get(
                    "status"
                )
                ==
                "Hired"
            ])


            m1, m2, m3, m4, m5 = (
                st.columns(5)
            )


            m1.metric(
                "Analyzed",
                total_jobs
            )


            m2.metric(
                "Applied",
                applied
            )


            m3.metric(
                "Interviews",
                interviews
            )


            m4.metric(
                "Hired",
                hired
            )


            m5.metric(
                "Contract Value",
                f"${total_revenue:,.0f}"
            )


            if applied > 0:

                r1, r2 = (
                    st.columns(2)
                )


                r1.metric(
                    "Interview Rate",
                    (
                        f"{interviews / applied * 100:.1f}%"
                    )
                )


                r2.metric(
                    "Hire Rate",
                    (
                        f"{hired / applied * 100:.1f}%"
                    )
                )


            st.divider()


            st.subheader(
                "📋 Saved Opportunities"
            )


            for job in jobs:

                title = (
                    job.get(
                        "job_title"
                    )
                    or
                    "Untitled Job"
                )


                score = (
                    job.get(
                        "opportunity_score"
                    )
                    or
                    "—"
                )


                current_status = (
                    job.get(
                        "status"
                    )
                    or
                    "Not applied"
                )


                category = (
                    job.get(
                        "category"
                    )
                    or
                    "Uncategorized"
                )


                with st.expander(
                    f"{title} | "
                    f"{category} | "
                    f"Score: {score} | "
                    f"{current_status}"
                ):

                    c1, c2, c3 = (
                        st.columns(3)
                    )


                    c1.metric(
                        "Opportunity Score",
                        job.get(
                            "opportunity_score"
                        )
                        or
                        "—"
                    )


                    c2.metric(
                        "Skill Match",
                        job.get(
                            "skill_match"
                        )
                        or
                        "—"
                    )


                    c3.metric(
                        "Win Probability",
                        job.get(
                            "win_probability"
                        )
                        or
                        "—"
                    )


                    statuses = [
                        "Not applied",
                        "Applied",
                        "Interview",
                        "Hired",
                        "Rejected"
                    ]


                    if (
                        current_status
                        not in statuses
                    ):

                        current_status = (
                            "Not applied"
                        )


                    new_status = (
                        st.selectbox(
                            "Update status",
                            statuses,
                            index=(
                                statuses.index(
                                    current_status
                                )
                            ),
                            key=(
                                f"status_"
                                f"{job['id']}"
                            )
                        )
                    )


                    new_value = (
                        st.number_input(
                            "Contract value ($)",
                            min_value=0.0,
                            value=float(
                                job.get(
                                    "contract_value"
                                )
                                or 0
                            ),
                            step=50.0,
                            key=(
                                f"value_"
                                f"{job['id']}"
                            )
                        )
                    )


                    if st.button(
                        "Update",
                        key=(
                            f"update_"
                            f"{job['id']}"
                        )
                    ):

                        try:

                            (
                                supabase
                                .table(
                                    "jobs"
                                )
                                .update({
                                    "status":
                                        new_status,

                                    "contract_value":
                                        new_value
                                })
                                .eq(
                                    "id",
                                    job[
                                        "id"
                                    ]
                                )
                                .execute()
                            )


                            st.success(
                                "✅ Updated!"
                            )


                            st.rerun()


                        except Exception as e:

                            st.error(
                                "Could not update."
                            )

                            st.code(
                                str(e)
                            )


    except Exception as e:

        st.error(
            "Could not load Job History."
        )

        st.code(
            str(e)
        )

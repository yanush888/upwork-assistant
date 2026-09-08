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


def extract_number(text, label):
    pattern = rf"{re.escape(label)}:\s*(\d+)"

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    value = int(match.group(1))

    return max(
        0,
        min(100, value)
    )


def extract_text_value(text, label):
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


def safe_score(value, fallback=50):
    if value is None:
        return fallback

    return max(
        0,
        min(100, value)
    )


def money_number(money):
    """
    Converts Upwork Money into float.
    """
    if not money:
        return None

    value = money.get("displayValue")

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

    value = money.get("displayValue")
    currency = money.get("currency")

    if value in [None, ""]:
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
        formatted = str(value)

    if currency:
        return f"${formatted} {currency}"

    return f"${formatted}"


# =====================================================
# FINAL SCORING
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

    if deal_breaker:
        score = min(
            score,
            59
        )

    if win_probability < 35:
        score = min(
            score,
            64
        )

    return score


def decision_from_score(score):
    if score >= 90:
        return "🔥 APPLY NOW"

    if score >= 80:
        return "🟢 APPLY"

    if score >= 65:
        return "🟡 MAYBE"

    return "🔴 SKIP"


# =====================================================
# UPWORK OAUTH
# =====================================================

def build_upwork_auth_url():
    params = {
        "response_type": "code",
        "client_id": upwork_client_id,
        "redirect_uri": upwork_redirect_uri
    }

    return (
        UPWORK_AUTH_URL
        + "?"
        + urlencode(params)
    )


def exchange_upwork_code(code):
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

    oauth_code = st.query_params.get(
        "code"
    )

    if (
        oauth_code
        and
        "UPWORK_ACCESS_TOKEN"
        not in st.session_state
    ):
        try:
            token_data = exchange_upwork_code(
                oauth_code
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

            st.code(str(e))


# =====================================================
# GRAPHQL
# =====================================================

def upwork_graphql(
    query,
    variables=None
):
    token = st.session_state.get(
        "UPWORK_ACCESS_TOKEN"
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
            "query": query,
            "variables": variables or {}
        },
        timeout=30
    )

    response.raise_for_status()

    payload = response.json()

    if payload.get("errors"):
        raise Exception(
            str(payload["errors"])
        )

    return payload.get(
        "data",
        {}
    )


# =====================================================
# LIVE UPWORK SEARCH
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
                "after": "0",
                "first": first
            }
        }
    }

    data = upwork_graphql(
        query,
        variables
    )

    result = data.get(
        "marketplaceJobPostingsSearch",
        {}
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
# BUDGET PARSING
# =====================================================

def parse_budget(node):
    hourly_min_money = node.get(
        "hourlyBudgetMin"
    )

    hourly_max_money = node.get(
        "hourlyBudgetMax"
    )

    fixed_money = node.get(
        "amount"
    )

    hourly_min = money_number(
        hourly_min_money
    )

    hourly_max = money_number(
        hourly_max_money
    )

    fixed_amount = money_number(
        fixed_money
    )

    hourly_type = node.get(
        "hourlyBudgetType"
    )

    # ---------------------------------------------
    # HOURLY
    # ---------------------------------------------

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
            "type": "hourly",
            "text": text,
            "hourly_min": hourly_min,
            "hourly_max": hourly_max,
            "fixed": None
        }

    # ---------------------------------------------
    # HOURLY BUT CLIENT DID NOT ENTER BUDGET
    # ---------------------------------------------

    if hourly_type == "NOT_PROVIDED":

        return {
            "type": "hourly",
            "text":
                "Hourly — budget not specified",

            "hourly_min": None,
            "hourly_max": None,
            "fixed": None
        }

    # ---------------------------------------------
    # FIXED
    # ---------------------------------------------

    if (
        fixed_amount
        and fixed_amount > 0
    ):

        return {
            "type": "fixed",
            "text":
                f"${fixed_amount:g} fixed",

            "hourly_min": None,
            "hourly_max": None,
            "fixed": fixed_amount
        }

    # ---------------------------------------------
    # UNKNOWN
    # ---------------------------------------------

    return {
        "type": "unknown",
        "text":
            "Budget not specified",

        "hourly_min": None,
        "hourly_max": None,
        "fixed": None
    }


# =====================================================
# FORMAT LIVE JOB
# =====================================================

def format_upwork_job(node):

    client = (
        node.get("client")
        or {}
    )

    location = (
        client.get("location")
        or {}
    )

    budget_info = parse_budget(
        node
    )


    location_parts = [
        location.get("city"),
        location.get("country")
    ]

    location_text = ", ".join([
        x
        for x in location_parts
        if x
    ])


    skills = []

    for skill in (
        node.get("skills")
        or []
    ):

        name = (
            skill.get("prettyName")
            or
            skill.get("name")
        )

        if name:
            skills.append(name)


    return {
        "id":
            node.get("id", ""),

        "title":
            node.get("title", ""),

        "description":
            node.get(
                "description",
                ""
            ),

        "url":
            "",

        "budget":
            budget_info["text"],

        "budget_type":
            budget_info["type"],

        "hourly_min":
            budget_info[
                "hourly_min"
            ],

        "hourly_max":
            budget_info[
                "hourly_max"
            ],

        "fixed_budget":
            budget_info["fixed"],

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
# QUICK FIT PRE-FILTER
# =====================================================

STRONG_KEYWORDS = [
    "photoshop",
    "retouch",
    "retouching",
    "photo editing",
    "image editing",
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
    """
    Cheap local heuristic.
    No OpenAI call.
    Used only to prioritize which jobs deserve AI analysis.
    """

    score = 0

    text = (
        (
            job.get("title", "")
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


    # ---------------------------------------------
    # SKILL RELEVANCE — MAX 40
    # ---------------------------------------------

    matches = sum(
        1
        for keyword in STRONG_KEYWORDS
        if keyword in text
    )

    score += min(
        matches * 8,
        40
    )


    # ---------------------------------------------
    # BUDGET — MAX 25
    # ---------------------------------------------

    if (
        job.get("budget_type")
        == "hourly"
    ):

        hourly_max = job.get(
            "hourly_max"
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
        job.get("budget_type")
        == "fixed"
    ):

        fixed = job.get(
            "fixed_budget"
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


    # ---------------------------------------------
    # CLIENT — MAX 20
    # ---------------------------------------------

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


    # ---------------------------------------------
    # COMPETITION — MAX 15
    # ---------------------------------------------

    applicants = job.get(
        "proposals"
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


    # ---------------------------------------------
    # PAYMENT VERIFICATION BONUS
    # ---------------------------------------------

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
# PREFILL ANALYZER
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
        ] = str(value)

    st.session_state[
        "load_job_into_analyzer"
    ] = False


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
    1. Search live jobs
    2. Quick Fit removes noise
    3. Analyze strongest jobs
    4. Decide APPLY / SKIP
    5. Generate proposal
    6. Save result
    7. Track Interview / Hired
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
            "✅ Job loaded from Find Jobs. "
            "Review it and click Analyze Job."
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

        unanswered_invites = st.text_input(
            "Unanswered invites",
            key="unanswered_invites_input"
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

        client_active_hires = st.text_input(
            "Active hires",
            key="active_hires_input"
        )


    with c6:

        client_hours = st.text_input(
            "Hours billed",
            key="hours_billed_input"
        )


    with c7:

        client_member_since = st.text_input(
            "Member since",
            key="member_since_input"
        )


    with c8:

        project_length = st.text_input(
            "Project length",
            key="project_length_input"
        )


    st.info(
        f"Your target hourly rate: "
        f"${TARGET_HOURLY_RATE}/hr."
    )


    # =================================================
    # AI ANALYSIS
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

            with st.spinner(
                "Analyzing opportunity..."
            ):

                prompt = f"""
You are a senior Upwork business opportunity analyst.

Determine whether applying is a smart use
of this freelancer's time and Upwork Connects.

FREELANCER PROFILE:

- Top Rated
- 100% Job Success
- Amazon Listing Images Expert
- High-End Photo Retoucher
- Photoshop Expert
- AI Image Specialist
- E-commerce Image Specialist

Strong skills:

- Amazon listing images
- product retouching
- e-commerce product imagery
- Photoshop compositing
- AI + Photoshop
- photorealistic AI images
- product replacement
- lifestyle integration
- background replacement
- maintaining exact product geometry
- interior manipulation
- architectural editing
- portrait retouching

TARGET HOURLY RATE:
${TARGET_HOURLY_RATE}/hr


IMPORTANT:

Skill Match and Opportunity Score
are NOT the same thing.

For hourly jobs, evaluate whether
${TARGET_HOURLY_RATE}/hr fits inside
the client's range.

Do NOT punish a $15-$35/hr job
as though it paid $15/hr.

For fixed jobs, compare realistic workload
to the stated fixed budget.

Example:
71 precision images for $100
should receive Budget Quality around 0-10
and usually DEAL BREAKER YES.


Score:

SKILL MATCH: 0-100
CLIENT QUALITY: 0-100
BUDGET QUALITY: 0-100
COMPETITION SCORE: 0-100
WIN PROBABILITY: 0-100

Competition:
100 = favorable.
0 = extremely unfavorable.

DEAL BREAKER:
YES only for a serious reason not to apply.


JOB:

TITLE:
{clean_value(job_title)}

DESCRIPTION:
{job_description}

BUDGET:
{clean_value(budget)}

APPLICANTS:
{clean_value(proposals)}

INTERVIEWING:
{clean_value(interviewing)}

INVITES:
{clean_value(invites)}

POSTED:
{clean_value(posted)}

PROJECT LENGTH:
{clean_value(project_length)}


CLIENT:

SPENT:
{clean_value(client_spent)}

HIRES:
{clean_value(client_hires)}

RATING:
{clean_value(client_rating)}

LOCATION:
{clean_value(client_location)}

MEMBER SINCE:
{clean_value(client_member_since)}


RETURN EXACTLY:

CATEGORY: Amazon or Product Retouching or AI + Photoshop or Interior / Architecture or Portrait or Other

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
One concise recommendation.

PORTFOLIO TO SHOW:
1. example
2. example
3. example

APPLICATION STRATEGY:
- recommendation
- recommendation

PROPOSAL:
Write a personalized proposal
of approximately 100-140 words.

Do not start with:
"I am excited to apply."

Start with the client's actual problem.
"""

                try:

                    response = (
                        openai_client
                        .responses
                        .create(
                            model="gpt-5-mini",
                            input=prompt
                        )
                    )

                    analysis = (
                        response.output_text
                    )


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
                        ).upper()
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


                    proposal = (
                        extract_section(
                            analysis,
                            "PROPOSAL"
                        )
                    )


                    st.session_state[
                        "analysis"
                    ] = analysis

                    st.session_state[
                        "opportunity_score"
                    ] = opportunity_score

                    st.session_state[
                        "decision"
                    ] = decision

                    st.session_state[
                        "skill_match"
                    ] = skill_match

                    st.session_state[
                        "client_quality"
                    ] = client_quality

                    st.session_state[
                        "budget_quality"
                    ] = budget_quality

                    st.session_state[
                        "competition_score"
                    ] = competition_score

                    st.session_state[
                        "win_probability"
                    ] = win_probability

                    st.session_state[
                        "category"
                    ] = category

                    st.session_state[
                        "proposal"
                    ] = proposal

                    st.session_state[
                        "job_title"
                    ] = job_title

                    st.session_state[
                        "job_url"
                    ] = job_url

                    st.session_state[
                        "job_description"
                    ] = job_description


                except Exception as e:

                    st.error(
                        "AI analysis failed."
                    )

                    st.code(str(e))


    # =================================================
    # DISPLAY ANALYSIS
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
                    .table("jobs")
                    .insert(data)
                    .execute()
                )


                st.success(
                    "✅ Job saved!"
                )


            except Exception as e:

                st.error(
                    "Could not save job."
                )

                st.code(str(e))


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


        s1, s2 = st.columns(
            [4, 1]
        )


        with s1:

            search_expression = (
                st.text_input(
                    "Search Upwork",
                    value="photo editing retouching"
                )
            )


        with s2:

            results_count = (
                st.selectbox(
                    "Results",
                    [
                        10,
                        20,
                        50
                    ],
                    index=1
                )
            )


        # =================================================
        # SEARCH
        # =================================================

        if st.button(
            "🔎 Search Upwork",
            type="primary",
            use_container_width=True
        ):

            if not search_expression.strip():

                st.warning(
                    "Enter a search phrase."
                )

            else:

                with st.spinner(
                    "Searching Upwork..."
                ):

                    try:

                        total_count, edges = (
                            search_upwork_jobs(
                                search_expression,
                                results_count
                            )
                        )


                        live_jobs = []


                        for edge in edges:

                            node = (
                                edge.get(
                                    "node"
                                )
                                or {}
                            )


                            job = (
                                format_upwork_job(
                                    node
                                )
                            )


                            job[
                                "quick_fit"
                            ] = (
                                calculate_quick_fit(
                                    job
                                )
                            )


                            live_jobs.append(
                                job
                            )


                        live_jobs = sorted(
                            live_jobs,
                            key=lambda x:
                                x[
                                    "quick_fit"
                                ],
                            reverse=True
                        )


                        st.session_state[
                            "live_jobs"
                        ] = live_jobs


                        st.session_state[
                            "live_total_count"
                        ] = total_count


                    except Exception as e:

                        st.error(
                            "Upwork search failed."
                        )

                        st.code(str(e))


        # =================================================
        # FILTERS
        # =================================================

        live_jobs = (
            st.session_state.get(
                "live_jobs",
                []
            )
        )


        if live_jobs:

            st.divider()

            st.markdown(
                "### 🎚️ Quick Filter"
            )


            f1, f2, f3 = (
                st.columns(3)
            )


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
                    job["quick_fit"]
                    <
                    minimum_quick_fit
                ):
                    continue


                if hide_low_hourly:

                    if (
                        job[
                            "budget_type"
                        ]
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

                    if (
                        applicants
                        is not None
                    ):

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


            m1, m2, m3 = (
                st.columns(3)
            )


            m1.metric(
                "Upwork matches",
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
                "Quick Fit is a local pre-filter. "
                "It does not use OpenAI and does not "
                "replace the full Opportunity Score."
            )


            st.divider()


            # =================================================
            # JOB CARDS
            # =================================================

            if not filtered_jobs:

                st.info(
                    "No jobs match the current filters. "
                    "Try lowering Minimum Quick Fit."
                )


            for index, job in enumerate(
                filtered_jobs
            ):

                with st.container(
                    border=True
                ):

                    c1, c2, c3 = (
                        st.columns(
                            [5, 1, 1]
                        )
                    )


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
                                job[
                                    "budget"
                                ]
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
                                "payment_verified"
                            ):

                                st.caption(
                                    "✅ Payment verified"
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
                        ) > 420:

                            description = (
                                description[
                                    :420
                                ]
                                + "..."
                            )


                        st.write(
                            description
                        )


                    with c2:

                        st.metric(
                            "Quick Fit",
                            f"{job['quick_fit']}/100"
                        )

                        st.write(
                            quick_fit_label(
                                job[
                                    "quick_fit"
                                ]
                            )
                        )


                    with c3:

                        st.write("")

                        st.write("")

                        if st.button(
                            "🎯 Analyze",
                            key=(
                                f"live_analyze_"
                                f"{index}_"
                                f"{job.get('id')}"
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
                                "selected_job_loaded_message"
                            ] = True


                            st.rerun()


# =====================================================
# TAB 3 — HISTORY
# =====================================================

with tab3:

    st.subheader(
        "📊 Job History"
    )


    try:

        response = (
            supabase
            .table("jobs")
            .select("*")
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


            m1, m2, m3, m4 = (
                st.columns(4)
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


            st.divider()


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


                with st.expander(
                    f"{title} | "
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


                    new_status = st.selectbox(
                        "Update status",
                        statuses,
                        index=statuses.index(
                            current_status
                        ),
                        key=(
                            f"status_"
                            f"{job['id']}"
                        )
                    )


                    new_value = st.number_input(
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
                                .table("jobs")
                                .update({
                                    "status":
                                        new_status,

                                    "contract_value":
                                        new_value
                                })
                                .eq(
                                    "id",
                                    job["id"]
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

                            st.code(str(e))


    except Exception as e:

        st.error(
            "Could not load Job History."
        )

        st.code(str(e))

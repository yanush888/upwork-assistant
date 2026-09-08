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
# GENERAL HELPERS
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

    if match:

        value = int(
            match.group(1)
        )

        return max(
            0,
            min(100, value)
        )

    return None


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


def money_display(money):

    if not money:
        return ""

    display_value = money.get(
        "displayValue"
    )

    currency = money.get(
        "currency"
    )

    if display_value:

        if currency:
            return f"{display_value} {currency}"

        return str(
            display_value
        )

    return ""


# =====================================================
# SCORING
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

    score = (
        skill_match * 0.25
        + client_quality * 0.20
        + budget_quality * 0.20
        + competition_score * 0.15
        + win_probability * 0.20
    )

    score = round(
        score
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
# HANDLE OAUTH CALLBACK
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

            st.code(
                str(e)
            )


# =====================================================
# UPWORK GRAPHQL
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
                payload["errors"]
            )
        )

    return payload.get(
        "data",
        {}
    )


def search_upwork_jobs(
    search_expression,
    first=10
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

                    createdDateTime
                    publishedDateTime

                    skills {
                        name
                        prettyName
                    }

                    client {
                        totalHires
                        totalPostedJobs

                        totalSpent {
                            displayValue
                            currency
                        }

                        totalReviews
                        totalFeedback
                        memberSinceDateTime
                        hasFinancialPrivacy

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

    results = (
        data
        .get(
            "marketplaceJobPostingsSearch",
            {}
        )
    )

    return (
        results.get(
            "totalCount",
            0
        ),
        results.get(
            "edges",
            []
        )
    )


# =====================================================
# FORMAT LIVE UPWORK JOB
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

    hourly_min = money_display(
        node.get(
            "hourlyBudgetMin"
        )
    )

    hourly_max = money_display(
        node.get(
            "hourlyBudgetMax"
        )
    )

    fixed_amount = money_display(
        node.get(
            "amount"
        )
    )


    # ---------------------------------------------
    # BUDGET
    # ---------------------------------------------

    if hourly_min or hourly_max:

        if hourly_min and hourly_max:

            budget = (
                f"{hourly_min} - "
                f"{hourly_max} / hr"
            )

        elif hourly_max:

            budget = (
                f"Up to {hourly_max} / hr"
            )

        else:

            budget = (
                f"{hourly_min} / hr"
            )

    else:

        budget = fixed_amount


    # ---------------------------------------------
    # LOCATION
    # ---------------------------------------------

    location_parts = [
        location.get(
            "city"
        ),
        location.get(
            "country"
        )
    ]

    location_text = ", ".join([
        part
        for part in location_parts
        if part
    ])


    # ---------------------------------------------
    # SKILLS
    # ---------------------------------------------

    skills = []

    for skill in (
        node.get(
            "skills"
        )
        or []
    ):

        skill_name = (
            skill.get(
                "prettyName"
            )
            or
            skill.get(
                "name"
            )
        )

        if skill_name:

            skills.append(
                skill_name
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
            budget,

        "proposals":
            str(
                node.get(
                    "totalApplicants",
                    ""
                )
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

        "client_hires":
            str(
                client.get(
                    "totalHires",
                    ""
                )
            ),

        "client_rating":
            str(
                client.get(
                    "totalFeedback",
                    ""
                )
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
            )
    }


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

        st.session_state[
            session_key
        ] = selected_job.get(
            job_key,
            ""
        )

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
    1. Search live Upwork jobs
    2. Open a promising job
    3. Analyze opportunity
    4. Decide APPLY or SKIP
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
# TAB 1 — ANALYZE
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
            "Proposals / Applicants",
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
        f"Target rate: ${TARGET_HOURLY_RATE}/hr."
    )


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

Evaluate whether applying to this job is a smart
use of time and Upwork Connects.

FREELANCER:

- Top Rated
- 100% Job Success
- Amazon Listing Images Expert
- High-End Photo Retoucher
- Photoshop Expert
- AI Image Specialist
- E-commerce Image Specialist

Strongest skills:

- Amazon listing images
- e-commerce product imagery
- product retouching
- high-end Photoshop
- AI + Photoshop
- photorealistic compositing
- product replacement
- lifestyle product integration
- preserving product geometry
- interior manipulation
- architectural editing
- portrait retouching

TARGET RATE:
${TARGET_HOURLY_RATE}/hour

IMPORTANT BUDGET RULE:

For hourly jobs, judge whether
${TARGET_HOURLY_RATE}/hour fits inside
the client's range.

Do NOT judge an hourly range only
by its minimum.

Examples:

$15-$35/hr:
reasonable because freelancer can bid $35.

$25-$50/hr:
good.

$10-$25/hr:
weak.

For fixed-price jobs, compare scope,
complexity and likely hours to the budget.

71 complex images for $100:
Budget Quality approximately 0-10
and normally a deal breaker.


SCORING:

SKILL MATCH:
0-100

CLIENT QUALITY:
0-100

BUDGET QUALITY:
0-100

COMPETITION SCORE:
0-100

100 = favorable competition.

WIN PROBABILITY:
0-100

DEAL BREAKER:
YES only for a serious reason to avoid applying.


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
Write a personalized Upwork proposal
of approximately 100-140 words.

Never start with "I am excited to apply."
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
                        deal_breaker_text.startswith(
                            "YES"
                        )
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

                    category = extract_text_value(
                        analysis,
                        "CATEGORY"
                    )

                    proposal = extract_section(
                        analysis,
                        "PROPOSAL"
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

                    st.code(
                        str(e)
                    )


    if "analysis" in st.session_state:

        st.divider()

        st.subheader(
            "📈 Opportunity Overview"
        )


        score = st.session_state.get(
            "opportunity_score"
        )

        decision = st.session_state.get(
            "decision"
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

                st.code(
                    str(e)
                )


# =====================================================
# TAB 2 — LIVE FIND JOBS
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


        search_col1, search_col2 = (
            st.columns(
                [4, 1]
            )
        )


        with search_col1:

            search_expression = (
                st.text_input(
                    "Search Upwork",
                    value="photo retouching",
                    placeholder=(
                        "photo retouching"
                    )
                )
            )


        with search_col2:

            results_count = (
                st.selectbox(
                    "Results",
                    [
                        5,
                        10,
                        20
                    ],
                    index=1
                )
            )


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

                            live_jobs.append(
                                format_upwork_job(
                                    node
                                )
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

                        st.code(
                            str(e)
                        )


        live_jobs = (
            st.session_state.get(
                "live_jobs",
                []
            )
        )


        if live_jobs:

            st.divider()


            st.metric(
                "Jobs found by Upwork",
                st.session_state.get(
                    "live_total_count",
                    len(live_jobs)
                )
            )


            st.caption(
                f"Showing the newest "
                f"{len(live_jobs)} results."
            )


            for index, job in enumerate(
                live_jobs
            ):

                with st.container(
                    border=True
                ):

                    col1, col2 = (
                        st.columns(
                            [5, 1]
                        )
                    )


                    with col1:

                        st.subheader(
                            job["title"]
                        )

                        if job["budget"]:

                            st.write(
                                "**Budget:**",
                                job["budget"]
                            )


                        if job[
                            "client_spent"
                        ]:

                            st.write(
                                "**Client spent:**",
                                job[
                                    "client_spent"
                                ]
                            )


                        if job[
                            "client_hires"
                        ]:

                            st.write(
                                "**Client hires:**",
                                job[
                                    "client_hires"
                                ]
                            )


                        if job[
                            "client_rating"
                        ]:

                            st.write(
                                "**Client rating:**",
                                job[
                                    "client_rating"
                                ]
                            )


                        if job[
                            "client_location"
                        ]:

                            st.write(
                                "**Location:**",
                                job[
                                    "client_location"
                                ]
                            )


                        if job[
                            "proposals"
                        ]:

                            st.write(
                                "**Applicants:**",
                                job[
                                    "proposals"
                                ]
                            )


                        if job[
                            "skills"
                        ]:

                            st.caption(
                                "Skills: "
                                + ", ".join(
                                    job[
                                        "skills"
                                    ][:8]
                                )
                            )


                        description = (
                            job[
                                "description"
                            ]
                            or ""
                        )

                        if len(
                            description
                        ) > 450:

                            description = (
                                description[
                                    :450
                                ]
                                + "..."
                            )

                        st.write(
                            description
                        )


                    with col2:

                        st.write("")

                        st.write("")

                        if st.button(
                            "🎯 Analyze",
                            key=(
                                f"live_analyze_"
                                f"{index}"
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
                if j.get("status")
                in [
                    "Applied",
                    "Interview",
                    "Hired"
                ]
            ])

            interviews = len([
                j
                for j in jobs
                if j.get("status")
                in [
                    "Interview",
                    "Hired"
                ]
            ])

            hired = len([
                j
                for j in jobs
                if j.get("status")
                == "Hired"
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

                status = (
                    job.get(
                        "status"
                    )
                    or
                    "Not applied"
                )


                with st.expander(
                    f"{title} | "
                    f"Score: {score} | "
                    f"{status}"
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


                    if status not in statuses:

                        status = (
                            "Not applied"
                        )


                    new_status = st.selectbox(
                        "Update status",
                        statuses,
                        index=statuses.index(
                            status
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
            "Could not load Job History."
        )

        st.code(
            str(e)
        )

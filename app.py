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

# Your preferred sustainable rate.
# Later we can make this editable in Settings.
TARGET_HOURLY_RATE = 35


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
# UPWORK API SETTINGS
# =====================================================

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
# HELPER FUNCTIONS
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


# =====================================================
# FINAL OPPORTUNITY SCORE
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

    score = round(score)

    # ---------------------------------------------
    # BUSINESS SAFETY CAPS
    # ---------------------------------------------

    # Terrible budget should never become APPLY.
    if budget_quality <= 15:
        score = min(
            score,
            59
        )

    # Weak budget should not easily become strong APPLY.
    elif budget_quality <= 30:
        score = min(
            score,
            69
        )

    # Major deal breaker = SKIP.
    if deal_breaker:
        score = min(
            score,
            59
        )

    # Very low probability of winning
    # should stop a job becoming APPLY.
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
# PREFILL FROM FIND JOBS
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
            "⏳ Waiting for Upwork API approval"
        )

        st.caption(
            "Manual job analysis remains available."
        )

    elif not all([
        upwork_client_id,
        upwork_client_secret,
        upwork_redirect_uri
    ]):

        st.error(
            "⚠️ Upwork API credentials are missing"
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

    st.caption(
        "Hourly jobs are evaluated primarily "
        "by whether your target rate fits inside "
        "the client's range."
    )


    st.divider()

    st.markdown(
        "### 🎯 Workflow"
    )

    st.write("""
    1. Find Upwork jobs
    2. Filter strong opportunities
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


    # =================================================
    # JOB
    # =================================================

    with col1:

        job_title = st.text_input(
            "Job title",
            placeholder=(
                "Example: Amazon Product Image Retoucher"
            ),
            key="job_title_input"
        )

        job_url = st.text_input(
            "Upwork URL (optional)",
            placeholder=(
                "https://www.upwork.com/jobs/..."
            ),
            key="job_url_input"
        )

        job_description = st.text_area(
            "Job description",
            height=420,
            placeholder=(
                "Paste the full Upwork job description here..."
            ),
            key="job_description_input"
        )


    # =================================================
    # BUDGET & COMPETITION
    # =================================================

    with col2:

        st.markdown(
            "### 💰 Budget & Competition"
        )

        budget = st.text_input(
            "Budget / Hourly Rate",
            placeholder=(
                "Example: $300 fixed or $25-$50/hr"
            ),
            key="budget_input"
        )

        proposals = st.text_input(
            "Proposals",
            placeholder="Example: 10 to 15",
            key="proposals_input"
        )

        interviewing = st.text_input(
            "Interviewing",
            placeholder="Example: 2",
            key="interviewing_input"
        )

        invites = st.text_input(
            "Invites sent",
            placeholder="Example: 5",
            key="invites_input"
        )

        unanswered_invites = (
            st.text_input(
                "Unanswered invites",
                placeholder="Example: 3",
                key="unanswered_invites_input"
            )
        )

        posted = st.text_input(
            "Posted",
            placeholder="Example: 2 hours ago",
            key="posted_input"
        )


    # =================================================
    # CLIENT
    # =================================================

    st.divider()

    st.markdown(
        "### 👤 Client Information"
    )

    c1, c2, c3, c4 = st.columns(4)


    with c1:

        client_spent = st.text_input(
            "Client total spent",
            placeholder="Example: $50K+",
            key="client_spent_input"
        )


    with c2:

        client_hires = st.text_input(
            "Client hires",
            placeholder="Example: 35",
            key="client_hires_input"
        )


    with c3:

        client_rating = st.text_input(
            "Client rating",
            placeholder="Example: 4.95",
            key="client_rating_input"
        )


    with c4:

        client_location = st.text_input(
            "Client location",
            placeholder="Example: United States",
            key="client_location_input"
        )


    c5, c6, c7, c8 = st.columns(4)


    with c5:

        client_active_hires = (
            st.text_input(
                "Active hires",
                placeholder="Example: 3",
                key="active_hires_input"
            )
        )


    with c6:

        client_hours = st.text_input(
            "Hours billed",
            placeholder="Example: 1,250",
            key="hours_billed_input"
        )


    with c7:

        client_member_since = (
            st.text_input(
                "Member since",
                placeholder="Example: 2018",
                key="member_since_input"
            )
        )


    with c8:

        project_length = st.text_input(
            "Project length",
            placeholder="Example: 1-3 months",
            key="project_length_input"
        )


    st.info(
        f"💡 Your target rate is ${TARGET_HOURLY_RATE}/hr. "
        "For hourly jobs, the system evaluates whether "
        "that rate fits inside the client's range."
    )


    # =================================================
    # ANALYZE BUTTON
    # =================================================

    if st.button(
        "🚀 Analyze Job",
        type="primary",
        use_container_width=True
    ):

        if not job_description.strip():

            st.warning(
                "Please paste the job description."
            )

        else:

            with st.spinner(
                "Analyzing opportunity..."
            ):

                prompt = f"""
You are a senior Upwork business opportunity analyst.

Evaluate this job for ONE specific freelancer.

The purpose is NOT to answer:
"Can the freelancer do this?"

The purpose is:
"Is applying to this job a smart use of time and Upwork Connects?"


=====================================================
FREELANCER
=====================================================

Positioning:

- Amazon Listing Images Expert
- High-End Photo Retoucher
- Photoshop Expert
- AI Image Specialist
- Product Image Specialist
- E-commerce Image Specialist

Profile:

- Top Rated
- 100% Job Success
- 5-star history
- strong completed-job history
- experienced freelancer

Strongest work:

- Amazon listing images
- product retouching
- e-commerce images
- AI + Photoshop
- photorealistic compositing
- product replacement
- lifestyle product integration
- background replacement
- preserving exact product geometry
- interior manipulation
- architectural retouching
- natural portrait retouching
- AI artifact correction


=====================================================
PRICING STRATEGY
=====================================================

The freelancer's target sustainable hourly rate is:

${TARGET_HOURLY_RATE}/hour


VERY IMPORTANT:

For HOURLY jobs, do NOT judge the job using
the LOWEST number in the client's range.

Instead ask:

"Can this freelancer reasonably bid at
${TARGET_HOURLY_RATE}/hour within the client's range?"


Examples:

Client range $15-$35/hr

The freelancer can bid $35/hr.

This is NOT a terrible budget.

Budget Quality should usually be approximately
55-70 depending on scope and client quality.


Client range $25-$50/hr

The freelancer can comfortably bid at $35-$45/hr.

Budget Quality should usually be 75-90.


Client range $10-$25/hr

The freelancer's target rate does NOT fit.

Budget Quality should usually be 20-40.


Client range $5-$15/hr

Budget Quality should usually be 0-20.


For FIXED PRICE jobs:

Estimate the realistic workload.

Consider:

- number of images
- complexity
- revisions
- precision required
- likely working hours

Then compare the fixed budget with a reasonable
professional value of the work.


Example:

71 complex images for $100

Budget Quality should be 0-10.

This is normally a DEAL BREAKER.


Example:

8 high-end interior images for $500-$800

This may be a healthy professional budget.


=====================================================
SKILL MATCH
=====================================================

Score 0-100.

Judge only fit with the freelancer's strongest skills.

Do NOT use budget when scoring Skill Match.


=====================================================
CLIENT QUALITY
=====================================================

Score 0-100.

Consider:

- lifetime spending
- number of hires
- active hires
- hours billed
- client rating
- professionalism
- clarity of brief
- repeat-work potential
- agency/company potential

Do not punish a good client heavily just because
one field such as rating is missing.


=====================================================
BUDGET QUALITY
=====================================================

Score 0-100.

Use the pricing rules above.

Most importantly:

A range such as $15-$35/hr should NOT receive
a score like 35 solely because its minimum is $15.

If the freelancer can bid at the TOP of the range
at their target rate, the opportunity may still
have a healthy budget.


=====================================================
COMPETITION SCORE
=====================================================

Score 0-100.

100 = very favorable.

0 = extremely unfavorable.

Consider:

- proposals
- interviewing
- invites
- unanswered invites
- how recently posted

Examples:

5-10 proposals, 0 interviews:
good competition.

15-20 proposals, 0 interviews:
reasonable competition.

20-50 proposals, 10 interviews:
poor competition.

30 invites + 11 interviews:
very unfavorable.


=====================================================
WIN PROBABILITY
=====================================================

Score 0-100.

Estimate probability that THIS freelancer
can stand out.

Consider:

- specialization
- Top Rated
- 100% JSS
- portfolio fit
- exact client problem
- AI + Photoshop advantage
- competition
- pricing compatibility


=====================================================
DEAL BREAKER
=====================================================

Return YES only for a serious reason to avoid applying.

Examples:

- absurdly low fixed budget
- clearly impossible deadline
- huge unpaid test
- major scope/budget mismatch
- suspicious or clearly problematic job

Do NOT return YES just because a job is imperfect.


=====================================================
CATEGORY
=====================================================

Choose exactly one:

Amazon
Product Retouching
AI + Photoshop
Interior / Architecture
Portrait
Other


=====================================================
JOB
=====================================================

TITLE:
{clean_value(job_title)}

DESCRIPTION:
{job_description}

BUDGET:
{clean_value(budget)}

PROPOSALS:
{clean_value(proposals)}

INTERVIEWING:
{clean_value(interviewing)}

INVITES:
{clean_value(invites)}

UNANSWERED INVITES:
{clean_value(unanswered_invites)}

POSTED:
{clean_value(posted)}

PROJECT LENGTH:
{clean_value(project_length)}


=====================================================
CLIENT
=====================================================

SPENT:
{clean_value(client_spent)}

HIRES:
{clean_value(client_hires)}

ACTIVE HIRES:
{clean_value(client_active_hires)}

RATING:
{clean_value(client_rating)}

HOURS:
{clean_value(client_hours)}

LOCATION:
{clean_value(client_location)}

MEMBER SINCE:
{clean_value(client_member_since)}


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
- reason

RISKS:
- risk
- risk

RECOMMENDED BID:
One concise recommendation only.

Example:
Recommended: $35/hr.

or:

Recommended: $700-$900 fixed.

Do not include complicated formulas.

PORTFOLIO TO SHOW:
1. example
2. example
3. example

APPLICATION STRATEGY:
- recommendation
- recommendation
- recommendation

PROPOSAL:
Write a concise personalized Upwork proposal
of approximately 100-140 words.

Never start with:
"I am excited to apply."

Start with the client's actual problem.

Sound natural, human and confident.
"""

                try:

                    response = (
                        openai_client.responses.create(
                            model="gpt-5-mini",
                            input=prompt
                        )
                    )

                    analysis = (
                        response.output_text
                    )


                    # ---------------------------------
                    # EXTRACT AI COMPONENT SCORES
                    # ---------------------------------

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


                    # ---------------------------------
                    # PYTHON CALCULATES FINAL SCORE
                    # ---------------------------------

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


                    # ---------------------------------
                    # SAVE SESSION
                    # ---------------------------------

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
                        "deal_breaker"
                    ] = deal_breaker

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
                        "The AI analysis could not be completed."
                    )

                    st.code(
                        str(e)
                    )


    # =================================================
    # DISPLAY RESULT
    # =================================================

    if "analysis" in st.session_state:

        analysis = st.session_state[
            "analysis"
        ]

        opportunity_score = (
            st.session_state.get(
                "opportunity_score"
            )
        )

        decision = (
            st.session_state.get(
                "decision"
            )
        )

        skill_match = (
            st.session_state.get(
                "skill_match"
            )
        )

        client_quality = (
            st.session_state.get(
                "client_quality"
            )
        )

        budget_quality = (
            st.session_state.get(
                "budget_quality"
            )
        )

        competition_score = (
            st.session_state.get(
                "competition_score"
            )
        )

        win_probability = (
            st.session_state.get(
                "win_probability"
            )
        )

        category = (
            st.session_state.get(
                "category",
                ""
            )
        )

        proposal = (
            st.session_state.get(
                "proposal",
                ""
            )
        )


        st.divider()

        st.subheader(
            "📈 Opportunity Overview"
        )


        # =================================================
        # FINAL SCORE FIRST
        # =================================================

        big1, big2 = st.columns(
            [2, 1]
        )

        with big1:

            st.metric(
                "Opportunity Score",
                f"{opportunity_score}/100"
            )

        with big2:

            st.markdown(
                "### Decision"
            )

            st.markdown(
                f"## {decision}"
            )


        st.write(
            "**Category:**",
            category
        )


        st.divider()


        # =================================================
        # COMPONENT SCORES
        # =================================================

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Skill Match",
            f"{skill_match}/100"
            if skill_match is not None
            else "—"
        )

        c2.metric(
            "Client Quality",
            f"{client_quality}/100"
            if client_quality is not None
            else "—"
        )

        c3.metric(
            "Budget Quality",
            f"{budget_quality}/100"
            if budget_quality is not None
            else "—"
        )


        c4, c5 = st.columns(2)

        c4.metric(
            "Competition",
            f"{competition_score}/100"
            if competition_score is not None
            else "—"
        )

        c5.metric(
            "Win Probability",
            f"{win_probability}/100"
            if win_probability is not None
            else "—"
        )


        st.divider()

        st.subheader(
            "🤖 Detailed Analysis"
        )

        st.markdown(
            analysis
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
                        opportunity_score,

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

                    "decision":
                        decision,

                    "category":
                        category,

                    "status":
                        status,

                    "proposal":
                        proposal,

                    "contract_value":
                        contract_value
                }


                supabase.table(
                    "jobs"
                ).insert(
                    data
                ).execute()


                st.success(
                    "✅ Job saved to history!"
                )

            except Exception as e:

                st.error(
                    "Could not save the job."
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

    st.caption(
        "Demo mode. Real Upwork jobs will appear here "
        "after API approval."
    )


    demo_jobs = [

        {
            "title":
                "AI Product Image Generation + Canva Rebrand",

            "url":
                "",

            "description":
                """
Generate realistic product and fashion images
for more than 30 products.

Change fabrics and environments while keeping
garments consistent and photographic.

Create 5-7 Canva tiles per product.

AI image generation combined with professional
manual editing is preferred.
""",

            "category":
                "AI + Photoshop",

            "budget":
                "$25-$45/hr",

            "client_spent":
                "$136K",

            "client_hires":
                "242",

            "client_rating":
                "",

            "client_location":
                "United Kingdom",

            "active_hires":
                "",

            "hours_billed":
                "7,680",

            "member_since":
                "2012",

            "project_length":
                "1-3 months",

            "proposals":
                "5-10",

            "interviewing":
                "0",

            "invites":
                "0",

            "unanswered_invites":
                "0",

            "posted":
                "4 hours ago",

            "score":
                91,

            "decision":
                "🔥 APPLY NOW"
        },


        {
            "title":
                "High-End Interior Photoshop Expert",

            "url":
                "",

            "description":
                """
Edit approximately 8 high-end interior photographs.

Remove objects, replace furniture and add curtains.

All edits must look completely photographic.

Previous AI attempts did not look realistic,
so professional Photoshop work is required.
""",

            "category":
                "Interior / Architecture",

            "budget":
                "$20-$45/hr",

            "client_spent":
                "$4.1K",

            "client_hires":
                "11",

            "client_rating":
                "",

            "client_location":
                "Australia",

            "active_hires":
                "4",

            "hours_billed":
                "152",

            "member_since":
                "",

            "project_length":
                "Less than 1 month",

            "proposals":
                "20-50",

            "interviewing":
                "1",

            "invites":
                "0",

            "unanswered_invites":
                "0",

            "posted":
                "",

            "score":
                88,

            "decision":
                "🟢 APPLY"
        },


        {
            "title":
                "Photo Editing and Retouching",

            "url":
                "",

            "description":
                """
Branding and marketing agency needs
a professional photo retoucher.

Fewer than 10 images.

Tasks include natural retouching,
background replacement,
expression adjustments
and group compositing.

Natural professional results are important.
AI-assisted tools are welcome.
""",

            "category":
                "Product Retouching",

            "budget":
                "$15-$35/hr",

            "client_spent":
                "$11K",

            "client_hires":
                "30",

            "client_rating":
                "",

            "client_location":
                "United States",

            "active_hires":
                "",

            "hours_billed":
                "499",

            "member_since":
                "",

            "project_length":
                "Less than 1 month",

            "proposals":
                "15-20",

            "interviewing":
                "0",

            "invites":
                "0",

            "unanswered_invites":
                "0",

            "posted":
                "",

            "score":
                84,

            "decision":
                "🟢 APPLY"
        },


        {
            "title":
                "Amazon Product Retoucher",

            "url":
                "",

            "description":
                """
Edit 71 existing Amazon product images.

Replace the fabric brand label on all images
while preserving perspective, texture,
lighting and stitching.

Standardize 42 cosmetic pouch images
to a reference.

Exact proportions, embroidery, fabric,
zipper and seams must be preserved.
""",

            "category":
                "Amazon",

            "budget":
                "$100 fixed",

            "client_spent":
                "$2.4K",

            "client_hires":
                "51",

            "client_rating":
                "",

            "client_location":
                "Germany",

            "active_hires":
                "4",

            "hours_billed":
                "",

            "member_since":
                "2013",

            "project_length":
                "",

            "proposals":
                "15-20",

            "interviewing":
                "0",

            "invites":
                "0",

            "unanswered_invites":
                "0",

            "posted":
                "",

            "score":
                51,

            "decision":
                "🔴 SKIP"
        }
    ]


    # =================================================
    # FILTERS
    # =================================================

    st.markdown(
        "### 🎚️ Filters"
    )


    f1, f2 = st.columns(2)


    with f1:

        minimum_score = st.slider(
            "Minimum Opportunity Score",
            0,
            100,
            65,
            5
        )


    with f2:

        category_filter = st.selectbox(
            "Category",
            [
                "All",
                "Amazon",
                "Product Retouching",
                "AI + Photoshop",
                "Interior / Architecture",
                "Portrait",
                "Other"
            ],
            key="find_category_filter"
        )


    filtered_jobs = []


    for job in demo_jobs:

        if job["score"] < minimum_score:
            continue

        if (
            category_filter != "All"
            and
            job["category"] != category_filter
        ):
            continue

        filtered_jobs.append(
            job
        )


    st.divider()


    m1, m2, m3 = st.columns(3)


    m1.metric(
        "Jobs found",
        len(demo_jobs)
    )

    m2.metric(
        "Worth reviewing",
        len(filtered_jobs)
    )

    m3.metric(
        "Strong opportunities",
        len([
            job
            for job in filtered_jobs
            if job["score"] >= 80
        ])
    )


    st.divider()


    for index, job in enumerate(
        filtered_jobs
    ):

        with st.container(
            border=True
        ):

            col1, col2, col3 = st.columns(
                [4, 1, 1]
            )


            with col1:

                st.subheader(
                    job["title"]
                )

                st.write(
                    f"**Category:** {job['category']}"
                )

                st.write(
                    f"**Budget:** {job['budget']}"
                )

                st.write(
                    f"**Client:** {job['client_spent']} spent"
                )

                st.write(
                    f"**Proposals:** {job['proposals']}"
                )


            with col2:

                st.metric(
                    "Score",
                    f"{job['score']}/100"
                )

                st.write(
                    job["decision"]
                )


            with col3:

                st.write("")

                st.write("")

                if st.button(
                    "🎯 Analyze",
                    key=f"analyze_{index}",
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
# TAB 3 — JOB HISTORY
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

            total_revenue = sum([
                float(
                    j.get(
                        "contract_value"
                    )
                    or 0
                )
                for j in jobs
                if j.get("status")
                == "Hired"
            ])


            c1, c2, c3, c4, c5 = (
                st.columns(5)
            )


            c1.metric(
                "Jobs Analyzed",
                total_jobs
            )

            c2.metric(
                "Applied",
                applied
            )

            c3.metric(
                "Interviews",
                interviews
            )

            c4.metric(
                "Hired",
                hired
            )

            c5.metric(
                "Contract Value",
                f"${total_revenue:,.0f}"
            )


            if applied > 0:

                r1, r2 = st.columns(2)

                r1.metric(
                    "Interview Rate",
                    f"{interviews / applied * 100:.1f}%"
                )

                r2.metric(
                    "Hire Rate",
                    f"{hired / applied * 100:.1f}%"
                )


            st.divider()

            st.subheader(
                "📋 Saved Opportunities"
            )


            for job in jobs:

                title = (
                    job.get("job_title")
                    or "Untitled Job"
                )

                score = (
                    job.get(
                        "opportunity_score"
                    )
                    or "—"
                )

                job_status = (
                    job.get("status")
                    or "Not applied"
                )

                job_category = (
                    job.get("category")
                    or "Uncategorized"
                )


                with st.expander(
                    f"{title} | "
                    f"{job_category} | "
                    f"Score: {score} | "
                    f"{job_status}"
                ):


                    p1, p2, p3 = (
                        st.columns(3)
                    )


                    p1.metric(
                        "Opportunity Score",
                        job.get(
                            "opportunity_score"
                        )
                        or "—"
                    )

                    p2.metric(
                        "Skill Match",
                        job.get(
                            "skill_match"
                        )
                        or "—"
                    )

                    p3.metric(
                        "Win Probability",
                        job.get(
                            "win_probability"
                        )
                        or "—"
                    )


                    statuses = [
                        "Not applied",
                        "Applied",
                        "Interview",
                        "Hired",
                        "Rejected"
                    ]


                    if (
                        job_status
                        not in statuses
                    ):
                        job_status = (
                            "Not applied"
                        )


                    new_status = st.selectbox(
                        "Update status",
                        statuses,
                        index=statuses.index(
                            job_status
                        ),
                        key=f"status_{job['id']}"
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
                        key=f"value_{job['id']}"
                    )


                    if st.button(
                        "Update",
                        key=f"update_{job['id']}"
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
                                "Could not update the job."
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

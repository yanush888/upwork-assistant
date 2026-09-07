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

def extract_number(text, label):

    pattern = rf"{re.escape(label)}:\s*(\d+)"

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if match:
        return int(match.group(1))

    return None


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


def clean_value(value):

    if value is None:
        return "Unknown"

    value = str(value).strip()

    if not value:
        return "Unknown"

    return value


# =====================================================
# PREFILL JOB FROM FIND JOBS
# =====================================================

if st.session_state.get(
    "load_job_into_analyzer"
):

    selected_job = st.session_state.get(
        "selected_job",
        {}
    )

    st.session_state[
        "job_title_input"
    ] = selected_job.get(
        "title",
        ""
    )

    st.session_state[
        "job_url_input"
    ] = selected_job.get(
        "url",
        ""
    )

    st.session_state[
        "job_description_input"
    ] = selected_job.get(
        "description",
        ""
    )

    st.session_state[
        "budget_input"
    ] = selected_job.get(
        "budget",
        ""
    )

    st.session_state[
        "proposals_input"
    ] = selected_job.get(
        "proposals",
        ""
    )

    st.session_state[
        "interviewing_input"
    ] = selected_job.get(
        "interviewing",
        ""
    )

    st.session_state[
        "invites_input"
    ] = selected_job.get(
        "invites",
        ""
    )

    st.session_state[
        "unanswered_invites_input"
    ] = selected_job.get(
        "unanswered_invites",
        ""
    )

    st.session_state[
        "posted_input"
    ] = selected_job.get(
        "posted",
        ""
    )

    st.session_state[
        "client_spent_input"
    ] = selected_job.get(
        "client_spent",
        ""
    )

    st.session_state[
        "client_hires_input"
    ] = selected_job.get(
        "client_hires",
        ""
    )

    st.session_state[
        "client_rating_input"
    ] = selected_job.get(
        "client_rating",
        ""
    )

    st.session_state[
        "client_location_input"
    ] = selected_job.get(
        "client_location",
        ""
    )

    st.session_state[
        "active_hires_input"
    ] = selected_job.get(
        "active_hires",
        ""
    )

    st.session_state[
        "hours_billed_input"
    ] = selected_job.get(
        "hours_billed",
        ""
    )

    st.session_state[
        "member_since_input"
    ] = selected_job.get(
        "member_since",
        ""
    )

    st.session_state[
        "project_length_input"
    ] = selected_job.get(
        "project_length",
        ""
    )

    st.session_state[
        "load_job_into_analyzer"
    ] = False


# =====================================================
# UPWORK OAUTH FUNCTIONS
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
            "Accept": "application/json",
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

            st.session_state[
                "UPWORK_TOKEN_EXPIRES_IN"
            ] = token_data.get(
                "expires_in"
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

        authorization_url = (
            build_upwork_auth_url()
        )

        st.link_button(
            "Connect Upwork",
            authorization_url,
            use_container_width=True
        )


    st.divider()

    st.markdown(
        "### 🎯 Workflow"
    )

    st.write("""
    1. Find Upwork jobs
    2. Filter strong opportunities
    3. Analyze the opportunity
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
            "Review the information and click Analyze Job."
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

        unanswered_invites = st.text_input(
            "Unanswered invites",
            placeholder="Example: 3",
            key="unanswered_invites_input"
        )

        posted = st.text_input(
            "Posted",
            placeholder="Example: 2 hours ago",
            key="posted_input"
        )


    # =================================================
    # CLIENT INFORMATION
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

        client_active_hires = st.text_input(
            "Active hires",
            placeholder="Example: 3",
            key="active_hires_input"
        )


    with c6:

        client_hours = st.text_input(
            "Hours billed",
            placeholder="Example: 1,250",
            key="hours_billed_input"
        )


    with c7:

        client_member_since = st.text_input(
            "Member since",
            placeholder="Example: 2018",
            key="member_since_input"
        )


    with c8:

        project_length = st.text_input(
            "Project length",
            placeholder="Example: 1-3 months",
            key="project_length_input"
        )


    st.info(
        "💡 The more Upwork data you add, "
        "the more accurate the Opportunity Score will be."
    )


    # =================================================
    # ANALYZE
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
You are a senior Upwork opportunity analyst.

Your task is to determine whether this is a GOOD BUSINESS
OPPORTUNITY for this specific freelancer.

Skill Match is NOT the same as Opportunity Score.

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
- Experienced freelancer

Core strengths:

- Amazon listing images
- product retouching
- high-end Photoshop
- AI + Photoshop
- photorealistic AI compositing
- lifestyle product integration
- product replacement
- preserving product geometry
- background replacement
- interior manipulation
- architectural editing
- natural portrait retouching
- AI artifact correction


=====================================================
BUSINESS PRIORITIES
=====================================================

Prioritize:

1. Amazon / e-commerce
2. AI + Photoshop
3. Product/lifestyle compositing
4. High-end retouching
5. Interior / architecture
6. Recurring image production
7. Agencies
8. Established clients
9. Long-term relationships

Penalize:

- extremely low budgets
- unrealistic workload
- low compensation per image
- commodity Photoshop work
- excessive unpaid tests
- unclear scope
- unrealistic deadlines
- huge competition
- many active interviews
- price-driven clients


=====================================================
SCORING
=====================================================

Skill Match: 25%

Client Quality: 20%

Budget Quality: 20%

Competition: 15%

Win Probability: 20%


An excellent Skill Match must NOT compensate
for a terrible budget.

Example:

70 skilled image edits for $100
can be:

SKILL MATCH: 95

but

OPPORTUNITY SCORE: 50


=====================================================
DECISIONS
=====================================================

90-100:
🔥 APPLY NOW

80-89:
🟢 APPLY

65-79:
🟡 MAYBE

0-64:
🔴 SKIP


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
OUTPUT
=====================================================

OPPORTUNITY SCORE: X/100

DECISION:
decision

CATEGORY:
Amazon
or
Product Retouching
or
AI + Photoshop
or
Interior / Architecture
or
Portrait
or
Other

SKILL MATCH: X/100

CLIENT QUALITY: X/100 or Unknown

BUDGET QUALITY: X/100 or Unknown

COMPETITION SCORE: X/100 or Unknown

WIN PROBABILITY: X/100

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

DEAL BREAKERS:
None or explain

RECOMMENDED BID:
Give one concise realistic recommendation.

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

Do not start with:
"I am excited to apply."

Start with the client's actual problem.

Sound human, concise and confident.
"""

                try:

                    response = (
                        openai_client.responses.create(
                            model="gpt-5-mini",
                            input=prompt
                        )
                    )

                    result = response.output_text

                    st.session_state[
                        "analysis"
                    ] = result

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
    # DISPLAY ANALYSIS
    # =================================================

    if "analysis" in st.session_state:

        result = st.session_state[
            "analysis"
        ]

        st.divider()

        st.subheader(
            "🤖 AI Analysis"
        )

        st.markdown(
            result
        )


        opportunity_score = extract_number(
            result,
            "OPPORTUNITY SCORE"
        )

        skill_match = extract_number(
            result,
            "SKILL MATCH"
        )

        client_quality = extract_number(
            result,
            "CLIENT QUALITY"
        )

        budget_quality = extract_number(
            result,
            "BUDGET QUALITY"
        )

        competition_score = extract_number(
            result,
            "COMPETITION SCORE"
        )

        win_probability = extract_number(
            result,
            "WIN PROBABILITY"
        )


        decision = extract_section(
            result,
            "DECISION",
            "CATEGORY"
        )

        category = extract_section(
            result,
            "CATEGORY",
            "SKILL MATCH"
        )

        proposal = extract_section(
            result,
            "PROPOSAL"
        )


        st.divider()

        st.subheader(
            "📈 Opportunity Overview"
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Opportunity Score",
            (
                f"{opportunity_score}/100"
                if opportunity_score is not None
                else "—"
            )
        )

        c2.metric(
            "Skill Match",
            (
                f"{skill_match}/100"
                if skill_match is not None
                else "—"
            )
        )

        c3.metric(
            "Win Probability",
            (
                f"{win_probability}/100"
                if win_probability is not None
                else "—"
            )
        )


        c4, c5, c6 = st.columns(3)

        c4.metric(
            "Client Quality",
            (
                f"{client_quality}/100"
                if client_quality is not None
                else "Unknown"
            )
        )

        c5.metric(
            "Budget Quality",
            (
                f"{budget_quality}/100"
                if budget_quality is not None
                else "Unknown"
            )
        )

        c6.metric(
            "Competition",
            (
                f"{competition_score}/100"
                if competition_score is not None
                else "Unknown"
            )
        )


        st.write(
            "**Category:**",
            category
        )

        st.write(
            "**Decision:**",
            decision
        )


        # =================================================
        # SAVE JOB
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
        "after the API key is activated."
    )


    demo_jobs = [

        {
            "title":
                "AI Product Image Generation + Canva Rebrand",

            "url":
                "",

            "description":
                """
We need a freelancer to generate realistic product
and fashion images for more than 30 products.

The work includes changing fabric and environments
while maintaining consistent garments and realistic
photographic results.

The freelancer will also create 5-7 Canva tiles
per product.

AI image generation experience combined with
professional image editing is preferred.
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
We need an experienced Photoshop expert to edit
approximately 8 high-end interior design photographs.

Tasks include removing objects, replacing furniture,
adding curtains and making all alterations look
completely realistic.

Previous AI attempts did not look convincing.
We specifically need professional Photoshop work.
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
Branding and marketing agency is looking for
a professional photo retoucher.

The project includes fewer than 10 images.

Tasks may include natural retouching,
background replacement, expression adjustments
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
We need an experienced Photoshop product retoucher
to edit 71 existing Amazon product images.

Replace the fabric brand label on all 71 images
while preserving realistic perspective, texture,
lighting and stitching.

Standardize 42 cosmetic pouch images so they match
a reference image in position, scale, angle,
background and lighting.

Exact proportions, embroidery, colors, texture,
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
        },


        {
            "title":
                "Calendar Photoshop Adjustments",

            "url":
                "",

            "description":
                """
We need a Photoshop retoucher to adjust
approximately 20 calendar images.

Tasks include changing calendar years from
2026 to 2027, replacing calendar elements,
matching colors and delivering high-resolution
and web-resolution images.
""",

            "category":
                "Product Retouching",

            "budget":
                "$10-$25/hr",

            "client_spent":
                "$7K",

            "client_hires":
                "78",

            "client_rating":
                "",

            "client_location":
                "United Kingdom",

            "active_hires":
                "28",

            "hours_billed":
                "245",

            "member_since":
                "",

            "project_length":
                "1-3 months",

            "proposals":
                "10-15",

            "interviewing":
                "11",

            "invites":
                "30",

            "unanswered_invites":
                "19",

            "posted":
                "",

            "score":
                58,

            "decision":
                "🔴 SKIP"
        }
    ]


    demo_jobs = sorted(
        demo_jobs,
        key=lambda x: x["score"],
        reverse=True
    )


    # =================================================
    # FILTERS
    # =================================================

    st.markdown(
        "### 🎚️ Filters"
    )

    filter_col1, filter_col2 = st.columns(2)


    with filter_col1:

        minimum_score = st.slider(
            "Minimum Opportunity Score",
            min_value=0,
            max_value=100,
            value=65,
            step=5
        )


    with filter_col2:

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


    # =================================================
    # SUMMARY
    # =================================================

    c1, c2, c3 = st.columns(3)


    c1.metric(
        "Jobs found",
        len(demo_jobs)
    )


    c2.metric(
        "Worth reviewing",
        len(filtered_jobs)
    )


    strong_jobs_count = len([
        job for job in filtered_jobs
        if job["score"] >= 80
    ])


    c3.metric(
        "Strong opportunities",
        strong_jobs_count
    )


    st.divider()


    # =================================================
    # JOB CARDS
    # =================================================

    if not filtered_jobs:

        st.info(
            "No jobs match your current filters."
        )


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

                info1, info2 = st.columns(2)


                with info1:

                    st.write(
                        f"**Category:** "
                        f"{job['category']}"
                    )

                    st.write(
                        f"**Budget:** "
                        f"{job['budget']}"
                    )


                with info2:

                    st.write(
                        f"**Client:** "
                        f"{job['client_spent']} spent"
                    )

                    st.write(
                        f"**Proposals:** "
                        f"{job['proposals']}"
                    )


            with col2:

                st.metric(
                    "Score",
                    f"{job['score']}/100"
                )

                st.write(
                    f"**{job['decision']}**"
                )


            with col3:

                st.write("")

                st.write("")

                if st.button(
                    "🎯 Analyze",
                    key=f"analyze_demo_{index}",
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


    st.info(
        "Demo data only. After Upwork API approval, "
        "these cards will be populated with live marketplace jobs."
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
                j for j in jobs
                if j.get("status")
                in [
                    "Applied",
                    "Interview",
                    "Hired"
                ]
            ])


            interviews = len([
                j for j in jobs
                if j.get("status")
                in [
                    "Interview",
                    "Hired"
                ]
            ])


            hired = len([
                j for j in jobs
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


            col1, col2, col3, col4, col5 = (
                st.columns(5)
            )


            col1.metric(
                "Jobs Analyzed",
                total_jobs
            )

            col2.metric(
                "Applied",
                applied
            )

            col3.metric(
                "Interviews",
                interviews
            )

            col4.metric(
                "Hired",
                hired
            )

            col5.metric(
                "Contract Value",
                f"${total_revenue:,.0f}"
            )


            if applied > 0:

                interview_rate = (
                    interviews /
                    applied *
                    100
                )

                hire_rate = (
                    hired /
                    applied *
                    100
                )


                c1, c2 = st.columns(2)


                c1.metric(
                    "Interview Rate",
                    f"{interview_rate:.1f}%"
                )

                c2.metric(
                    "Hire Rate",
                    f"{hire_rate:.1f}%"
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


                    c1, c2, c3 = st.columns(3)


                    c1.metric(
                        "Opportunity Score",
                        job.get(
                            "opportunity_score"
                        )
                        or "—"
                    )


                    c2.metric(
                        "Skill Match",
                        job.get(
                            "skill_match"
                        )
                        or "—"
                    )


                    c3.metric(
                        "Win Probability",
                        job.get(
                            "win_probability"
                        )
                        or "—"
                    )


                    st.write(
                        "**Category:**",
                        job_category
                    )


                    st.write(
                        "**Decision:**",
                        job.get(
                            "decision"
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


                    if job_status not in statuses:

                        job_status = (
                            "Not applied"
                        )


                    new_status = st.selectbox(
                        "Update status",
                        statuses,
                        index=statuses.index(
                            job_status
                        ),
                        key=(
                            f"status_{job['id']}"
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
                            f"value_{job['id']}"
                        )
                    )


                    if st.button(
                        "Update",
                        key=(
                            f"update_{job['id']}"
                        )
                    ):

                        try:

                            supabase.table(
                                "jobs"
                            ).update({

                                "status":
                                    new_status,

                                "contract_value":
                                    new_value

                            }).eq(
                                "id",
                                job["id"]
                            ).execute()


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

import streamlit as st
import re
from openai import OpenAI
from supabase import create_client

# -----------------------------
# SETTINGS
# -----------------------------

st.set_page_config(
    page_title="Upwork Opportunity Assistant",
    page_icon="🎯",
    layout="wide"
)

openai_client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

# -----------------------------
# HELPERS
# -----------------------------

def extract_number(text, label):
    pattern = rf"{re.escape(label)}:\s*(\d+)"
    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        return int(match.group(1))

    return None


def extract_section(text, section_name, next_section=None):

    if next_section:
        pattern = (
            rf"{re.escape(section_name)}:\s*(.*?)"
            rf"(?={re.escape(next_section)}:)"
        )
    else:
        pattern = rf"{re.escape(section_name)}:\s*(.*)"

    match = re.search(
        pattern,
        text,
        re.IGNORECASE | re.DOTALL
    )

    if match:
        return match.group(1).strip()

    return ""


# -----------------------------
# HEADER
# -----------------------------

st.title("🎯 Upwork Opportunity Assistant")

st.caption(
    "Analyze opportunities, generate proposals and track which jobs "
    "actually lead to interviews and contracts."
)

tab1, tab2 = st.tabs([
    "🎯 Analyze Job",
    "📊 Job History"
])

# =====================================================
# TAB 1 — ANALYZE
# =====================================================

with tab1:

    col1, col2 = st.columns([2, 1])

    with col1:

        job_title = st.text_input(
            "Job title",
            placeholder="Example: Amazon Product Image Retoucher"
        )

        job_url = st.text_input(
            "Upwork URL (optional)",
            placeholder="https://www.upwork.com/jobs/..."
        )

        job_description = st.text_area(
            "Job description",
            height=380,
            placeholder="Paste the full Upwork job description here..."
        )

    with col2:

        st.subheader("What the assistant evaluates")

        st.write("""
        • Skill Match  
        • Client Quality  
        • Budget Quality  
        • Competition  
        • Win Probability  
        • Business value  
        """)

        st.info(
            "The goal is not to find jobs you CAN do. "
            "The goal is to find jobs worth winning."
        )

    if st.button(
        "Analyze Job",
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

Your task is to determine whether this job is a strong BUSINESS
OPPORTUNITY for this specific freelancer.

FREELANCER PROFILE

Positioning:
- Amazon Listing Images Expert
- High-End Photo Retoucher
- Photoshop Expert
- AI Image Specialist
- Product Image Specialist

Profile strength:
- Top Rated
- 100% Job Success
- 5-star history
- Experienced freelancer

CORE SKILLS

- Amazon listing image creation
- E-commerce product images
- Product retouching
- High-end Photoshop retouching
- AI-generated images
- AI + Photoshop compositing
- Photorealistic AI finishing
- Product replacement
- Lifestyle product integration
- Maintaining exact product proportions and textures
- Interior and architectural photo editing
- Furniture replacement
- Background replacement
- Natural portrait retouching
- Complex compositing
- Correcting AI artifacts
- Maintaining consistency across image series

COMPETITIVE ADVANTAGE

The freelancer is particularly strong when pure AI is not sufficient
and professional Photoshop finishing is necessary to achieve
photographic realism.

BUSINESS STRATEGY

Strongly prioritize:

1. Amazon / e-commerce product images
2. AI + Photoshop projects
3. Product/lifestyle compositing
4. High-end photo retouching
5. Interior / architectural manipulation
6. Recurring production work
7. Agencies and established companies

Prefer:

- clients with proven Upwork spending
- repeat work potential
- professional briefs
- quality-sensitive projects
- higher-value projects
- long-term relationships

Penalize:

- extremely low budgets
- unrealistic amount of work for the budget
- commodity Photoshop jobs
- excessive unpaid tests
- unclear scope
- unrealistic deadlines
- excessive competition
- clients already interviewing many freelancers

IMPORTANT:

Skill Match is NOT the same as Opportunity Score.

A job can have a Skill Match of 98/100
but an Opportunity Score of only 50/100
if the economics are poor.

SCORING

SKILL MATCH:
0-100

CLIENT QUALITY:
0-100 or Unknown

BUDGET QUALITY:
0-100 or Unknown

COMPETITION SCORE:
0-100 or Unknown

100 competition score means very favorable competition.

WIN PROBABILITY:
0-100

Estimate this freelancer's probability of standing out from
other applicants.

OPPORTUNITY SCORE:
0-100

Suggested weighting:

Skill Match: 25%
Client Quality: 20%
Budget Quality: 20%
Competition: 15%
Win Probability: 20%

DECISION

90-100 = 🔥 APPLY NOW
80-89 = 🟢 APPLY
65-79 = 🟡 MAYBE
0-64 = 🔴 SKIP

Be selective and realistic.

JOB TITLE:

{job_title}

JOB DESCRIPTION:

{job_description}


RETURN EXACTLY THIS STRUCTURE:

OPPORTUNITY SCORE: X/100

DECISION:
decision

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

RISKS:
- risk
- risk

DEAL BREAKERS:
None or explain

RECOMMENDED BID:
pricing recommendation

PORTFOLIO TO SHOW:
1. example
2. example
3. example

APPLICATION STRATEGY:
- recommendation
- recommendation
- recommendation

PROPOSAL:
Write a personalized Upwork proposal around 100-140 words.

Proposal rules:

- Never start with "I am excited to apply"
- Start with the client's actual problem
- Sound human
- Be concise
- Do not exaggerate
- Mention AI + Photoshop only when relevant
- Focus on outcomes
- End with a simple call to action
"""

                try:

                    response = openai_client.responses.create(
                        model="gpt-5-mini",
                        input=prompt
                    )

                    result = response.output_text

                    st.session_state["analysis"] = result
                    st.session_state["job_title"] = job_title
                    st.session_state["job_url"] = job_url
                    st.session_state["job_description"] = job_description

                except Exception as e:

                    st.error(
                        "AI analysis failed."
                    )

                    st.code(str(e))

    # -----------------------------
    # DISPLAY RESULT
    # -----------------------------

    if "analysis" in st.session_state:

        result = st.session_state["analysis"]

        st.divider()

        st.subheader("AI Analysis")

        st.markdown(result)

        # Extract numbers

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
            "SKILL MATCH"
        )

        proposal = extract_section(
            result,
            "PROPOSAL"
        )

        st.divider()

        st.subheader("💾 Save to Job History")

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

                st.code(str(e))


# =====================================================
# TAB 2 — HISTORY
# =====================================================

with tab2:

    st.subheader("📊 Job History")

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

            # -------------------------
            # METRICS
            # -------------------------

            total_jobs = len(jobs)

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
                if j.get("status") == "Hired"
            ])

            col1, col2, col3, col4 = st.columns(4)

            col1.metric(
                "Jobs analyzed",
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

                st.write(
                    f"**Interview rate:** "
                    f"{interview_rate:.1f}%"
                )

                st.write(
                    f"**Hire rate:** "
                    f"{hire_rate:.1f}%"
                )

            st.divider()

            # -------------------------
            # JOB LIST
            # -------------------------

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

                status = (
                    job.get("status")
                    or "Not applied"
                )

                with st.expander(
                    f"{title} | "
                    f"Score: {score} | "
                    f"{status}"
                ):

                    st.write(
                        "**Opportunity Score:**",
                        job.get(
                            "opportunity_score"
                        )
                    )

                    st.write(
                        "**Skill Match:**",
                        job.get(
                            "skill_match"
                        )
                    )

                    st.write(
                        "**Win Probability:**",
                        job.get(
                            "win_probability"
                        )
                    )

                    st.write(
                        "**Decision:**",
                        job.get(
                            "decision"
                        )
                    )

                    if job.get("job_url"):

                        st.write(
                            "**Upwork URL:**",
                            job.get(
                                "job_url"
                            )
                        )

                    new_status = st.selectbox(
                        "Update status",
                        [
                            "Not applied",
                            "Applied",
                            "Interview",
                            "Hired",
                            "Rejected"
                        ],
                        index=[
                            "Not applied",
                            "Applied",
                            "Interview",
                            "Hired",
                            "Rejected"
                        ].index(status),
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
                            "Updated!"
                        )

                        st.rerun()

    except Exception as e:

        st.error(
            "Could not load Job History."
        )

        st.code(str(e))

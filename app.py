import streamlit as st
import re
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

openai_client = OpenAI(
    api_key=st.secrets["OPENAI_API_KEY"]
)

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def extract_number(text, label):
    """
    Extracts a number from lines such as:
    OPPORTUNITY SCORE: 87/100
    """

    pattern = rf"{re.escape(label)}:\s*(\d+)"
    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        return int(match.group(1))

    return None


def extract_section(text, section_name, next_section=None):
    """
    Extracts text between two section headings.
    """

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


# =====================================================
# HEADER
# =====================================================

st.title("🎯 Upwork Opportunity Assistant")

st.caption(
    "Find the Upwork opportunities that are actually worth applying to."
)

tab1, tab2 = st.tabs([
    "🎯 Analyze Job",
    "📊 Job History"
])


# =====================================================
# TAB 1 — ANALYZE JOB
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
            height=420,
            placeholder="Paste the full Upwork job description here..."
        )

    with col2:

        st.subheader("What AI evaluates")

        st.write("""
        • Skill Match  
        • Client Quality  
        • Budget Quality  
        • Competition  
        • Win Probability  
        • Business Value  
        """)

        st.info(
            "The goal is not to find jobs you CAN do. "
            "The goal is to find jobs worth winning."
        )


    # =================================================
    # ANALYZE BUTTON
    # =================================================

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

Your task is NOT simply to determine whether the freelancer can
technically perform the job.

Your task is to determine whether this is a GOOD BUSINESS OPPORTUNITY
for this specific freelancer and whether the freelancer has a realistic
competitive advantage.

=====================================================
FREELANCER PROFILE
=====================================================

Positioning:

- Amazon Listing Images Expert
- High-End Photo Retoucher
- Photoshop Expert
- AI Image Specialist / AI Artist
- Product Image Specialist
- E-commerce Image Specialist

Upwork profile strength:

- Top Rated
- 100% Job Success
- 5-star history
- Strong completed-job history
- Experienced freelancer


=====================================================
CORE SKILLS
=====================================================

- Amazon listing image creation
- Amazon product images
- E-commerce product photography
- Product retouching
- High-end Photoshop retouching
- Natural photo retouching
- AI-generated imagery
- AI + Photoshop workflows
- Photorealistic AI compositing
- Product replacement
- Lifestyle product integration
- Maintaining exact product proportions
- Maintaining texture and geometry
- Background replacement
- Complex compositing
- Interior photo manipulation
- Architectural photo editing
- Furniture replacement
- Natural portrait retouching
- Correcting AI artifacts
- Maintaining consistency across image series


=====================================================
COMPETITIVE ADVANTAGE
=====================================================

The freelancer is particularly strong when pure AI generation
is not sufficient.

The freelancer combines AI generation with professional manual
Photoshop finishing to achieve photographic realism.

This is especially valuable for:

- Amazon products
- e-commerce images
- lifestyle product scenes
- difficult AI-generated images
- interior manipulation
- high-end retouching
- realistic compositing


=====================================================
BUSINESS STRATEGY
=====================================================

Strongly prioritize:

1. Amazon / e-commerce product images
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
- clients with previous hires
- repeat work potential
- professional briefs
- quality-sensitive projects
- higher-value projects
- long-term relationships
- jobs where photographic realism matters


Penalize:

- extremely low budgets
- unrealistic amount of work for the budget
- commodity Photoshop jobs
- excessive unpaid tests
- unclear scope
- unrealistic deadlines
- huge competition
- clients already interviewing many freelancers
- jobs where price appears to be the primary selection factor


=====================================================
IMPORTANT SCORING PRINCIPLE
=====================================================

Skill Match is NOT the same as Opportunity Score.

For example:

A job may have:

SKILL MATCH: 98/100

but

OPPORTUNITY SCORE: 50/100

if the client wants 70 images for only $100.

Do not inflate Opportunity Score simply because the freelancer
can technically perform the work.


=====================================================
CATEGORY
=====================================================

Choose EXACTLY ONE category:

Amazon

Product Retouching

AI + Photoshop

Interior / Architecture

Portrait

Other


CATEGORY RULES:

Amazon:
Amazon listing images, A+ content, Amazon product graphics,
Amazon lifestyle images.

Product Retouching:
Product photography, e-commerce images, product cleanup,
color correction, product editing.

AI + Photoshop:
AI-generated images, generative AI, AI compositing,
AI correction, AI + manual Photoshop workflows.

Interior / Architecture:
Interior photography, real estate, architecture,
furniture replacement, room manipulation.

Portrait:
People, faces, beauty, skin, portrait photography,
headshots.

Other:
Use only when none of the categories above fit well.


=====================================================
SCORING
=====================================================

Calculate:

SKILL MATCH:
0-100

How closely the work matches the freelancer's strongest skills.


CLIENT QUALITY:
0-100

Consider:

- previous spending
- hiring history
- professionalism
- clarity of brief
- potential repeat work

If information is missing, return:

Unknown


BUDGET QUALITY:
0-100

Evaluate compensation relative to:

- scope
- number of images
- complexity
- freelancer seniority

Do NOT reward low-paying projects just because they are easy.

If budget information is missing, return:

Unknown


COMPETITION SCORE:
0-100

100 = very favorable competition.

0 = extremely unfavorable competition.

Consider:

- proposals
- interviews
- invitations
- how recently the job was posted

If information is missing, return:

Unknown


WIN PROBABILITY:
0-100

Estimate how likely THIS freelancer is to stand out from other
applicants.

Consider:

- specialization
- profile strength
- relevant portfolio
- client's exact problem
- competitive advantage


OPPORTUNITY SCORE:
0-100

This represents overall business value.


Suggested weighting:

Skill Match: 25%
Client Quality: 20%
Budget Quality: 20%
Competition: 15%
Win Probability: 20%


Use professional judgment when some information is missing.


=====================================================
DECISION RULES
=====================================================

90-100:

🔥 APPLY NOW


80-89:

🟢 APPLY


65-79:

🟡 MAYBE


0-64:

🔴 SKIP


Be selective.

The purpose is to avoid wasting time and Upwork Connects.


=====================================================
JOB
=====================================================

JOB TITLE:

{job_title}


JOB DESCRIPTION:

{job_description}


=====================================================
RETURN EXACTLY THIS STRUCTURE
=====================================================

OPPORTUNITY SCORE: X/100

DECISION:
decision

CATEGORY:
category

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
Give a realistic pricing recommendation.

Do not automatically compete at the bottom of the client's
budget range.

PORTFOLIO TO SHOW:
1. example
2. example
3. example

APPLICATION STRATEGY:
- recommendation
- recommendation
- recommendation

PROPOSAL:
Write a personalized Upwork proposal of approximately 100-140 words.


PROPOSAL RULES:

- Never start with "I am excited to apply"
- Start with the client's actual problem
- Sound human and confident
- Be concise
- Do not exaggerate
- Mention only relevant experience
- Mention AI + Photoshop only when relevant
- Focus on the result the client wants
- Avoid generic freelancer language
- End with a simple call to action
"""

                try:

                    response = openai_client.responses.create(
                        model="gpt-5-mini",
                        input=prompt
                    )

                    result = response.output_text

                    # Save current analysis in session

                    st.session_state["analysis"] = result

                    st.session_state["job_title"] = (
                        job_title
                    )

                    st.session_state["job_url"] = (
                        job_url
                    )

                    st.session_state["job_description"] = (
                        job_description
                    )

                except Exception as e:

                    st.error(
                        "The AI analysis could not be completed."
                    )

                    st.code(str(e))


    # =================================================
    # DISPLAY ANALYSIS
    # =================================================

    if "analysis" in st.session_state:

        result = st.session_state["analysis"]

        st.divider()

        st.subheader("🤖 AI Analysis")

        st.markdown(result)


        # ---------------------------------------------
        # EXTRACT DATA
        # ---------------------------------------------

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


        # ---------------------------------------------
        # SCORE CARDS
        # ---------------------------------------------

        st.divider()

        st.subheader("📈 Opportunity Overview")

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Opportunity Score",
            f"{opportunity_score}/100"
            if opportunity_score is not None
            else "—"
        )

        c2.metric(
            "Skill Match",
            f"{skill_match}/100"
            if skill_match is not None
            else "—"
        )

        c3.metric(
            "Win Probability",
            f"{win_probability}/100"
            if win_probability is not None
            else "—"
        )


        c4, c5, c6 = st.columns(3)

        c4.metric(
            "Client Quality",
            f"{client_quality}/100"
            if client_quality is not None
            else "Unknown"
        )

        c5.metric(
            "Budget Quality",
            f"{budget_quality}/100"
            if budget_quality is not None
            else "Unknown"
        )

        c6.metric(
            "Competition",
            f"{competition_score}/100"
            if competition_score is not None
            else "Unknown"
        )


        st.write(
            "**Category:**",
            category
        )

        st.write(
            "**Decision:**",
            decision
        )


        # ---------------------------------------------
        # SAVE JOB
        # ---------------------------------------------

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

                st.code(str(e))


# =====================================================
# TAB 2 — JOB HISTORY
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

            # =========================================
            # OVERALL METRICS
            # =========================================

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


            total_revenue = sum([
                float(
                    j.get("contract_value")
                    or 0
                )
                for j in jobs
                if j.get("status") == "Hired"
            ])


            col1, col2, col3, col4, col5 = st.columns(5)


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


            # =========================================
            # CATEGORY PERFORMANCE
            # =========================================

            st.divider()

            st.subheader(
                "🏆 Performance by Category"
            )


            categories = [
                "Amazon",
                "Product Retouching",
                "AI + Photoshop",
                "Interior / Architecture",
                "Portrait",
                "Other"
            ]


            category_stats = []


            for category_name in categories:


                category_jobs = [
                    j for j in jobs
                    if j.get("category")
                    == category_name
                ]


                category_applied = [
                    j for j in category_jobs
                    if j.get("status")
                    in [
                        "Applied",
                        "Interview",
                        "Hired"
                    ]
                ]


                category_interviews = [
                    j for j in category_jobs
                    if j.get("status")
                    in [
                        "Interview",
                        "Hired"
                    ]
                ]


                category_hired = [
                    j for j in category_jobs
                    if j.get("status")
                    == "Hired"
                ]


                if len(category_jobs) > 0:


                    if len(category_applied) > 0:

                        category_interview_rate = (
                            len(category_interviews) /
                            len(category_applied) *
                            100
                        )


                        category_hire_rate = (
                            len(category_hired) /
                            len(category_applied) *
                            100
                        )

                    else:

                        category_interview_rate = 0

                        category_hire_rate = 0


                    category_revenue = sum([
                        float(
                            j.get(
                                "contract_value"
                            )
                            or 0
                        )
                        for j in category_jobs
                        if j.get("status")
                        == "Hired"
                    ])


                    category_stats.append({

                        "Category":
                            category_name,

                        "Analyzed":
                            len(category_jobs),

                        "Applied":
                            len(category_applied),

                        "Interviews":
                            len(category_interviews),

                        "Hired":
                            len(category_hired),

                        "Interview Rate":
                            f"{category_interview_rate:.1f}%",

                        "Hire Rate":
                            f"{category_hire_rate:.1f}%",

                        "Value":
                            f"${category_revenue:,.0f}"
                    })


            if category_stats:

                st.dataframe(
                    category_stats,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "Category statistics will appear "
                    "after you save new analyzed jobs."
                )


            # =========================================
            # JOB LIST
            # =========================================

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


                    if job.get("job_url"):

                        st.write(
                            "**Upwork URL:**",
                            job.get(
                                "job_url"
                            )
                        )


                    statuses = [
                        "Not applied",
                        "Applied",
                        "Interview",
                        "Hired",
                        "Rejected"
                    ]


                    if job_status not in statuses:
                        job_status = "Not applied"


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

                            st.code(str(e))


    except Exception as e:

        st.error(
            "Could not load Job History."
        )

        st.code(str(e))

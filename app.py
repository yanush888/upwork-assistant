import streamlit as st
from openai import OpenAI

st.set_page_config(
    page_title="Upwork Opportunity Assistant",
    page_icon="🎯",
    layout="centered"
)

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("🎯 Upwork Opportunity Assistant")

st.write(
    "Paste an Upwork job description below. "
    "The assistant will evaluate whether it is worth applying."
)

job_description = st.text_area(
    "Upwork Job Description",
    height=350,
    placeholder="Paste the full Upwork job description here..."
)

if st.button("Analyze Job", type="primary"):

    if not job_description.strip():
        st.warning("Please paste a job description first.")

    else:
        with st.spinner("Analyzing the job..."):

            prompt = f"""
You are an Upwork opportunity analyst for a freelance specialist.

Freelancer profile:
- High-end photo retoucher
- Photoshop expert
- AI image specialist
- Product and Amazon image specialist
- Architectural and interior photo retouching
- Photorealistic AI compositing
- Strong at combining AI generation with manual Photoshop finishing
- Prefers higher-value projects over low-budget repetitive work
- Wants long-term clients where possible

Analyze the following Upwork job:

{job_description}

Return your analysis in this exact structure:

OPPORTUNITY SCORE: X/100

RECOMMENDATION:
Choose one:
HIGH PRIORITY — APPLY
GOOD — APPLY
MAYBE
SKIP

SKILL MATCH:
X/100

CLIENT QUALITY:
X/100 or "Unknown"

BUDGET QUALITY:
X/100 or "Unknown"

COMPETITION:
Low / Medium / High / Unknown

WHY THIS JOB IS A GOOD FIT:
- point
- point
- point

RISKS:
- point
- point

RECOMMENDED BID:
Give a realistic bid or hourly rate. If insufficient information, say so.

PORTFOLIO TO SHOW:
Recommend 2-3 types of portfolio examples that would best match this job.

PROPOSAL:
Write a short, personalized Upwork proposal of approximately 100-150 words.
Do not sound generic.
Start by addressing the client's actual problem.
Focus on photographic realism, relevant expertise, and how the job would be approached.
Do not exaggerate experience.
"""

            response = client.responses.create(
                model="gpt-5-mini",
                input=prompt
            )

            result = response.output_text

        st.success("Analysis complete")
        st.markdown(result)

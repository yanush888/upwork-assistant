import streamlit as st
from openai import OpenAI

st.set_page_config(
    page_title="Upwork Opportunity Assistant",
    page_icon="🎯",
    layout="centered"
)

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("🎯 Upwork Opportunity Assistant")

st.caption(
    "Personalized job scoring for Amazon Images, Photo Retouching, "
    "AI + Photoshop and photorealistic compositing projects."
)

job_description = st.text_area(
    "Paste Upwork Job Description",
    height=420,
    placeholder="Paste the full Upwork job description here..."
)

if st.button("Analyze Job", type="primary", use_container_width=True):

    if not job_description.strip():
        st.warning("Please paste a job description first.")

    else:
        with st.spinner("Analyzing opportunity..."):

            prompt = f"""
You are a senior Upwork opportunity analyst.

Your job is NOT simply to determine whether the freelancer technically
can perform the work.

Your job is to determine whether this is a GOOD BUSINESS OPPORTUNITY
for this specific freelancer and whether they have a realistic
competitive advantage.

FREELANCER PROFILE

Positioning:
Amazon Listing Images Expert
High-End Photo Retoucher
Photo Editor
AI Image Specialist / AI Artist

Main strengths:
- Amazon listing image creation and editing
- E-commerce product photography and product retouching
- High-end Photoshop retouching
- Natural portrait retouching
- AI-generated imagery combined with manual Photoshop finishing
- Photorealistic AI compositing
- Product replacement and product integration into lifestyle scenes
- Maintaining correct product proportions, texture and geometry
- Interior and architectural photo manipulation
- Furniture replacement and realistic object integration
- Background replacement
- Complex image compositing
- Strong eye for photographic realism
- Correcting typical AI artifacts
- Consistency across image series

Competitive advantage:
The freelancer is especially strong when pure AI generation is not
good enough and manual Photoshop finishing is required to achieve
realistic professional photography.

Upwork profile signals:
- Top Rated
- 100% Job Success
- 5-star profile
- strong completed-job history
- experienced freelancer

BUSINESS STRATEGY

Prioritize:
1. Amazon / e-commerce product images
2. AI + Photoshop photorealistic work
3. High-end photo retouching
4. Product/lifestyle compositing
5. Architectural/interior photo manipulation
6. Recurring or long-term image production

Prefer:
- professional clients
- agencies
- established companies
- clients with previous Upwork spending
- repeat work
- projects where quality matters
- jobs where AI + Photoshop provides an advantage
- projects that can lead to long-term work

Penalize:
- extremely low budgets
- large image quantities with unrealistic budgets
- commodity Photoshop work
- jobs where price is clearly the primary selection factor
- excessive unpaid tests
- unclear scope
- unrealistic deadlines
- clients interviewing many freelancers already
- jobs with huge proposal volume unless the freelancer has a very
  strong competitive advantage

IMPORTANT:
Skill Match and Opportunity Score are NOT the same.

Example:
A project may be a 98/100 skill match but only a 50/100 opportunity
if the client wants 70 images for $100.

SCORING

Calculate:

SKILL MATCH: 0-100
How closely the work matches the freelancer's strongest skills.

CLIENT QUALITY: 0-100
Consider previous spending, hiring history, professionalism,
clarity and probability of becoming a good client.
If information is missing, say "Unknown".

BUDGET QUALITY: 0-100
Evaluate compensation relative to scope and freelancer level.
Do not reward low-paying projects just because they are easy.

COMPETITION SCORE: 0-100
100 means very favorable competition.
0 means extremely unfavorable.
Consider proposals, interviews, invitations and how recently
the job was posted.
If information is missing, say "Unknown".

WIN PROBABILITY: 0-100
Estimate how likely THIS freelancer is to stand out versus other
applicants based on specialization, profile strength and client need.

OPPORTUNITY SCORE: 0-100
This is the final business-value score.

Suggested weighting:
Skill Match: 25%
Client Quality: 20%
Budget Quality: 20%
Competition: 15%
Win Probability: 20%

However, use judgment where necessary.

DECISION RULES

90-100:
🔥 APPLY NOW

80-89:
🟢 APPLY

65-79:
🟡 MAYBE

0-64:
🔴 SKIP

Be selective.
Do not inflate scores just because the freelancer can perform the work.

Analyze this Upwork job:

---------------- JOB ----------------

{job_description}

-------------------------------------

Return the answer using EXACTLY this structure:

OPPORTUNITY SCORE: X/100

DECISION:
🔥 APPLY NOW
or
🟢 APPLY
or
🟡 MAYBE
or
🔴 SKIP

SKILL MATCH:
X/100

CLIENT QUALITY:
X/100 or Unknown

BUDGET QUALITY:
X/100 or Unknown

COMPETITION SCORE:
X/100 or Unknown

WIN PROBABILITY:
X/100

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
State "None" if there are no major deal breakers.
Otherwise list them.

RECOMMENDED BID:
Give a realistic pricing recommendation.
Consider the freelancer's seniority and do not automatically compete
at the bottom of the client's range.

PORTFOLIO TO SHOW:
1. portfolio type
2. portfolio type
3. portfolio type

APPLICATION STRATEGY:
Give 2-4 short tactical recommendations for applying to this exact job.

PROPOSAL:
Write a personalized Upwork proposal of around 100-140 words.

Proposal rules:
- Do not begin with generic phrases such as
  "I am excited to apply"
- Start with the client's actual problem
- Sound human and confident
- Mention only skills directly relevant to this project
- Do not exaggerate
- Avoid long lists of software
- Focus on outcome and realism
- If useful, mention combining AI with Photoshop
- End with a simple call to action
"""

            try:
                response = client.responses.create(
                    model="gpt-5-mini",
                    input=prompt
                )

                result = response.output_text

                st.success("Analysis complete")
                st.markdown(result)

            except Exception as e:
                st.error(
                    "The AI analysis could not be completed. "
                    "Please try again or check the API settings."
                )
                st.code(str(e))

import streamlit as st

st.set_page_config(
    page_title="Upwork Opportunity Assistant",
    page_icon="🎯",
    layout="centered"
)

st.title("🎯 Upwork Opportunity Assistant")

st.write(
    "Paste an Upwork job description below and I will help you "
    "decide whether it's worth applying."
)

job_description = st.text_area(
    "Upwork Job Description",
    height=300,
    placeholder="Paste the job description here..."
)

if st.button("Analyze Job", type="primary"):

    if not job_description:
        st.warning("Please paste a job description first.")

    else:
        st.success("Job received successfully!")

        st.subheader("Opportunity Score")

        st.metric(
            label="Match Score",
            value="89 / 100"
        )

        st.progress(89)

        st.subheader("Recommendation")
        st.write("🟢 HIGH PRIORITY — APPLY")

        st.subheader("Why this job may be a good fit")

        st.write("""
        ✓ Relevant to your skills  
        ✓ Potentially good client  
        ✓ Good portfolio match  
        ✓ Worth further analysis
        """)

        st.info(
            "This is the first test version. "
            "AI analysis will be added next."
        )

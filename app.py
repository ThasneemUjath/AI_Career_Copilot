import html
import json
import uuid
from pathlib import Path

import streamlit as st

from profile_extractor import extract_profile
from job_extractor import extract_job
from matcher import match
from resume_builder import build_resume, render_markdown
from mcp_client import call_tool
from orchestrator import run_agent
from interview_coach import generate_questions, evaluate_answer
from resume_export import to_docx_bytes, to_pdf_bytes

st.set_page_config(page_title="AI Career Copilot", page_icon="🧭", layout="wide")

ss = st.session_state
ss.setdefault("sid", uuid.uuid4().hex)   # private id: keys this visitor's saved data

LEVELS = {"Fresher / intern (0-1 yrs)": "entry",
          "Junior (1-3 yrs)": "mid",
          "Experienced (3+ yrs)": "senior"}

REC = {"HIGH_PRIORITY": ("High priority", "green"),
       "MEDIUM_PRIORITY": ("Medium priority", "amber"),
       "LOW_PRIORITY": ("Low priority", "red")}

BREAKDOWN_LABELS = {"required_skills": "Required skills",
                    "project_evidence": "Project evidence",
                    "preferred_skills": "Preferred skills",
                    "level_fit": "Level fit"}

# ---------- styling ----------
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
section[data-testid="stSidebar"] .stButton > button {width: 100%;}
.hero h1 {margin-bottom: 0; font-size: 2.2rem;}
.hero p {margin-top: 0.2rem; opacity: 0.7;}
.chip {display: inline-block; padding: 2px 11px; margin: 3px 5px 3px 0; border-radius: 999px;
       font-size: 0.85rem; border: 1px solid; white-space: normal;
       overflow-wrap: anywhere; max-width: 100%;}
.chip-green {background: rgba(34,160,90,.14); color: #1f9d57; border-color: rgba(34,160,90,.45);}
.chip-red   {background: rgba(214,69,69,.14); color: #d64545; border-color: rgba(214,69,69,.45);}
.chip-amber {background: rgba(217,142,4,.14); color: #c27c00; border-color: rgba(217,142,4,.45);}
.chip-blue  {background: rgba(79,70,229,.12); color: #4f46e5; border-color: rgba(79,70,229,.4);}
.chip-gray  {background: rgba(128,128,128,.14); color: inherit; border-color: rgba(128,128,128,.4);}
.muted {opacity: 0.65; font-size: 0.9rem;}
.bignum {font-size: 3rem; font-weight: 700; line-height: 1.1;}
.good {color: #1f9d57;} .warn {color: #c27c00;} .bad {color: #d64545;}
</style>
""", unsafe_allow_html=True)


# ---------- helpers ----------
def chip(text, color="gray"):
    return f"<span class='chip chip-{color}'>{html.escape(str(text))}</span>"


def chips(items, color="gray"):
    if not items:
        return "<span class='muted'>None</span>"
    return "".join(chip(i, color) for i in items)


def show_chips(label, items, color):
    st.markdown(f"**{label}**")
    st.markdown(chips(items, color), unsafe_allow_html=True)


def match_class(score):
    return "good" if score >= 75 else "warn" if score >= 50 else "bad"


def interview_class(avg):
    return "good" if avg >= 4 else "warn" if avg >= 3 else "bad"


def get_weak(cand):
    """Weak topics are cached per candidate so other tabs don't hit the database on every rerun."""
    cache = ss.setdefault("weak_cache", {})
    if cand not in cache:
        cache[cand] = json.loads(call_tool("db", "get_weak_topics", {"candidate": cand}) or "[]")
    return cache[cand]


def download_buttons(t, profile, key):
    """Word, PDF and Markdown downloads for an approved resume."""
    name = (profile.name or "resume").strip().replace(" ", "_")
    b1, b2, b3 = st.columns(3)
    b1.download_button("⬇ Word (.docx)", to_docx_bytes(t, profile), f"{name}_resume.docx",
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                       key=f"{key}_docx")
    b2.download_button("⬇ PDF", to_pdf_bytes(t, profile), f"{name}_resume.pdf",
                       "application/pdf", key=f"{key}_pdf")
    b3.download_button("⬇ Markdown (.md)", render_markdown(t, profile), f"{name}_resume.md",
                       key=f"{key}_md")


# ---------- sidebar: all inputs live here ----------
with st.sidebar:
    st.markdown("## 🧭 Career Copilot")
    st.caption("Resume → match → tailor → practice")

    st.markdown("### 1. Your resume")
    file = st.file_uploader("Upload resume (PDF)", type=["pdf"], label_visibility="collapsed")
    if st.button("Analyze resume", type="primary"):
        if not file:
            st.warning("Upload a PDF first.")
        else:
            try:
                uploads = Path(__file__).parent / "uploads"
                uploads.mkdir(exist_ok=True)
                saved_name = f"{ss['sid'][:8]}_{Path(file.name).name}"   # unique per visitor
                (uploads / saved_name).write_bytes(file.getvalue())

                try:
                    text = call_tool("files", "read_resume", {"path": saved_name})   # via MCP
                finally:
                    (uploads / saved_name).unlink(missing_ok=True)   # do not keep resumes on disk
                ss["raw_text"] = text
                if not text:
                    st.error("No text found. This may be a scanned PDF.")
                else:
                    with st.spinner("Building your profile..."):
                        profile, removed = extract_profile(text)
                    # a new resume makes the old match, draft and interview stale
                    for k in ("result", "tailored", "tailored_issues", "iv", "agent_state"):
                        ss.pop(k, None)
                    ss["profile"] = profile
                    ss["removed"] = removed
                    call_tool("db", "save_candidate_profile",
                              {"sid": ss["sid"], "profile_json": profile.model_dump_json()})   # via MCP
                    st.toast("Profile ready")
            except Exception as e:
                st.error(f"Could not analyze the resume: {e}")

    st.markdown("### 2. Job description")
    st.text_area("Paste the job description", key="jd_text", height=220,
                 label_visibility="collapsed",
                 placeholder="Paste the full job description here...")
    n_chars = len(ss.get("jd_text", "").strip())
    st.caption(f"JD captured: {n_chars} characters"
               + ("" if n_chars else " (click outside the box after pasting)"))
    st.selectbox("Your experience level", list(LEVELS), key="level_label")

    if st.button("Match me", type="primary"):
        jd = ss.get("jd_text", "").strip()
        if ss.get("profile") is None:
            st.warning("Analyze your resume first.")
        elif not jd:
            st.warning("Paste a job description first.")
        else:
            try:
                with st.spinner("Analyzing job..."):
                    cache = ss.setdefault("job_cache", {})
                    if jd not in cache:
                        cache[jd] = extract_job(jd)
                        call_tool("db", "save_job",
                                  {"sid": ss["sid"], "job_json": cache[jd].model_dump_json()})
                    job = cache[jd]
                    ss["job"] = job
                    ss["result"] = match(ss["profile"], job, LEVELS[ss["level_label"]])
                # a draft or interview made for the previous job is stale
                for k in ("tailored", "tailored_issues", "iv"):
                    ss.pop(k, None)
                st.toast("Match ready: open the Job match tab")
            except Exception as e:
                st.error(f"Could not analyze the job: {e}")

    st.divider()
    st.toggle("Developer mode", key="dev_mode",
              help="Show raw extracted text and JSON for debugging.")
    status_box = st.empty()

# ---------- shared state for the copilot chat (same JD and level as the sidebar) ----------
state = ss.setdefault("agent_state", {})
if "profile" in ss:
    state["profile"] = ss["profile"]
state["jd"] = ss.get("jd_text", "")
state["sid"] = ss["sid"]
state["level"] = LEVELS[ss["level_label"]]

# ---------- header ----------
st.markdown("<div class='hero'><h1>AI Career Copilot</h1>"
            "<p>Match your resume to a job, tailor it honestly, and practise the interview.</p></div>",
            unsafe_allow_html=True)

tab_profile, tab_match, tab_resume, tab_iv, tab_chat = st.tabs(
    ["👤 Profile", "🎯 Job match", "📄 Tailored resume", "🎤 Mock interview", "💬 Copilot"])

# =====================================================================
# Profile
# =====================================================================
with tab_profile:
    p = ss.get("profile")
    if p is None:
        st.info("👈 Upload your resume in the sidebar and click **Analyze resume** to begin.")
    else:
        st.subheader(p.name or "Candidate")
        contact = " · ".join(x for x in [p.email, p.phone, p.linkedin, p.github] if x)
        if contact:
            st.caption(contact)
        if p.objective:
            st.write(p.objective)
        if ss.get("removed"):
            st.warning("Removed because they were not found in your resume: "
                       + ", ".join(ss["removed"]))

        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                show_chips("Technical skills", p.technical_skills, "blue")
                show_chips("Soft skills", p.soft_skills, "gray")
            with st.container(border=True):
                st.markdown("**Education**")
                if not p.education:
                    st.caption("None found")
                for e in p.education:
                    st.write(f"{e.degree}, {e.institution} ({e.year})")
            if p.certifications or p.achievements:
                with st.container(border=True):
                    if p.certifications:
                        st.markdown("**Certifications**")
                        for c in p.certifications:
                            st.write(f"- {c}")
                    if p.achievements:
                        st.markdown("**Achievements**")
                        for a in p.achievements:
                            st.write(f"- {a}")
        with c2:
            with st.container(border=True):
                st.markdown("**Experience**")
                if not p.experience:
                    st.caption("None found")
                for e in p.experience:
                    st.write(f"**{e.role}**, {e.company} ({e.duration})")
                    for h in e.highlights:
                        st.write(f"- {h}")
            with st.container(border=True):
                st.markdown("**Projects**")
                if not p.projects:
                    st.caption("None found")
                for pr in p.projects:
                    st.write(f"**{pr.name}**")
                    if pr.technologies:
                        st.markdown(chips(pr.technologies, "blue"), unsafe_allow_html=True)
                    if pr.description:
                        st.caption(pr.description)

        if p.missing_info:
            with st.expander("Sections not found in the resume"):
                for m in p.missing_info:
                    st.write(f"- {m}")
        if ss.get("dev_mode"):
            with st.expander("Full profile (JSON)"):
                st.json(p.model_dump())
            with st.expander("Raw extracted text (debug)"):
                st.text(ss.get("raw_text", ""))

# =====================================================================
# Job match
# =====================================================================
with tab_match:
    r, job = ss.get("result"), ss.get("job")
    if r is None or job is None:
        st.info("👈 Add a job description in the sidebar and click **Match me**.")
    else:
        st.subheader(f"{job.title or 'Job'}" + (f" · {job.company}" if job.company else ""))
        score = r["match_score"]
        label, color = REC.get(r["recommendation"], (r["recommendation"], "gray"))

        with st.container(border=True):
            s1, s2 = st.columns([1, 3])
            s1.markdown(f"<div class='bignum {match_class(score)}'>{score}%</div>"
                        "<div class='muted'>Technical match</div>", unsafe_allow_html=True)
            with s2:
                st.markdown(chip(label, color), unsafe_allow_html=True)
                st.progress(min(max(int(score), 0), 100))
                st.caption("Scores hard skills and experience level only. Soft skills, education "
                           "and institute preferences are shown but not scored.")

        if r["low_confidence"]:
            st.warning(f"Low confidence: only {r['n_requirements']} technical requirement(s), "
                       f"so the score is capped at 60 (uncapped: {r['raw_score']}).")

        if r["breakdown"]:
            cols = st.columns(len(r["breakdown"]))
            for col, (k, v) in zip(cols, r["breakdown"].items()):
                col.metric(BREAKDOWN_LABELS.get(k, k), f"{v}")
            st.caption("Points each part contributed to the score, before any cap.")

        k1, k2 = st.columns(2)
        with k1:
            with st.container(border=True):
                show_chips("✅ Matched required", r["matched_required"], "green")
                show_chips("✅ Matched preferred", r["matched_preferred"], "green")
                show_chips("🛠 Proven in your projects", r.get("skills_proven_in_projects", []), "blue")
        with k2:
            with st.container(border=True):
                show_chips("❌ Missing required", r["missing_required"], "red")
                show_chips("⚠️ Missing preferred", r["missing_preferred"], "amber")

        if r.get("related_evidence"):
            with st.container(border=True):
                st.markdown("**🔎 Missing as a skill, but related terms appear in your resume** "
                            "(not scored)")
                for skill, terms in r["related_evidence"].items():
                    st.markdown(f"{html.escape(skill)}: " + chips(terms, "amber"),
                                unsafe_allow_html=True)
                st.caption("These terms are only nearby evidence. They do not count as the skill.")

        with st.container(border=True):
            st.markdown("**📋 Experience requirements**")
            if job.experience_requirements:
                for x in job.experience_requirements:
                    st.write(f"- {x}")
            else:
                st.caption("None stated")
            show_chips("🤝 Soft skills wanted", job.soft_skills, "gray")

        if ss.get("dev_mode"):
            with st.expander("Extracted job requirements (JSON)"):
                st.json(job.model_dump())

# =====================================================================
# Tailored resume
# =====================================================================
with tab_resume:
    if "result" not in ss or "profile" not in ss:
        st.info("Analyze your resume and match a job first. The draft is tailored to that job.")
    else:
        st.caption("The draft uses only facts from your profile and is checked for invented "
                   "skills, names and numbers. You approve it before it can be downloaded.")
        if st.button("Generate tailored resume", type="primary"):
            try:
                with st.spinner("Writing resume..."):
                    t, issues = build_resume(ss["profile"], ss["job"])
                ss["tailored"] = t
                ss["tailored_issues"] = issues
            except Exception as e:
                st.error(f"Could not generate the resume: {e}")

        if "tailored" in ss:
            issues = ss["tailored_issues"]
            if issues:
                st.error("Faithfulness check failed. Review before using:\n- " + "\n- ".join(issues))
            else:
                st.success("Faithfulness check passed: no invented skills, names or numbers detected.")

            md = render_markdown(ss["tailored"], ss["profile"])
            with st.container(border=True):
                st.markdown(md)

            if st.checkbox("I have reviewed this resume and approve it", key="approve_main"):
                download_buttons(ss["tailored"], ss["profile"], "main")
                if st.button("Save markdown copy to outputs folder", key="save_main"):
                    st.success("Saved: " + call_tool("files", "save_document",
                                                     {"filename": f"{ss['sid'][:8]}_tailored_resume.md", "content": md}))

# =====================================================================
# Mock interview
# =====================================================================
with tab_iv:
    if ss.get("profile") is None or ss.get("job") is None:
        st.info("Analyze your resume and click **Match me** first. The interview uses that job.")
    else:
        cand = ss["sid"]   # interview history is keyed by this visitor's private id
        weak = get_weak(cand)

        st.caption(f"Level: {ss['level_label']} (change it in the sidebar)")
        c1, c2 = st.columns(2)
        n_q = c1.slider("Number of questions", 3, 8, 5, key="iv_n")
        focus = c2.checkbox("Focus on my weak topics", value=bool(weak), key="iv_focus")

        st.markdown("**Weak topics so far**")
        st.markdown(chips([f"{w['topic']} {w['avg_score']}/5" for w in weak], "red")
                    if weak else "<span class='muted'>None yet</span>", unsafe_allow_html=True)

        if st.button("Start interview", type="primary"):
            try:
                with st.spinner("Preparing questions..."):
                    qs = generate_questions(ss["profile"], ss["job"], n=n_q,
                                            level=LEVELS[ss["level_label"]],
                                            priority_topics=[w["topic"] for w in weak] if focus else None)
                ss["iv"] = {"qs": qs, "i": 0, "eval": None, "scores": [], "log": [],
                            "level": LEVELS[ss["level_label"]]}
            except Exception as e:
                st.error(f"Could not prepare questions: {e}")

        iv = ss.get("iv")
        if iv is not None and not iv["qs"]:
            st.warning("No valid questions were generated. Try again.")
        elif iv is not None:
            def _next():
                iv["i"] += 1
                iv["eval"] = None

            st.divider()
            total = len(iv["qs"])

            if iv["i"] >= total:
                avg = sum(iv["scores"]) / len(iv["scores"]) if iv["scores"] else 0
                with st.container(border=True):
                    st.markdown("### Interview finished")
                    st.markdown(f"<div class='bignum {interview_class(avg)}'>{avg:.1f} / 5</div>"
                                "<div class='muted'>Average score</div>", unsafe_allow_html=True)
                    st.markdown("".join(chip(f"{t} {s:.1f}",
                                             "green" if s >= 4 else "amber" if s >= 3 else "red")
                                        for t, s in iv["log"]), unsafe_allow_html=True)
                    st.caption("Your weak topics are updated for the next session.")
            else:
                q = iv["qs"][iv["i"]]
                st.progress(iv["i"] / total, text=f"Question {iv['i'] + 1} of {total}")
                with st.container(border=True):
                    st.markdown(chip(q.topic, "blue"), unsafe_allow_html=True)
                    st.markdown(f"#### {q.question}")
                    answer = st.text_area("Your answer", key=f"iv_ans_{iv['i']}", height=150,
                                          disabled=iv["eval"] is not None)

                if iv["eval"] is None:
                    if st.button("Submit answer"):
                        try:
                            with st.spinner("Evaluating..."):
                                ev = evaluate_answer(q.topic, q.question, answer, level=iv["level"])
                                call_tool("db", "save_interview_result", {
                                    "candidate": cand,
                                    "topic": q.topic, "question": q.question, "answer": answer,
                                    "concept": ev.concept, "accuracy": ev.accuracy,
                                    "clarity": ev.clarity, "feedback": ev.feedback})
                            avg_q = (ev.concept + ev.accuracy + ev.clarity) / 3
                            iv["eval"] = ev
                            iv["scores"].append(avg_q)
                            iv["log"].append((q.topic, avg_q))
                            ss.get("weak_cache", {}).pop(cand, None)   # refresh weak topics
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not evaluate the answer: {e}")
                else:
                    ev = iv["eval"]
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Concept", f"{ev.concept}/5")
                    m2.metric("Accuracy", f"{ev.accuracy}/5")
                    m3.metric("Clarity", f"{ev.clarity}/5")
                    st.markdown(f"**Feedback:** {ev.feedback}")
                    if ev.follow_up:
                        st.info(f"💭 Think about: {ev.follow_up}")
                    st.button("Finish" if iv["i"] + 1 >= total else "Next question", on_click=_next)

# =====================================================================
# Copilot chat
# =====================================================================
with tab_chat:
    if not ss.get("jd_text", "").strip():
        st.info("Paste a job description in the sidebar to ask about your fit. "
                "You can still ask about your resume and weak topics.")
    else:
        st.caption(f"Using the job description and level from the sidebar "
                   f"({len(ss['jd_text'].strip())} characters, {ss['level_label']}).")

    history = ss.setdefault("chat", [])
    for m in history:
        st.chat_message(m["role"]).write(m["content"])

    prompt = st.chat_input("e.g. How well do I fit this job? Then prepare my resume for it.")
    if prompt:
        st.chat_message("user").write(prompt)
        try:
            with st.spinner("Thinking..."):
                answer, trace = run_agent(prompt, state, history)
        except Exception as e:
            st.error(f"The copilot hit an error (the model service may be rate limited). Try again in a moment. Details: {e}")
        else:
            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": answer})
            st.chat_message("assistant").write(answer)
            with st.expander("What the agent did"):
                for line in trace:
                    st.write(line)

    if state.get("tailored"):
        st.divider()
        st.subheader("Tailored resume draft")
        issues = state.get("issues", [])
        if issues:
            st.error("Faithfulness check failed. Review before using:\n- " + "\n- ".join(issues))
        else:
            st.success("Faithfulness check passed.")
        agent_md = render_markdown(state["tailored"], state["profile"])
        with st.container(border=True):
            st.markdown(agent_md)
        if st.checkbox("I have reviewed and approve this resume", key="agent_approve"):
            download_buttons(state["tailored"], state["profile"], "agent")

# ---------- sidebar progress checklist (filled last so it is always current) ----------
with status_box.container():
    st.markdown("**Progress**")
    for key, text in [("profile", "Resume analyzed"), ("result", "Job matched"),
                      ("tailored", "Resume tailored"), ("iv", "Interview started")]:
        st.markdown(("✅ " if key in ss else "⬜ ") + text)
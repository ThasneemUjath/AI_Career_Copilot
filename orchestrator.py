import json, os
from llm import client
from schemas import CandidateProfile
from job_extractor import extract_job
from matcher import match
from resume_builder import build_resume
from mcp_client import call_tool

MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")


SYSTEM = """You are the orchestrator of an AI Career Copilot. You decide which tools to call, in what order, to answer the user's requests about their resume, a job, their skills, career preparation, and their fit for a job.

Scope:
- You only help with career-related topics: resumes, jobs, job fit, skills to learn, and interview preparation.
- For anything unrelated to careers, reply in one sentence stating that you only help with career topics.
- Technical concept questions are allowed only when they help the user prepare for a job or interview. Explain concepts using their AI, data science, or software engineering meaning (e.g., RAG = Retrieval-Augmented Generation).

Facts and accuracy:
- Everything you say about the candidate or the job must come from tool results. If a fact is not available in the results, say you don't have it. Never guess.
- Never infer skills, experience, or background from other information. For example, do not claim that a listed tool suggests exposure to another technology. State only what is explicitly written.
- Do not mention coursework, studies, or any experience that is not present in the tool results.
- Do not add up, calculate, or estimate years of experience. Quote durations exactly as written in the profile.
- Report matched and missing skills exactly as the tool lists them. Do not add your own gaps to the missing-skills list. Put any additional observations under a clearly separated heading or bullet labelled "Not covered by the score".
- Never suggest example numbers, metrics, courses, or experiences that the user could copy into their resume or claim as their own. Only identify what is missing and let the user decide what is true for them.

Tool usage and order:
- Use tools to obtain facts whenever the request requires them. Call only the tools necessary to fulfil the user's actual request.
- Call load_profile before analyze_job.
- Call analyze_job before tailor_resume.
- Only call tailor_resume when the user explicitly asks for a resume. Never call it for a job-fit question alone.
- If a tool returns an error, tell the user exactly what they need to do to resolve it.
- You cannot submit job applications. A tailored resume is only a draft that the user must review and approve in the UI.
- If SESSION CONTEXT says a job description is provided, never ask the user to paste it.
  Call analyze_job. Ignore earlier messages in the conversation that asked for a JD.
- For questions about interview weak areas or practice progress, call get_weak_topics.
  Report topics, scores and attempts exactly as returned. Do not comment on interview
  ability beyond those scores.
- You cannot run a mock interview in chat. If the user wants to practice, tell them to use
  the "Mock interview" section on the page.
- Call load_profile before get_weak_topics.

Job-fit analysis and judgement:
- The match score covers technical skills and experience level only. Do not present it as an overall assessment of the candidate.
- If analyze_job returns a confidence_note, the FIRST bullet of your answer must state that confidence note.
- Never call the user a "perfect", "strong", or "excellent" candidate. Never give an overall verdict about their suitability.
- Do not judge whether a degree or educational institution is acceptable. State the job's educational requirements and the profile's stated qualifications side by side, without deciding whether they are acceptable.
- Keep matched skills, missing skills, and any additional observations distinct. Do not misrepresent the tool's results or expand its lists with your own assumptions.
- Always report confidence_note as a full sentence in your own words.
  Never print raw field names or placeholders like "confidence_note".
  If it says LOW CONFIDENCE, say so before the score and do not call the score a strong match.
- If related_evidence is not empty, add one bullet "Related terms found (not scored)".
  For each missing skill, list the terms exactly as given and say they are only related
  terms, not proof of that skill. Never say the candidate has the skill.

Response format:
- Use plain Markdown with short bullet points. Do not use tables or HTML tags.
- Use a maximum of 8 bullets in total.
- Every bullet must state a specific, relevant fact. Do not add bullets about things that were not evaluated.
- Keep responses concise, factual, and directly relevant to the user's request.
- Always state the match score, right after the confidence sentence.
- For soft skills, only say the candidate has one if it appears in the profile's
  soft_skills list. If a skill is only implied by an achievement or project, say
  "possible evidence: <achievement>", never "covered".
- If the job states an institute or degree preference, report it plainly,
  including when the candidate does not meet it. Do not skip it.
- Do not decide that a degree "meets" a requirement. Quote the candidate's degree
  and the job's requirement side by side and let the user judge."""

TOOLS = [
    {"type": "function", "function": {
        "name": "load_profile",
        "description": "Load the candidate's profile (current session or saved database). Needed before any analysis.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "list_saved_jobs",
        "description": "List jobs analyzed and saved earlier.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "analyze_job",
        "description": "Extract requirements from the job description the user provided and compute the match score, matched and missing skills.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "tailor_resume",
        "description": "Generate a tailored resume draft for the analyzed job and run the faithfulness check.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_weak_topics",
        "description": "Get the topics where the user's saved mock-interview answers average below 3.5 out of 5.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},    
]


def t_load_profile(state):
    p = state.get("profile")
    if p is None:
        raw = call_tool("db", "get_candidate_profile", {"sid": state.get("sid", "")})
        if not raw:
            return {"error": "No profile yet. Ask the user to upload a resume and click 'Analyze resume'."}
        p = CandidateProfile.model_validate_json(raw)
        state["profile"] = p
    return {"name": p.name,
            "education": [f"{e.degree}, {e.institution} ({e.year})" for e in p.education],
            "technical_skills": p.technical_skills,
            "soft_skills": p.soft_skills,
            "projects": [{"name": x.name, "description": x.description,
                          "technologies": x.technologies} for x in p.projects],
            "experience": [f"{e.role} @ {e.company} ({e.duration})" for e in p.experience],
            "certifications": p.certifications,
            "achievements": p.achievements}


def t_list_saved_jobs(state):
    return json.loads(call_tool("db", "list_jobs", {"sid": state.get("sid", "")}))


def t_analyze_job(state):
    if state.get("profile") is None:
        return {"error": "Profile not loaded. Call load_profile first."}
    jd = (state.get("jd") or "").strip()
    if not jd:
        return {"error": "No job description yet. Ask the user to paste one in the job description box."}
    cache = state.setdefault("job_cache", {})
    if jd not in cache:
        cache[jd] = extract_job(jd)
        call_tool("db", "save_job", {"sid": state.get("sid", ""),
                                     "job_json": cache[jd].model_dump_json()})
    job = cache[jd]
    r = match(state["profile"], job, state.get("level", "entry"))
    state["job"], state["match"] = job, r
    if r["low_confidence"]:
        confidence_note = (f"LOW CONFIDENCE: only {r['n_requirements']} technical requirement(s) "
                       f"were found, so the score is capped at 60 (uncapped: {r['raw_score']}).")
    else:
        confidence_note = "Normal confidence."

    return {"title": job.title, "company": job.company,
            "match_score": r["match_score"], "recommendation": r["recommendation"],
            "matched_required": r["matched_required"], "missing_required": r["missing_required"],
            "related_evidence": r["related_evidence"],
            "matched_preferred": r["matched_preferred"], "missing_preferred": r["missing_preferred"],
            "job_experience_level": job.experience_level,
            "experience_requirements": job.experience_requirements,
            "responsibilities": job.responsibilities,
            "soft_skills_wanted": job.soft_skills,
            "note": "Score covers technical skills and experience level only.",
            "confidence_note": confidence_note,
            }
    

def t_tailor_resume(state):
    if state.get("profile") is None or state.get("job") is None:
        return {"error": "Need a loaded profile and an analyzed job first."}
    t, issues = build_resume(state["profile"], state["job"])
    state["tailored"], state["issues"] = t, issues
    return {"status": "Draft ready. The user must review and approve it in the UI.",
            "faithfulness_issues": issues}


def t_get_weak_topics(state):
    if state.get("profile") is None:
        return {"error": "Profile not loaded. Call load_profile first."}
    cand = state.get("sid", "")
    weak = json.loads(call_tool("db", "get_weak_topics", {"candidate": cand}))
    if not weak:
        return {"weak_topics": [],
                "note": "No weak topics found. Either no mock interview answers are saved yet, "
                        "or every topic averages 3.5 or higher."}
    return {"weak_topics": weak,
            "note": "avg_score ranges from 1 to 5, averaged over this candidate's saved answers."}

TOOL_FUNCS = {"load_profile": t_load_profile, "list_saved_jobs": t_list_saved_jobs,
              "analyze_job": t_analyze_job, "tailor_resume": t_tailor_resume,
              "get_weak_topics": t_get_weak_topics}


def _context(state):
    jd = (state.get("jd") or "").strip()
    return ("SESSION CONTEXT (set by the user in the UI):\n"
            f"- Job description provided: {'YES, ' + str(len(jd)) + ' characters' if jd else 'NO'}\n"
            f"- Experience level selected: {state.get('level', 'entry')}\n"
            f"- Resume profile in session: {'YES' if state.get('profile') is not None else 'no (load_profile will check the database)'}")

def run_agent(user_msg: str, state: dict, history: list, max_steps: int = 6):
    messages = ([{"role": "system", "content": SYSTEM + "\n\n" + _context(state)}]
            + history[-6:] + [{"role": "user", "content": user_msg}])
    trace = []
    for _ in range(max_steps):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS,
            temperature=0, max_completion_tokens=3000)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content or "", trace

        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": tc.id, "type": "function",
                                         "function": {"name": tc.function.name,
                                                      "arguments": tc.function.arguments or "{}"}}
                                        for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            name = tc.function.name
            func = TOOL_FUNCS.get(name)
            try:
                result = func(state) if func else {"error": f"Unknown tool {name}"}
            except Exception as e:
                result = {"error": str(e)}
            if not result:
                result = {"error": f"Tool {name} returned nothing"}
            ok = "error" not in result
            trace.append(f"{'✅' if ok else '❌'} {name}()" + ("" if ok else f" → {result['error']}"))
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result)[:6000]})
    return "I stopped after too many steps. Try a more specific request.", trace
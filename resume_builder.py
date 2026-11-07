import json, re
from pydantic import ValidationError
from schemas import TailoredResume
from llm import call_llm
from skills import normalize
from matcher import _in_text

SYSTEM = """You tailor a candidate's resume to a target job.

Rules:
- The candidate profile is the ONLY source of facts. Never add skills, tools, technologies,
  projects, employers, certifications, achievements, numbers or metrics that are not in it.
- Do NOT mention a job requirement the candidate lacks, even if the job asks for it.
- skills: copy items EXACTLY from the profile's technical_skills / soft_skills. Put the ones
  most relevant to the job first. Never add new ones.
- projects / experience: keep names, companies, roles and durations EXACTLY as in the profile.
  Rewrite bullets using only the profile's description/highlights: strong action verbs, clear
  wording, emphasis on what is relevant to the job. Do not exaggerate (do not turn "helped" into "led").
- certifications / achievements: copy items EXACTLY from the profile, most relevant first.
- summary: 2 sentences maximum, built only from facts in the profile and aimed at the job.
- Respond with a single JSON object matching the schema. No explanation, no markdown."""


def _job_skills(job):
    s = list(job.required_skills) + list(job.preferred_skills)
    for g in job.skill_alternatives:
        s += g
    return s


def _tailored_text(t):
    parts = [t.summary]
    for p in t.projects:
        parts += p.bullets
    for e in t.experience:
        parts += e.bullets
    return " ".join(parts)


def check_faithfulness(t, profile, job):
    """Plain-code check: anything not traceable to the profile is flagged."""
    issues = []
    raw = profile.model_dump_json()
    corpus = normalize(raw)

    allowed = {normalize(x) for x in profile.technical_skills + profile.soft_skills}
    for s in t.skills:
        if normalize(s) not in allowed:
            issues.append(f"Skill not in your profile: {s}")

    names = {normalize(p.name) for p in profile.projects}
    for p in t.projects:
        if normalize(p.name) not in names:
            issues.append(f"Project not in your profile: {p.name}")

    companies = {normalize(e.company) for e in profile.experience}
    for e in t.experience:
        if normalize(e.company) not in companies:
            issues.append(f"Employer not in your profile: {e.company}")

    for field in ("certifications", "achievements"):
        allowed_items = {normalize(x) for x in getattr(profile, field)}
        for x in getattr(t, field):
            if normalize(x) not in allowed_items:
                issues.append(f"{field[:-1].capitalize()} not in your profile: {x}")

    text = _tailored_text(t)
    text_norm = normalize(text)
    for s in dict.fromkeys(_job_skills(job)):
        n = normalize(s)
        if n and not _in_text(n, corpus) and _in_text(n, text_norm):
            issues.append(f"Mentions '{s}' (from the job) but it is not in your profile")

    for num in set(re.findall(r"\d[\d,.]*%?", text)):
        num = num.rstrip(".,")
        if num and num not in raw:
            issues.append(f"Number not in your profile: {num}")

    return issues


def build_resume(profile, job, retries: int = 1):
    base = (f"CANDIDATE PROFILE (the only allowed source of facts):\n{profile.model_dump_json(indent=2)}"
            f"\n\nTARGET JOB:\n{job.model_dump_json(indent=2)}"
            f"\n\nJSON schema:\n{json.dumps(TailoredResume.model_json_schema())}")
    prompt, tailored, issues = base, None, []
    for _ in range(retries + 1):
        raw = call_llm(SYSTEM, prompt)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        try:
            tailored = TailoredResume.model_validate_json(raw)
        except ValidationError as e:
            prompt = base + f"\n\nYour previous output was invalid: {e}. Return corrected JSON only."
            continue
        issues = check_faithfulness(tailored, profile, job)
        if not issues:
            break
        prompt = (base + "\n\nYour previous draft broke these rules:\n- " + "\n- ".join(issues)
                  + "\nFix them and return corrected JSON only.")
    if tailored is None:
        raise ValueError("Could not generate a valid resume. Try again.")
    return tailored, issues


def render_markdown(t, profile) -> str:
    """Contact details, education and languages are copied from the profile, not written by the LLM."""
    contact = " | ".join(x for x in [profile.email, profile.phone, profile.linkedin, profile.github] if x)
    out = [f"# {profile.name}", contact, ""]
    if t.summary:
        out += ["## Summary", t.summary, ""]
    if t.skills:
        out += ["## Skills", ", ".join(t.skills), ""]
    if t.experience:
        out.append("## Experience")
        for e in t.experience:
            out.append(f"**{e.role}**, {e.company} ({e.duration})")
            out += [f"- {b}" for b in e.bullets]
            out.append("")
    if t.projects:
        out.append("## Projects")
        for p in t.projects:
            out.append(f"**{p.name}**")
            out += [f"- {b}" for b in p.bullets]
            out.append("")
    if profile.education:
        out.append("## Education")
        out += [f"- {e.degree}, {e.institution} ({e.year})" for e in profile.education]
        out.append("")
    if t.certifications:
        out += ["## Certifications"] + [f"- {c}" for c in t.certifications] + [""]
    if t.achievements:
        out += ["## Achievements"] + [f"- {a}" for a in t.achievements] + [""]
    if profile.languages:
        out += ["## Languages", ", ".join(profile.languages)]
    return "\n".join(out)
import json, re
from pydantic import ValidationError
from schemas import JobRequirements
from llm import call_llm
from skills import normalize, ALIASES

SYSTEM = """You extract structured requirements from job descriptions.
Rules:
- Use ONLY information present in the job description. Never invent anything.
- Skills must be short names (e.g. "Python", "SQL", "Docker"), not sentences.
- required_skills = must-have; preferred_skills = nice-to-have / bonus.
- If something is not mentioned, leave it empty.
- Respond with a single JSON object matching the schema. No explanation, no markdown.
- required_skills and preferred_skills = technologies, tools, libraries, techniques AND general
  technology categories named in the job (e.g. Python, Docker, RAG, prompt engineering,
  databases, vector databases, cloud). Do NOT put years of experience, degrees, soft traits,
  or vague items like "computer science fundamentals" or "best coding practices" there.
- Include every skill named in the Requirements section, even when several appear in one sentence
  (e.g. "databases, vector DBs, and containerization" is three skills).
  - If skills are given as examples or alternatives ("e.g.", "such as", "like", "or"), do NOT put
  them in required_skills. Put them as ONE group in skill_alternatives,
  e.g. [["Python", "JavaScript"]], meaning any one of them satisfies the requirement.
- experience_level must be exactly one of: "entry" (intern, fresher, 0-2 years), "mid" (2-5 years),
  "senior" (5+ years), or "" if the job does not say.
- soft_skills = communication, ownership, problem-solving and similar non-technical requirements.
- preferred_skills = ONLY concrete technologies or tools named as "plus", "preferred" or
  "nice to have". Never put business activities (business analysis, process modelling),
  broad words (AI), or soft skills there.
- Skills introduced by "e.g.", "such as" or "like" are examples. Put them in
  skill_alternatives as ONE group, never in required_skills."""


NON_TECH = {"business", "process", "stakeholder", "customer", "communication",
            "ownership", "problem", "collaboration", "leadership"}
GENERIC = {"ai", "programming", "coding", "software", "technology", "technical skills",
           "programming languages", "tools", "data"}


def _in_jd(term: str, jd_lower: str) -> bool:
    """Whole-word match of the skill (or a known alias) in the job text."""
    n = normalize(term)
    variants = {term.lower().strip(), n} | {k for k, v in ALIASES.items() if v == n}
    for v in variants:
        if v and re.search(r"(?<![a-z0-9+#])" + re.escape(v) + r"(?![a-z0-9+#])", jd_lower):
            return True
    return False


def _soft_in_jd(term: str, jd_lower: str) -> bool:
    """Loose match: the first 6 letters of any word in the term appear at a word start in the JD."""
    for w in re.findall(r"[a-z]+", term.lower()):
        stem = w[:6]
        if len(stem) >= 4 and re.search(r"\b" + re.escape(stem), jd_lower):
            return True
    return False

def clean_job(job, jd_text: str):
    """Code-level cleanup: drop vague, non-technical, duplicate or ungrounded skills."""
    jd_lower = jd_text.lower()
    in_groups = {s.lower().strip() for g in job.skill_alternatives for s in g}

    def keep(s):
        t = s.lower().strip()
        if t in in_groups or t in GENERIC:
            return False
        if set(t.replace("-", " ").split()) & NON_TECH:
            return False
        return _in_jd(t, jd_lower)

    job.required_skills = [s for s in job.required_skills if keep(s)]
    job.preferred_skills = [s for s in job.preferred_skills if keep(s)]
    job.soft_skills = [s for s in job.soft_skills if _soft_in_jd(s, jd_lower)]    
    return job



def extract_job(job_text: str, retries: int = 1) -> JobRequirements:
    schema = json.dumps(JobRequirements.model_json_schema())
    prompt = f"JSON schema:\n{schema}\n\nJob description:\n{job_text}"
    last_error = None
    for _ in range(retries + 1):
        raw = call_llm(SYSTEM, prompt)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        try:
            return clean_job(JobRequirements.model_validate_json(raw), job_text)
        except ValidationError as e:
            last_error = e
            prompt += f"\n\nYour previous output was invalid: {e}. Return corrected JSON only."
    raise last_error
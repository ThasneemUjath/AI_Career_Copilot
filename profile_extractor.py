import json, re
from pydantic import ValidationError
from schemas import CandidateProfile
from llm import call_llm
from skills import normalize, ALIASES

SYSTEM = """You extract structured data from resumes.

Rules:
- Use ONLY information present in the resume. Never invent or assume anything.
- Respond with a single JSON object matching the schema. No explanation, no markdown.
- Use the "Hyperlinks found in the PDF" section to fill linkedin, github and other URLs.
- In the resume text, every line starting with "- " is ONE complete item (already merged if it
  wrapped across lines). Never split one "- " line into two items and never join two "- " lines.
- Leave missing_info as an empty list.

Section mapping:
- technical_skills = ONLY items from the Skills section (languages, libraries, tools).
  Never take items from Internships, Certifications, Projects or Education.
  One skill per item. If the Skills section has category labels such as
  "Programming: Python, SQL", output "Python" and "SQL" as separate items and never
  include the label.
- experience = ANY work done at a company or organization: internships, training,
  apprenticeships, freelance, part-time jobs. Everything under an Internships/Training heading
  goes here. An entry like "Data Analytics (May 2025 - June 2025)" followed by
  "TriRope Technologies, Chennai" means role="Data Analytics Intern",
  company="TriRope Technologies, Chennai", duration="May 2025 - June 2025".
- education = ONLY degrees, colleges, schools and their years.
- projects = things the candidate built. projects.technologies = ONLY technologies explicitly
  written for that project; if none are named, return an empty list.
- achievements = awards, rankings, competition results.
- certifications = completed courses and issued certificates.
- languages = spoken languages only (English, Tamil...), not programming languages."""


# ---------- one skill per item ----------
def split_skills(items):
    """'ML & Data: Pandas, NumPy' -> ['Pandas', 'NumPy']. Drops the category label."""
    out = []
    for item in items:
        text = item.split(":", 1)[1] if ":" in item else item
        for part in re.split(r"[,;|\u2022]", text):
            part = part.strip(" .-")
            if part:
                out.append(part)
    return list(dict.fromkeys(out))


# ---------- grounding check ----------
def _variants(term: str) -> set:
    n = normalize(term)
    v = {term.lower().strip(), n}
    v |= {k for k, val in ALIASES.items() if val == n}
    return {x for x in v if x}


def _in_text(term: str, text_lower: str) -> bool:
    """Whole-word match of the term (or a known alias of it) in the resume text."""
    for v in _variants(term):
        pattern = r"(?<![a-z0-9+#])" + re.escape(v) + r"(?![a-z0-9+#])"
        if re.search(pattern, text_lower):
            return True
    return False


def verify_profile(profile: CandidateProfile, resume_text: str):
    """Drop any skill or technology that does not appear in the resume text."""
    text_lower = resume_text.lower()
    removed = []

    for proj in profile.projects:
        kept = []
        for tech in proj.technologies:
            if _in_text(tech, text_lower):
                kept.append(tech)
            else:
                removed.append(f"{tech} (project: {proj.name})")
        proj.technologies = kept

    for field in ("technical_skills", "soft_skills"):
        kept = []
        for s in getattr(profile, field):
            if _in_text(s, text_lower):
                kept.append(s)
            else:
                removed.append(f"{s} ({field})")
        setattr(profile, field, kept)

    return profile, removed


# ---------- missing_info computed in code ----------
SECTIONS = [
    ("technical_skills", "Technical skills", {"skills", "technical skills"}),
    ("projects", "Projects", {"projects", "project"}),
    ("experience", "Experience", {"experience", "internships", "internship",
                                  "work experience", "training"}),
    ("education", "Education", {"education"}),
    ("certifications", "Certifications", {"certifications", "certification"}),
    ("achievements", "Achievements", {"achievements", "awards"}),
]
CONTACT = [("email", "Email"), ("phone", "Phone"), ("linkedin", "LinkedIn"),
           ("github", "GitHub"), ("objective", "Objective")]


def compute_missing_info(profile: CandidateProfile, resume_text: str) -> list:
    headings = {re.sub(r"[^a-z ]", "", l.lower()).strip() for l in resume_text.splitlines()}
    missing = []
    for field, label, keys in SECTIONS:
        if not getattr(profile, field):
            if headings & keys:
                missing.append(f"{label}: heading found in resume but nothing extracted (check manually)")
            else:
                missing.append(f"{label}: not found in resume")
    for field, label in CONTACT:
        if not getattr(profile, field):
            missing.append(f"{label}: not found")
    return missing


def extract_profile(resume_text: str, retries: int = 1):
    schema = json.dumps(CandidateProfile.model_json_schema())
    prompt = f"JSON schema:\n{schema}\n\nResume:\n{resume_text}"
    last_error = None
    for _ in range(retries + 1):
        raw = call_llm(SYSTEM, prompt)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        try:
            profile = CandidateProfile.model_validate_json(raw)
            profile.technical_skills = split_skills(profile.technical_skills)
            profile, removed = verify_profile(profile, resume_text)
            profile.missing_info = compute_missing_info(profile, resume_text)
            return profile, removed
        except ValidationError as e:
            last_error = e
            prompt += f"\n\nYour previous output was invalid: {e}. Return corrected JSON only."
    raise last_error
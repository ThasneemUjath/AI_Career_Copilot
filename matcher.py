import re
from skills import normalize, ALIASES, CONCEPTS, RELATED

W_REQUIRED, W_PREFERRED, W_PROJECTS, W_LEVEL = 45, 15, 25, 15
LEVELS = {"entry": 0, "mid": 1, "senior": 2}


def _flat(s: str) -> str:
    """Hyphen-insensitive form, so 'machine-learning' and 'machine learning' are the same."""
    return re.sub(r"\s+", " ", s.replace("-", " ")).strip()


def _in_text(skill_norm: str, text_norm: str) -> bool:
    """Whole-word match, so 'r' does not match inside 'research'. Ignores hyphen vs space."""
    if not skill_norm:
        return False
    pattern = r"(?<![a-z0-9+#])" + re.escape(_flat(skill_norm)) + r"(?![a-z0-9+#])"
    return re.search(pattern, _flat(text_norm)) is not None


def _variants(skill_norm: str) -> set:
    """The skill plus its known abbreviations (ml -> machine learning)."""
    return {skill_norm} | {k for k, v in ALIASES.items() if v == skill_norm}


def match(profile, job, candidate_level: str = "entry") -> dict:
    listed = {normalize(s) for s in profile.technical_skills}
    project_skills = {normalize(t) for p in profile.projects for t in p.technologies}
    candidate = listed | project_skills

    extra_text = " ".join(
        [profile.objective]
        + profile.certifications
        + [e.role + " " + e.company + " " + " ".join(e.highlights) for e in profile.experience]
        + [p.name + " " + p.description for p in profile.projects]
    )
    extra_norm = normalize(extra_text)
    project_text = normalize(" ".join(p.name + " " + p.description for p in profile.projects))

    def _has(skill: str) -> bool:
        n = normalize(skill)
        options = CONCEPTS.get(n, {n})
        return any(v in candidate or _in_text(v, extra_norm)
                   for o in options for v in _variants(o))

    def _in_proj(skill: str) -> bool:
        n = normalize(skill)
        return n in project_skills or any(_in_text(v, project_text) for v in _variants(n))

    def _related(skill: str) -> list:
        terms = RELATED.get(normalize(skill), set())
        return sorted(t for t in terms if t in candidate or _in_text(t, extra_norm))

    required = list(dict.fromkeys(job.required_skills))
    preferred = list(dict.fromkeys(job.preferred_skills))
    groups = [g for g in job.skill_alternatives if g]

    req_matched = [s for s in required if _has(s)]
    req_missing = [s for s in required if not _has(s)]
    in_projects = [s for s in required if _in_proj(s)]

    # an "any one of these" group counts as a single requirement
    for g in groups:
        label = " or ".join(g)
        (req_matched if any(_has(s) for s in g) else req_missing).append(label)
        if any(_in_proj(s) for s in g):
            in_projects.append(label)

    total_required = len(required) + len(groups)
    pref_matched = [s for s in preferred if _has(s)]
    pref_missing = [s for s in preferred if not _has(s)]

    # shown next to missing skills, never counted in the score
    related_evidence = {s: found for s in req_missing if (found := _related(s))}

    # only score components that actually apply to this job
    components = {}
    if total_required:
        components["required_skills"] = (W_REQUIRED, len(req_matched) / total_required)
        components["project_evidence"] = (W_PROJECTS, len(in_projects) / total_required)
    if preferred:
        components["preferred_skills"] = (W_PREFERRED, len(pref_matched) / len(preferred))

    job_level = (job.experience_level or "").strip().lower()
    if job_level in LEVELS and candidate_level in LEVELS:
        gap = abs(LEVELS[job_level] - LEVELS[candidate_level])
        components["level_fit"] = (W_LEVEL, max(0.0, 1 - 0.5 * gap))

    total_weight = sum(w for w, _ in components.values())
    breakdown = {k: round(100 * w * r / total_weight, 1) for k, (w, r) in components.items()} if total_weight else {}
    score = round(sum(breakdown.values()))

    n_requirements = total_required
    raw_score = score
    low_confidence = n_requirements <= 2
    if low_confidence:
        score = min(score, 60)   # heuristic cap: too little evidence to rate higher

    if score >= 75:
        recommendation = "HIGH_PRIORITY"
    elif score >= 50:
        recommendation = "MEDIUM_PRIORITY"
    else:
        recommendation = "LOW_PRIORITY"

    return {
        "match_score": score,
        "breakdown": breakdown,
        "matched_required": req_matched,
        "missing_required": req_missing,
        "matched_preferred": pref_matched,
        "missing_preferred": pref_missing,
        "skills_proven_in_projects": in_projects,
        "related_evidence": related_evidence,
        "recommendation": recommendation,
        "raw_score": raw_score,
        "n_requirements": n_requirements,
        "low_confidence": low_confidence,
    }
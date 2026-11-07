import json, re
from pydantic import ValidationError
from schemas import InterviewQuestions, AnswerEvaluation
from llm import call_llm
from skills import normalize

# ---------- question generation ----------
LEVEL_GUIDE = {
    "entry": "Fresher (0-1 yrs). Core concepts and basic practical use. "
             "One sentence, max 25 words. No system design.",
    "mid": "Junior (1-3 yrs). Practical trade-offs and debugging scenarios. "
           "Max 2 short sentences, 40 words.",
    "senior": "Experienced (3+ yrs). Design decisions, scaling, failure handling, trade-offs. "
              "Max 2 short sentences, 45 words.",
}

SYSTEM = """You are a technical interviewer.
Rules:
- Ask only about topics in the ALLOWED TOPICS list. Copy the topic exactly from that list.
- Match the difficulty and length limit given in LEVEL GUIDE.
- Each question asks ONE thing. No multi-part questions. Never use "also", "additionally" or "include".
- If PRIORITY TOPICS are given, ask about them first.
- Respond with a single JSON object matching the schema. No explanation, no markdown.
- When a question mentions a candidate project, mention only technologies listed for that project.
- The question must be about the named topic itself. If it needs a library
  (pandas, NumPy), the topic must be that library, not "Python"."""


def allowed_topics(profile, job):
    topics = list(job.required_skills) + list(job.preferred_skills)
    for g in job.skill_alternatives:
        topics += g
    topics += profile.technical_skills
    return list(dict.fromkeys(topics))


def generate_questions(profile, job, n: int = 5, priority_topics=None,
                       level: str = "entry", retries: int = 1):
    topics = allowed_topics(profile, job)
    ok = {normalize(t) for t in topics}
    priority_topics = ([t for t in (priority_topics or []) if normalize(t) in ok]
                       or list(job.required_skills))
    prompt = (f"ALLOWED TOPICS: {json.dumps(topics)}\n"
              f"PRIORITY TOPICS: {json.dumps(priority_topics)}\n"
              f"Candidate projects: {json.dumps([{'name': p.name, 'technologies': p.technologies} for p in profile.projects])}\n"
              f"LEVEL GUIDE: {LEVEL_GUIDE.get(level, LEVEL_GUIDE['entry'])}\n"
              f"Number of questions: {n}\n\n"
              f"JSON schema:\n{json.dumps(InterviewQuestions.model_json_schema())}")
    last_error = None
    for _ in range(retries + 1):
        raw = call_llm(SYSTEM, prompt, temperature=0.3)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        try:
            qs = InterviewQuestions.model_validate_json(raw).questions
            return [q for q in qs if normalize(q.topic) in ok and q.question.strip()
                    and len(q.question.split()) <= 50][:n]
        except ValidationError as e:
            last_error = e
            prompt += f"\n\nYour previous output was invalid: {e}. Return corrected JSON only."
    raise last_error


# ---------- answer evaluation ----------
EVAL_SYSTEM = """You grade a candidate's answer to an interview question.
Rules:
- Score concept, accuracy and clarity from 1 to 5
  (1 = wrong or empty, 3 = partly correct, 5 = correct and clear).
- Judge against the expected depth for CANDIDATE LEVEL: entry needs correct basics,
  mid needs practical reasoning, senior needs trade-offs and edge cases.
- Judge ONLY what the answer actually says. Give no credit for things the candidate did not write.
- feedback: maximum 2 short sentences. If something is wrong, say what is wrong and give a one-sentence hint.
- follow_up: ONE short question about the weakest part of the answer.
- Respond with a single JSON object matching the schema. No explanation, no markdown."""


def evaluate_answer(topic: str, question: str, answer: str,
                    level: str = "entry", retries: int = 1) -> AnswerEvaluation:
    if not answer.strip():
        return AnswerEvaluation(concept=1, accuracy=1, clarity=1,
                                feedback="No answer given.", follow_up=question)
    prompt = (f"CANDIDATE LEVEL: {level}\nTopic: {topic}\nQuestion: {question}\n"
              f"Candidate answer: {answer}\n\n"
              f"JSON schema:\n{json.dumps(AnswerEvaluation.model_json_schema())}")
    last_error = None
    for _ in range(retries + 1):
        raw = call_llm(EVAL_SYSTEM, prompt, temperature=0)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        try:
            ev = AnswerEvaluation.model_validate_json(raw)
            for f in ("concept", "accuracy", "clarity"):
                setattr(ev, f, max(1, min(5, getattr(ev, f))))
            return ev
        except ValidationError as e:
            last_error = e
            prompt += f"\n\nYour previous output was invalid: {e}. Return corrected JSON only."
    raise last_error
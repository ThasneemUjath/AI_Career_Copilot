from mcp_client import call_tool
from schemas import CandidateProfile, JobRequirements
from interview_coach import generate_questions

profile = CandidateProfile.model_validate_json(call_tool("db", "get_candidate_profile"))
job = JobRequirements(required_skills=["Python", "SQL"], preferred_skills=["Docker"])

for q in generate_questions(profile, job, n=4):
    print(q.topic, "|", q.question)
for lvl in ("entry", "mid", "senior"):
    print("---", lvl)
    for q in generate_questions(profile, job, n=3, level=lvl):
        print(q.topic, "|", q.question)
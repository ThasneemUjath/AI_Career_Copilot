from schemas import CandidateProfile, Project, JobRequirements, TailoredResume, TailoredProject
from resume_builder import check_faithfulness

profile = CandidateProfile(
    name="Test",
    technical_skills=["Python", "Pandas"],
    projects=[Project(name="Churn Model", description="Built a model using Python", technologies=["Python"])],
)
job = JobRequirements(required_skills=["Python", "Docker"])

bad = TailoredResume(
    skills=["Python", "Docker"],
    projects=[
        TailoredProject(name="Churn Model", bullets=["Deployed with Docker, improving accuracy by 25%"]),
        TailoredProject(name="Fake Project", bullets=["Did something"]),
    ],
)

for issue in check_faithfulness(bad, profile, job):
    print(issue)
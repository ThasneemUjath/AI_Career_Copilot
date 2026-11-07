from pydantic import BaseModel, Field
from typing import List


class Education(BaseModel):
    degree: str = Field("", description="Degree or course of study only, never internships or jobs")
    institution: str = ""
    year: str = ""


class Project(BaseModel):
    name: str = ""
    description: str = ""
    technologies: List[str] = Field([], description="Only technologies explicitly written for this project")


class Experience(BaseModel):
    role: str = Field("", description="Job title or topic, e.g. 'Data Analytics Intern'")
    company: str = ""
    duration: str = ""
    highlights: List[str] = Field([], description="Work done, including internships and training")


class CandidateProfile(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    objective: str = ""
    technical_skills: List[str] = []
    soft_skills: List[str] = []
    education: List[Education] = []
    projects: List[Project] = []
    experience: List[Experience] = []
    certifications: List[str] = []
    achievements: List[str] = []
    languages: List[str] = []
    missing_info: List[str] = []
    other_sections: dict[str, List[str]] = Field(
          {}, description="Any resume section that does not fit the fields above. Key = the section heading, value = its entries")

class JobRequirements(BaseModel):
    title: str = ""
    company: str = ""
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    experience_level: str = ""
    responsibilities: List[str] = []
    location: str = ""
    work_mode: str = ""  
    experience_requirements: List[str] = []   # e.g. "2+ years in AI engineering", "mentoring" 
    skill_alternatives: List[List[str]] = []   # e.g. [["Python", "JavaScript"]] = any one of these
    soft_skills: List[str] = []                # communication, ownership, problem-solving...

class TailoredProject(BaseModel):
    name: str = ""
    bullets: List[str] = []


class TailoredExperience(BaseModel):
    role: str = ""
    company: str = ""
    duration: str = ""
    bullets: List[str] = []


class TailoredResume(BaseModel):
    summary: str = ""
    skills: List[str] = []
    projects: List[TailoredProject] = []
    experience: List[TailoredExperience] = []
    certifications: List[str] = []
    achievements: List[str] = []

class InterviewQuestion(BaseModel):
    topic: str = Field("", description="Short skill/topic name, e.g. 'Python', 'SQL'")
    question: str = ""


class InterviewQuestions(BaseModel):
    questions: List[InterviewQuestion] = []


class AnswerEvaluation(BaseModel):
    concept: int = Field(0, description="Concept understanding, 1-5")
    accuracy: int = Field(0, description="Technical accuracy, 1-5")
    clarity: int = Field(0, description="Explanation clarity, 1-5")
    feedback: str = ""
    follow_up: str = ""
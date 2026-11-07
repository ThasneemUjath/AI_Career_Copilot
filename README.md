---
title: AI Career Copilot
emoji: 🧭
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# AI Career Copilot

A career assistant that reads your resume, matches it to a job description with an **explainable score**, writes a **tailored resume that is checked for invented facts**, and lets you **practise the interview**. Tools are exposed to an LLM agent through the **Model Context Protocol (MCP)**.

**Live demo:** _add your Hugging Face Space link_  
**Demo video:** _add your video link_

## What it does

- **Profile extraction:** PDF resume to a structured, validated profile. Every extracted skill must appear in the resume text (grounding check).
- **Job match:** pasted job description to required and preferred skills, then a deterministic score (no LLM) with matched and missing skills. Related terms in the resume are shown next to missing skills but never scored.
- **Tailored resume:** rewrites bullets using only facts from the profile, then a code-based faithfulness check flags new skills, projects, employers and numbers. You approve it before download as Word, PDF or Markdown.
- **Mock interview:** level-aware questions (fresher, junior, experienced), scored answers (concept, accuracy, clarity), and revisits your weak topics.
- **Copilot chat:** an orchestrator agent that decides which tools to call and answers only from tool results.

The app never submits applications. A human reviews everything before it is used.

## Design decisions

- The LLM does only fuzzy work (reading text, extracting fields, writing, grading). Parsing, scoring, grounding checks and faithfulness checks are plain code.
- Reliability comes from prompt rules **plus** code checks around the model. Nothing is fine-tuned.
- Each visitor's data is stored under a private session id, so visitors never see each other's data. Uploaded PDFs are deleted right after reading.

## Architecture

```
Streamlit UI  ->  Orchestrator (tool-calling agent)
                        |
        profile extractor / job extractor / matcher / resume builder / interview coach
                        |
                  MCP client  ->  files server (read resume, save document)
                              ->  db server (SQLite: profiles, jobs, interview results)
```

## Tech stack

Python, Streamlit, Groq (`openai/gpt-oss-120b`), Pydantic, PyMuPDF, SQLite, MCP (`mcp<2`), python-docx, ReportLab, Docker.

## Run locally

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file with `GROQ_API_KEY=your_key`, then:

```
streamlit run app.py
```

Or with Docker:

```
docker build -t career-copilot .
docker run -p 7860:7860 -e GROQ_API_KEY=your_key career-copilot
```

## Known limitations

- Matching is keyword-based, so "cloud platforms" does not match "Oracle Cloud". Embeddings would be the upgrade.
- Two-column resumes: layout detection uses text positions. A wrapped line in a two-column layout can occasionally be read as two items, and tables, text boxes or three columns can break it.
- The score cap for jobs with two or fewer technical requirements (60), the soft-skill grounding check and the related-terms table are heuristics.
- LLM extraction can vary between runs. Temperature 0, caching and code cleanup reduce this but do not remove it.
- Interview grading is an LLM judgement. It is a practice signal, not an exam grade. The follow-up question is shown but not scored.
- Interview history lasts for the browser session only.
- PDF export supports Latin, Greek and Cyrillic text and common symbols. Indic scripts are not supported in the PDF (the Word export has no such limit).
- Each MCP call starts the server fresh, which adds about a second.
- The free model tier has rate limits, so heavy use can return an error.

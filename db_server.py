import json, sqlite3
from datetime import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("career-db")
DB = Path(__file__).parent / "career.db"


def _conn():
    c = sqlite3.connect(DB)
    # every row belongs to a visitor's private session id (sid), so visitors never see each other's data
    c.execute("CREATE TABLE IF NOT EXISTS profiles "
              "(sid TEXT PRIMARY KEY, data TEXT, updated TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS saved_jobs "
              "(id INTEGER PRIMARY KEY AUTOINCREMENT, sid TEXT, title TEXT, company TEXT, "
              "data TEXT, created TEXT)")
    # in interview_results the 'candidate' column holds the same session id
    c.execute("CREATE TABLE IF NOT EXISTS interview_results "
              "(id INTEGER PRIMARY KEY AUTOINCREMENT, candidate TEXT, topic TEXT, question TEXT, "
              "answer TEXT, concept INTEGER, accuracy INTEGER, clarity INTEGER, feedback TEXT, created TEXT)")
    return c


@mcp.tool()
def save_candidate_profile(sid: str, profile_json: str) -> str:
    """Save (or overwrite) this session's candidate profile. Input is the profile as a JSON string."""
    json.loads(profile_json)  # reject invalid JSON
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO profiles (sid, data, updated) VALUES (?, ?, ?)",
                  (sid, profile_json, datetime.now().isoformat()))
    return "saved"


@mcp.tool()
def get_candidate_profile(sid: str) -> str:
    """Return this session's saved candidate profile as a JSON string, or an empty string if none."""
    with _conn() as c:
        row = c.execute("SELECT data FROM profiles WHERE sid = ?", (sid,)).fetchone()
    return row[0] if row else ""


@mcp.tool()
def save_job(sid: str, job_json: str) -> str:
    """Save a job's extracted requirements (JSON string) for this session. Returns the new job id."""
    j = json.loads(job_json)
    with _conn() as c:
        cur = c.execute("INSERT INTO saved_jobs (sid, title, company, data, created) VALUES (?, ?, ?, ?, ?)",
                        (sid, j.get("title", ""), j.get("company", ""), job_json,
                         datetime.now().isoformat()))
    return str(cur.lastrowid)


@mcp.tool()
def list_jobs(sid: str) -> str:
    """List this session's saved jobs as a JSON array of {id, title, company}."""
    with _conn() as c:
        rows = c.execute("SELECT id, title, company FROM saved_jobs WHERE sid = ? ORDER BY id DESC",
                         (sid,)).fetchall()
    return json.dumps([{"id": r[0], "title": r[1], "company": r[2]} for r in rows])


@mcp.tool()
def save_interview_result(candidate: str, topic: str, question: str, answer: str,
                          concept: int, accuracy: int, clarity: int, feedback: str) -> str:
    """Save one evaluated interview answer for a session id. Scores are 1-5. Returns the new row id."""
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO interview_results "
            "(candidate, topic, question, answer, concept, accuracy, clarity, feedback, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (candidate, topic, question, answer, concept, accuracy, clarity, feedback,
             datetime.now().isoformat()))
    return str(cur.lastrowid)


@mcp.tool()
def get_weak_topics(candidate: str, threshold: float = 3.5) -> str:
    """Topics where this session's average score is below the threshold, weakest first.
    Returns a JSON array of {topic, avg_score, attempts}."""
    with _conn() as c:
        rows = c.execute(
            "SELECT topic, AVG((concept + accuracy + clarity) / 3.0) AS avg, COUNT(*) "
            "FROM interview_results WHERE candidate = ? "
            "GROUP BY topic HAVING avg < ? ORDER BY avg ASC",
            (candidate, threshold)).fetchall()
    return json.dumps([{"topic": r[0], "avg_score": round(r[1], 2), "attempts": r[2]}
                       for r in rows])


if __name__ == "__main__":
    mcp.run()
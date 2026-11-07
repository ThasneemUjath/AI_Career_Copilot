from pathlib import Path
from mcp.server.fastmcp import FastMCP
from resume_parser import extract_text

mcp = FastMCP("career-files")
BASE = Path(__file__).parent
UPLOADS = BASE / "uploads"
OUTPUTS = BASE / "outputs"


@mcp.tool()
def read_resume(path: str) -> str:
    """Read a PDF resume from the uploads folder and return its text."""
    p = UPLOADS / Path(path).name          # .name blocks paths like ../../secret
    if not p.exists():
        raise FileNotFoundError(f"No such resume: {p.name}")
    return extract_text(p.read_bytes())


@mcp.tool()
def save_document(filename: str, content: str) -> str:
    """Save text content to the outputs folder and return the saved path."""
    OUTPUTS.mkdir(exist_ok=True)
    p = OUTPUTS / Path(filename).name
    p.write_text(content, encoding="utf-8")
    return str(p)


if __name__ == "__main__":
    mcp.run()
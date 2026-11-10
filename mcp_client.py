import asyncio, sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE = Path(__file__).parent
SERVERS = {"files": BASE / "files_server.py", "db": BASE / "db_server.py"}


async def _call(server: str, tool: str, args: dict) -> str:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVERS[server])])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
            if result.isError:
                raise RuntimeError(f"MCP tool '{tool}' failed: {text}")
            return text


def _root_cause(e: BaseException) -> BaseException:
    """anyio wraps errors in an ExceptionGroup ('unhandled errors in a TaskGroup').
    Dig out the real one so the message says what actually went wrong."""
    while getattr(e, "exceptions", None):
        e = e.exceptions[0]
    return e


def call_tool(server: str, tool: str, args: dict | None = None) -> str:
    try:
        return asyncio.run(_call(server, tool, args or {}))
    except Exception as e:
        root = _root_cause(e)
        raise RuntimeError(f"MCP {server}.{tool} failed: {type(root).__name__}: {root}") from None
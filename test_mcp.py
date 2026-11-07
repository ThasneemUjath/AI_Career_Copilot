from mcp_client import call_tool

print(call_tool("db", "save_job", {"sid": "test", "job_json": '{"title": "t", "company": "c"}'}))
print(call_tool("db", "list_jobs", {"sid": "test"}))
print(call_tool("db", "get_candidate_profile", {"sid": "nobody"}) or "(no profile for this session)")
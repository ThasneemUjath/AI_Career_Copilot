import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def call_llm(system: str, user: str, temperature: float = 0) -> str:
    resp = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
        max_completion_tokens=4000,
        temperature=temperature,
        seed=42,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content
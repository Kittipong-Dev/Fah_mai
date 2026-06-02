# -*- coding: utf-8 -*-
"""Diagnose LangSmith tracing: load .env, make one traced LLM call, then check the project for runs."""
import os
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Newer langsmith uses LANGSMITH_*; langchain-core historically reads LANGCHAIN_TRACING_V2. Set both.
if os.getenv("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGCHAIN_API_KEY", os.environ["LANGSMITH_API_KEY"])
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGSMITH_TRACING"] = "true"
PROJECT = (os.getenv("LANGSMITH_PROJECT") or "fahmai").strip().strip('"')
os.environ["LANGCHAIN_PROJECT"] = PROJECT
os.environ["LANGSMITH_PROJECT"] = PROJECT

print("LANGSMITH_TRACING:", os.getenv("LANGSMITH_TRACING"))
print("API key present  :", bool(os.getenv("LANGSMITH_API_KEY")))
print("endpoint         :", os.getenv("LANGSMITH_ENDPOINT"))
print("project          :", PROJECT)

from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="google/gemma-4-31b-it", base_url="https://openrouter.ai/api/v1",
                 api_key=os.environ["OPEN_ROUTER"], temperature=0)
out = llm.invoke("reply with one word: traced")
print("\nLLM said:", out.content[:40])

# verify a run landed in the project
from langsmith import Client
c = Client()
print("\nLangSmith client URL:", c.api_url)
time.sleep(4)  # allow background flush
try:
    runs = list(c.list_runs(project_name=PROJECT, limit=5))
    print(f"runs in project '{PROJECT}':", len(runs))
    for r in runs[:3]:
        print("  -", r.name, r.start_time)
except Exception as e:
    print("list_runs error:", e)

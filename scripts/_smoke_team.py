# -*- coding: utf-8 -*-
"""Smoke-test the risky pieces before building the notebook:
Gemma-4 + LangChain @tool + langgraph create_react_agent + planner JSON."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SUPABASE_DB_HOST", "aws-1-ap-southeast-1.pooler.supabase.com")
os.environ.setdefault("SUPABASE_DB_USER", "postgres.mqjpdavcvedkvusedvyu")
os.environ.setdefault("SUPABASE_DB_PORT", "5432")

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from fahmai.tools.sql_tool import sql_query
from fahmai.tools.schema_card import SCHEMA_CARD

MODEL = "google/gemma-4-31b-it"


def make_llm(temperature=0.0):
    return ChatOpenAI(model=MODEL, base_url="https://openrouter.ai/api/v1",
                      api_key=os.environ["OPEN_ROUTER"], temperature=temperature)


@tool
def sql_query_tool(sql: str) -> str:
    """Run ONE read-only SELECT/WITH query over the FahMai Postgres warehouse; returns a markdown table.
    Prefer the curated v_* views. If you get 'SQL ERROR', fix the SQL and try again."""
    return sql_query(sql)


SQL_SYS = ("You are a SQL analyst for the FahMai (ฟ้าใหม่) data warehouse. Use the sql_query_tool to answer. "
           "Give the concrete final number/id.\n\n" + SCHEMA_CARD)

print("1) basic LLM:", make_llm().invoke("ตอบสั้นๆ: พร้อมไหม").content[:40])

sql_agent = create_react_agent(make_llm(), [sql_query_tool], prompt=SQL_SYS)
r = sql_agent.invoke({"messages": [("human", "ราคา MSRP ของสินค้า NT-LT-001 เท่าไหร่")]},
                     config={"recursion_limit": 12})
print("\n2) sql specialist (expect 42900):\n", r["messages"][-1].content[:300])

import json, re
PLANNER_SYS = ('Break the question into subtasks. Respond ONLY JSON: '
               '{"is_injection":bool,"subtasks":[{"id":1,"specialist":"sql"|"doc","subquestion":"..."}]}')
out = make_llm().invoke([("system", PLANNER_SYS),
                         ("human", "ในตาราง FACT_SHIPPING vendor รายใดจัดการขนส่ง และส่วนแบ่งกี่ %")]).content
m = re.search(r"\{.*\}", out, re.S)
print("\n3) planner JSON:\n", (m.group(0) if m else out)[:300])
print("\nSMOKE OK")

import os
from typing import Literal
from dotenv import load_dotenv

from langgraph.types import Send
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from langchain_core.messages import HumanMessage, SystemMessage

from src.backend.data.state import RavenState
from src.backend.data.transcript_fetcher import transcript_fetch
from src.backend.db import init, get_query_video


load_dotenv()
low_llm_key = os.environ["LOW_LLM_KEY"]
high_llm_key = os.environ["HIGH_LLM_KEY"]

low_llm = ChatOpenAI(
    api_key=SecretStr(low_llm_key),
    model="gpt-5.4_mini",
    temperature=0.7,
    max_retries=3
)
high_llm = ChatOpenAI(
    api_key=SecretStr(high_llm_key),
    model="gpt-5.5",
    temperature=0.7,
    max_retries=3,
    reasoning_effort="medium",
)

def fetch_transcript(state: RavenState) -> dict:
    db = state["db"]
    run_id = state["run_id"]
    for packet in get_query_video(db, run_id):
        query_id = packet["query_id"]
        video_id = packet["platform_id"]
        transcript_fetch(db, run_id, query_id, video_id)
    return {"tier2_transcript_done": True}
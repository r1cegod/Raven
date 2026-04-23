import os
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, SecretStr

from src.backend.data.prompt.enricher import ENRICHER_PROMPT
from src.backend.data.search_base import search_youtube
from src.backend.db import init, create_run
from src.backend.data.state import RavenState

load_dotenv()
enricher_key = os.environ["ENRICHER_DEV_KEY"]


class EnricherOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    queries: list[str]


llm = ChatOpenAI(
    api_key=SecretStr(enricher_key),
    model="gpt-5.4-mini",
    max_retries=3,
)
enricher_llm = llm.with_structured_output(EnricherOutput)

def run_create(state: RavenState):
    query = state["query"]
    db = init()
    run_id = create_run(db, query)
    return {"run_id": run_id}

def youtube_search(state: RavenState) -> None:
    queries = state["queries"]
    run_id = state["run_id"]
    done = search_youtube(queries, run_id)
    return {"yt_search_done": done}

def enricher(state: RavenState):
    query = state.get("query", "")
    response = enricher_llm.invoke([
            SystemMessage(content=ENRICHER_PROMPT),
            HumanMessage(content=query),
        ])
    return {"queries": response.queries}


graph = StateGraph(RavenState)
graph.add_node("enricher", enricher)
graph.add_node("create_run", run_create)
graph.add_node("youtube_search", youtube_search)
graph.add_edge(START, "create_run")
graph.add_edge("create_run", "enricher")
graph.add_edge("enricher", "youtube_search")
graph.add_edge("youtube_search", END)
raven_graph = graph.compile()
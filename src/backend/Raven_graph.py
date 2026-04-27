import os
from typing import Literal
from dotenv import load_dotenv

from langgraph.types import Send
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from langchain_core.messages import HumanMessage, SystemMessage

from src.backend.data.prompt.ranker_tier1 import RANKER_TIER_1, TIER_1
from src.backend.data.prompt.enricher import ENRICHER_PROMPT
from src.backend.data.prompt.ranker_tier1_final import (
    RANKER_TIER1_FINAL_PROMPT,
    RANKER_TIER1_FINAL_INPUT,
    PACKET
)
from src.backend.data.search_base import search_youtube
from src.backend.db import (
    init,
    create_run,
    candidates_tier_0,
    candidates_rank,
    candidates_for_final_decision,
    candidates_final_decision,
    get_query_ids
)
from src.backend.data.state import RavenState

load_dotenv()
low_llm_key = os.environ["LOW_LLM_KEY"]
high_llm_key = os.environ["HIGH_LLM_KEY"]

#class output
class EnricherOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    queries: list[str]
    key_words: list[str]
    
class RankerTier1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sexy_label: Literal["skip", "maybe", "click", "must_click"]
    reasoning: str = Field(max_length=360)

class Tier1FinalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: int
    final_decision: Literal["keep", "throw_out"]
    reason: str = Field(max_length=220)

class Tier1FinalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: list[Tier1FinalDecision]


llm = ChatOpenAI(
    api_key=SecretStr(low_llm_key),
    model="gpt-5.4-mini",
    temperature=0.7,
    max_retries=3,
)
enricher_base_llm = ChatOpenAI(
    api_key=SecretStr(low_llm_key),
    model="gpt-5.4-mini",
    temperature=0.7,
    max_retries=3,
)
high_llm = ChatOpenAI(
    api_key=SecretStr(high_llm_key),
    model="gpt-5.5",
    temperature=0.7,
    max_retries=3,
)
enricher_llm = enricher_base_llm.with_structured_output(EnricherOutput)
ranker_tier1_llm = llm.with_structured_output(RankerTier1)
ranker_tier1_final_llm = high_llm.with_structured_output(Tier1FinalOutput)

#extra function
def make_tier1_final_packet(candidates: list[dict]) -> str:
    packet_blocks = []
    for candidate in candidates:
        packet_blocks.append(PACKET.format(
            candidate_id=candidate["id"],
            query=candidate.get("query", ""),
            sexy_label=candidate.get("sexy_label") or "",
            title=candidate.get("title", ""),
            final_verdict=candidate.get("final_verdict", ""),
            published_at=candidate.get("published_at", ""),
            view_count=candidate.get("view_count", 0)
        ))
    return "\n".join(packet_blocks)

#nodes
def run_create(state: RavenState):
    query = state["query"]
    db = init()
    run_id = create_run(db, query)
    return {"run_id": run_id, "db": db}

def youtube_search(state: RavenState) -> dict:
    queries = state["queries"]
    run_id = state["run_id"]
    key_words = state["key_words"]
    done = search_youtube(queries, run_id, key_words)
    return {"yt_search_done": done}

def enricher(state: RavenState) -> dict:
    query = state.get("query", "")
    response = enricher_llm.invoke(
            [
                SystemMessage(ENRICHER_PROMPT),
                HumanMessage(query),
            ]
        )
    return {"queries": response.queries, "key_words": response.key_words}

def ranker_tier_1(state: RavenState) -> dict:
    db = init()
    try:
        candidate = state["candidate"]
        candidate_id = candidate["id"]
        title = candidate.get("title", "")
        description = candidate.get("description", "")

        if title == "":
            return {"ranker_tier1_results": [{"id": candidate_id, "done": False}]}
        
        response = ranker_tier1_llm.invoke(
            [
                SystemMessage(RANKER_TIER_1),
                HumanMessage(TIER_1.format(title=title, description=description))
            ]
        )
        sexy_label = response.sexy_label
        reasoning = response.reasoning

        candidates_rank(db, candidate_id, sexy_label, [], [], "", "", reasoning)
        return {"ranker_tier1_results": [{"id": candidate_id, "done": True}]}
    finally:
        db.close()

def ranker_tier1_final(state: RavenState) -> dict:
    db = state["db"]
    run_id = state["run_id"]
    target = state.get("query", "")
    tier1_results = state.get("ranker_tier1_results", [])

    #check if tier 1 really done
    if not any(e["done"] for e in tier1_results) or not tier1_results:
        return {"ranker_tier1_final_done": False}

    #prepare the candidate packet
    candidates = candidates_for_final_decision(db, run_id)
    if not candidates:
        return {"ranker_tier1_final_done": False}
    candidate_packet = make_tier1_final_packet(candidates)

    response = ranker_tier1_final_llm.invoke(
        [
            SystemMessage(RANKER_TIER1_FINAL_PROMPT),
            HumanMessage(RANKER_TIER1_FINAL_INPUT.format(target=target, candidate_packet=candidate_packet))
        ]
    )

    for decision in response.decisions:
        candidates_final_decision(
            db=db,
            candidate_id=decision.candidate_id,
            final_decision=decision.final_decision,
            final_reason=decision.reason,
        )
    return {"ranker_tier1_final_done": True}

#routing
def ranker_tier1_route(state: RavenState):
    db = state["db"]
    run_id = state["run_id"]
    candidate_blocks = []

    #get candidates
    query_ids = get_query_ids(db, run_id)
    for f in query_ids:
        candidates = candidates_tier_0(db, f)
        candidate_blocks.extend(candidates)
    
    return [
        Send("ranker_tier1", {"candidate": candidate})
        for candidate in candidate_blocks
    ]


graph = StateGraph(RavenState)
graph.add_node("enricher", enricher)
graph.add_node("create_run", run_create)
graph.add_node("youtube_search", youtube_search)
graph.add_node("ranker_tier1", ranker_tier_1)
graph.add_node("ranker_tier1_final", ranker_tier1_final)

graph.add_edge(START, "create_run")
graph.add_edge("create_run", "enricher")
graph.add_edge("enricher", "youtube_search")
graph.add_conditional_edges("youtube_search", ranker_tier1_route, ["ranker_tier1"])
graph.add_edge("ranker_tier1", "ranker_tier1_final")
graph.add_edge("ranker_tier1_final", END)
raven_graph = graph.compile()
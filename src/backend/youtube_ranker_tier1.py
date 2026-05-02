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
    candidates_tier_0,
    candidates_rank,
    candidates_for_final_decision,
    candidates_final_label,
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
    final_decision: Literal["keep", "throw_out"]
    reasoning: str = Field(max_length=360)

class Tier1FinalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: int
    sexy_label: Literal["maybe", "click", "must_click"]
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
    reasoning_effort="medium",
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
            final_decision=candidate.get("final_decision") or "",
            title=candidate.get("title", ""),
            tier1_reasoning=candidate.get("tier1_reasoning", ""),
            published_at=candidate.get("published_at", ""),
            view_count=candidate.get("view_count", 0)
        ))
    return "\n".join(packet_blocks)

#nodes
def youtube_search(state: RavenState) -> dict:
    queries = state["queries"]
    run_id = state["run_id"]
    key_words = state["key_words"]
    done = search_youtube(queries, run_id, key_words)
    return {"yt_search_done": done}

def enricher(state: RavenState) -> dict:
    request = state["request"]
    response = enricher_llm.invoke(
            [
                SystemMessage(ENRICHER_PROMPT),
                HumanMessage(request),
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
        
        response = ranker_tier1_llm.invoke([
                SystemMessage(RANKER_TIER_1),
                HumanMessage(TIER_1.format(
                    request=state["request"],
                    title=title,
                    description=description
                ))
            ])
        final_decision = response.final_decision
        reasoning = response.reasoning
        candidates_rank(db, candidate_id, final_decision, reasoning)
        return {"ranker_tier1_results": [{"id": candidate_id, "done": True}]}
    finally:
        db.close()

def ranker_tier1_final(state: RavenState) -> dict:
    db = state["db"]
    run_id = state["run_id"]
    request = state["request"]
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
            HumanMessage(RANKER_TIER1_FINAL_INPUT.format(
                request=request,
                candidate_packet=candidate_packet
            ))
        ])

    for decision in response.decisions:
        candidates_final_label(
            db=db,
            candidate_id=decision.candidate_id,
            sexy_label=decision.sexy_label,
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
        Send("ranker_tier1", {
            "candidate": candidate,
            "request": state["request"]
            }
        )
        for candidate in candidate_blocks
    ]


graph = StateGraph(RavenState)
graph.add_node("enricher", enricher)
graph.add_node("youtube_search", youtube_search)
graph.add_node("ranker_tier1", ranker_tier_1)
graph.add_node("ranker_tier1_final", ranker_tier1_final)

graph.add_edge(START, "enricher")
graph.add_edge("enricher", "youtube_search")
graph.add_conditional_edges("youtube_search", ranker_tier1_route, ["ranker_tier1"])
graph.add_edge("ranker_tier1", "ranker_tier1_final")
graph.add_edge("ranker_tier1_final", END)
yt_ranker_tier1_graph = graph.compile()

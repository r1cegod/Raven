from langgraph.graph import END, START, StateGraph

from src.backend.db import (
    init,
    create_run
)
from src.backend.data.state import RavenState
from src.backend.youtube_ranker_tier1 import yt_ranker_tier1_graph


#nodes
def run_create(state: RavenState):
    request = state["request"]
    db = init()
    run_id = create_run(db, request)
    return {"run_id": run_id, "db": db}


graph = StateGraph(RavenState)
graph.add_node("create_run", run_create)
graph.add_node("yt_ranker_tier1", yt_ranker_tier1_graph)

graph.add_edge(START, "create_run")
graph.add_edge("create_run", "yt_ranker_tier1")
graph.add_edge("yt_ranker_tier1", END)
raven_graph = graph.compile()

import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, SecretStr
from src.backend.data.prompt.enricher import ENRICHER_PROMPT
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


def enricher(state: RavenState):
    query = state.get("query", "")
    response = enricher_llm.invoke([
            SystemMessage(content=ENRICHER_PROMPT),
            HumanMessage(content=query),
        ])
    return {"queries": response.queries}


graph = StateGraph(RavenState)
graph.add_node("enricher", enricher)
graph.add_edge(START, "enricher")
graph.add_edge("enricher", END)
raven_graph = graph.compile()
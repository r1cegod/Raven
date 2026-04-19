from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, ConfigDict
from dotenv import load_dotenv
import os

load_dotenv()

class EnricherOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    queries = list[str]

llm = ChatOpenAI(api_key=os.environ["ENRICHER_DEV_KEY"])
enricher_llm = llm.with_structured_output(EnricherOutput)


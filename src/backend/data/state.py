from typing import TypedDict, Any, Annotated
from operator import add


class RavenState(TypedDict, total=False):
    query: str
    queries: list[str]
    key_words: list[str]
    run_id: int
    db: Any

    yt_search_done: bool

    #ranker tier 1
    ranker_tier1_results: Annotated[list[dict], add]
    ranker_tier1_final_done: bool
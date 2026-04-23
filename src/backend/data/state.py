from typing import TypedDict


class RavenState(TypedDict, total=False):
    query: str
    queries: list[str]
    run_id: int
    yt_search_done: bool
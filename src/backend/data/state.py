from typing import TypedDict


class RavenState(TypedDict, total=False):
    query: str
    queries: list[str]

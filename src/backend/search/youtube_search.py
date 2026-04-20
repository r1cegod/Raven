import os
from dataclasses import dataclass
from typing import Any
from dotenv import load_dotenv
import json
import urllib.error
import urllib.parse
import urllib.request

load_dotenv()
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

@dataclass
class ApiResponse:
    status_code: int
    raw_response: dict[str, Any]
    error: str | None = None

@dataclass
class YoutubeSearchResult:
    query_list: list[dict[str, Any]]
    candidates_list: list[dict[str, Any]]
    error: str | None = None

def api_get() -> str | None:
    return os.getenv("YOUTUBE_API_KEY")

def youtube_call(query: str, max_results: int = 2) -> ApiResponse:

    #craft the request
    yt_api = api_get()
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "relevance",
        "maxResults": str(max(1, min(max_results, 50))),
        "safeSearch": "none",
        "key": yt_api,
    }
    url = f"{YOUTUBE_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})

    #call api
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
            return ApiResponse(status_code=response.status, raw_response=json.loads(body))
    except urllib.error.HTTPError as errors:
        body = errors.read().decode("utf-8", errors="replace")
        return ApiResponse(status_code=errors.code, raw_response=json.loads(body), error=str(errors))
    except urllib.error.URLError as errors:
        return ApiResponse(status_code=0, raw_response={"error": str(errors)}, error=str(errors))

def youtube_search(query: str, max_results: int = 2) -> YoutubeSearchResult:
    api_response = youtube_call(query, max_results)
    status_code = api_response.status_code
    raw_response = api_response.raw_response
    errors = api_response.error
    query_block = []
    candidates_block = []

    #build query
    if status_code != 0 and raw_response:
        query_pending = {
            "raw_response": raw_response,
            "status_code": status_code
        }
        query_block.append(query_pending)

    #build candidates
    for item in raw_response.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        snippet = item.get("snippet", {})

        if not video_id:
            continue

        candidates_pending = {
            "source": "youtube",
            "platform_id": video_id,
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "link": f"https://www.youtube.com/watch?v={video_id}",
            "author_or_channel": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt", "")
        }
        candidates_block.append(candidates_pending)

    return YoutubeSearchResult(query_list=query_block, candidates_list=candidates_block, error=errors)
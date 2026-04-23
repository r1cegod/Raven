import os
import json
import urllib.error
import urllib.parse
import urllib.request

from dataclasses import dataclass
from typing import Any
from dotenv import load_dotenv

load_dotenv()
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

@dataclass
class SearchResponse:
    status_code: int
    raw_response: dict[str, Any]
    error: str | None = None

@dataclass
class VideoResponse:
    status_code: int
    raw_response: dict[str, Any]
    error: str | None = None

@dataclass
class YoutubeSearchResult:
    query_list: list[dict[str, Any]]
    candidates_list: list[dict[str, Any]]
    error: list[str] | None = None
    search_list_finish: bool 
    search_list_status: int
    search_list_error: str
    video_list_finish: bool
    video_list_status: int
    video_list_error: str


def api_get() -> str | None:
    return os.getenv("YOUTUBE_API_KEY")

def searchs_call(query: str, max_results: int = 50) -> SearchResponse:

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
            return SearchResponse(status_code=response.status, raw_response=json.loads(body))
    except urllib.error.HTTPError as errors:
        body = errors.read().decode("utf-8", errors="replace")
        return SearchResponse(status_code=errors.code, raw_response=json.loads(body), error=str(errors))
    except urllib.error.URLError as errors:
        return SearchResponse(status_code=0, raw_response={"error": str(errors)}, error=str(errors))
    
def videos_call(video_ids: list[str]) -> VideoResponse:

    #craft the request
    yt_api = api_get()
    params = {
        "part": "snippet,statistics",
        "id": ",".join(video_ids),
        "key": yt_api,
    }
    url = f"{YOUTUBE_VIDEOS_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})

    #call api
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
            return VideoResponse(status_code=response.status, raw_response=json.loads(body))
    except urllib.error.HTTPError as errors:
        body = errors.read().decode("utf-8", errors="replace")
        return VideoResponse(status_code=errors.code, raw_response=json.loads(body), error=str(errors))
    except urllib.error.URLError as errors:
        return VideoResponse(status_code=0, raw_response={"error": str(errors)}, error=str(errors))

def youtube_search(query: str, max_results: int) -> YoutubeSearchResult:
    candidates_block = []
    query_block = []
    errors = []

    search_error = "None"
    video_error = "None"
    video_status = 0
    video_list_finish = False

    #search call
    search_response = searchs_call(query, max_results)
    search_status = search_response.status_code
    search_raw = search_response.raw_response
    search_items = search_raw.get("items", [])
    if search_response.error:
        errors.append(str(search_response.error))
        search_error = str(search_response.error)

    #gather ids
    video_ids = []
    for item in search_raw.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        video_ids.append(video_id)

    if video_ids:
        #video call
        video_response = videos_call(video_ids)
        video_raw = video_response.raw_response
        video_status = video_response.status_code
        video_items = video_raw.get("items", [])
        if video_response.error:
            errors.append(str(video_response.error))
            video_error = str(video_response.error)
        if video_status == 200:
            video_list_finish = True

        enriched_by_id = {
            item.get("id", ""): item
            for item in video_items
            if item.get("id")
        }

        #build query
        if search_status != 0 and search_raw:
            query_pending = {
                "query": query,
                "raw_response": search_raw,
                "status_code": search_status,
                "source": "youtube"
            }
            query_block.append(query_pending)

            #build candidates
            if video_status != 0 and video_raw:
                for item in search_items:
                    video_id = item.get("id", {}).get("videoId")
                    snippet = item.get("snippet", {})
                    if not video_id:
                        continue

                    #get the candidate item the same video id
                    enriched_item = enriched_by_id.get(video_id, {})
                    enriched_snippet = enriched_item.get("snippet", {})
                    enriched_stats = enriched_item.get("statistics", {})
                    raw_view_count = enriched_stats.get("viewCount", 0)
                    view_count = int(raw_view_count)

                    if view_count >= 10000:
                        candidates_pending = {
                            "source": "youtube",
                            "platform_id": video_id,
                            "title": snippet.get("title", ""),
                            "description": snippet.get("description", ""),
                            "link": f"https://www.youtube.com/watch?v={video_id}",
                            "author_or_channel": snippet.get("channelTitle", ""),
                            "published_at": snippet.get("publishedAt", ""),
                            "channel_id": enriched_snippet.get("channelId", ""),
                            "channel_title": enriched_snippet.get("channelTitle", ""),
                            "view_count": view_count
                        }
                        candidates_block.append(candidates_pending)

    return YoutubeSearchResult(
        query_list=query_block, 
        candidates_list=candidates_block, 
        error=errors,
        search_list_finish=search_status == 200, 
        search_list_status=search_status,
        search_list_error=search_error,
        video_list_finish=video_list_finish,
        video_list_status=video_status,
        video_list_error=video_error
        )
import os
import json
import urllib.error
import urllib.parse
import urllib.request

from dataclasses import dataclass
from typing import Any
from dotenv import load_dotenv

from datetime import datetime, timezone, timedelta

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
    search_list_finish: bool 
    search_list_status: int
    search_list_error: str
    video_list_finish: bool
    video_list_status: int
    video_list_error: str
    error: list[str] | None = None


def api_get() -> str | None:
    return os.getenv("YOUTUBE_API_KEY")

#key word filter
def title_has_key_word(title: str, key_words: list[str]) -> bool:
    title_lower = title.lower()
    return any(
        key_word.lower() in title_lower
        for key_word in key_words
    )

#date filter
def parse_youtube_published_at(published_at: str) -> datetime | None:
    if not published_at:
        return None
    try:
        return datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )
    except ValueError:
        return None

def is_recent_enough(published_at: str, max_age_days: int = 365) -> bool:
    published_dt = parse_youtube_published_at(published_at)
    if published_dt is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    return published_dt >= cutoff


#call yt api
def searchs_call(query: str, max_results: int = 50, duration: str = "medium") -> SearchResponse:

    #craft the request
    yt_api = api_get()
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "relevance",
        "videoDuration": duration,
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


#compile the results
def youtube_search(query: str, max_results: int, key_words: list[str]) -> YoutubeSearchResult:
    candidates_block = []
    query_block = []
    errors = []

    search_error = "None"
    video_error = "None"
    video_status = 0
    video_list_finish = False

    #search call
    search_items = []
    raw_responses = {}
    search_statuses = []
    for duration in ["medium", "long"]:
        search_response = searchs_call(query, max_results, duration)
        search_statuses.append(search_response.status_code)
        raw_responses[duration] = search_response.raw_response
        search_items.extend(search_response.raw_response.get("items", []))
        if search_response.error:
            errors.append(str(search_response.error))
    search_status = 200 if search_statuses and all(status == 200 for status in search_statuses) else 0
    search_raw = {"duration_searches": raw_responses}
    if errors:
        search_error = " | ".join(errors)

    #gather ids
    video_ids = []
    seen_video_ids = set()
    for item in search_items:
        video_id = item.get("id", {}).get("videoId")
        if not video_id or video_id in seen_video_ids:
            continue
        seen_video_ids.add(video_id)
        video_ids.append(video_id)

    if video_ids:
        #video call
        video_items = []
        video_raw = {"items": []}
        video_statuses = []
        for start in range(0, len(video_ids), 50):
            video_response = videos_call(video_ids[start:start + 50])
            video_statuses.append(video_response.status_code)
            video_items.extend(video_response.raw_response.get("items", []))
            if video_response.error:
                errors.append(str(video_response.error))
        video_raw["items"] = video_items
        video_status = 200 if video_statuses and all(status == 200 for status in video_statuses) else 0
        if errors:
            video_error = " | ".join(errors)
        video_list_finish = video_status == 200

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
                seen_candidate_ids = set()
                for item in search_items:
                    video_id = item.get("id", {}).get("videoId")
                    snippet = item.get("snippet", {})
                    if not video_id or video_id in seen_candidate_ids:
                        continue
                    seen_candidate_ids.add(video_id)

                    #get the candidate item the same video id
                    enriched_item = enriched_by_id.get(video_id, {})
                    enriched_snippet = enriched_item.get("snippet", {})
                    enriched_stats = enriched_item.get("statistics", {})
                    raw_view_count = enriched_stats.get("viewCount", 0)
                    publish_date = snippet.get("publishedAt", "")
                    view_count = int(raw_view_count)
                    title = snippet.get("title", "")

                    if view_count >= 40000 and is_recent_enough(published_at=publish_date) and title_has_key_word(title, key_words):
                        candidates_pending = {
                            "source": "youtube",
                            "platform_id": video_id,
                            "title": title,
                            "description": snippet.get("description", ""),
                            "link": f"https://www.youtube.com/watch?v={video_id}",
                            "author_or_channel": snippet.get("channelTitle", ""),
                            "published_at": publish_date,
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
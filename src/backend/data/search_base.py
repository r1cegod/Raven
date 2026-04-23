import json, sqlite3

from src.backend.search.youtube_search import youtube_search
from src.backend.db import create_query, create_candidate, init, create_query_log, create_api_log, create_candidate_log


def search_youtube(queries: list[str], run_id: int) -> bool:
    runs = []

    for query_index, query in enumerate(queries):
        result = youtube_search(query, 50)
        search_finish = result.search_list_finish
        search_status = result.search_list_status
        search_error = result.search_list_error
        video_finish = result.video_list_finish
        video_status = result.video_list_status
        video_error = result.video_list_error

        #unpack items
        query_item = result.query_list[0] if result.query_list else None
        candidate_items = result.candidates_list

        #query create/log
        if not query_item:
            runs.append(False)
            continue
        query_payload = {
            "run_id": run_id, 
            "raw_response": json.dumps(query_item["raw_response"]),
            "status_code": query_item["status_code"],
            "query": query, 
            "query_index": query_index, 
            "source": query_item["source"]
        }
        db = init()
        query_id=None
        try:
            query_id = create_query(db, **query_payload)
            query_log_id = create_query_log(db=db, run_id=run_id, query_id=query_id, query=query, query_create=True, error_raw= "None")
        except sqlite3.IntegrityError as e:
            query_log_id = create_query_log(db=db, run_id=run_id, query_id=query_id, query=query, query_create=False, error_raw=str(e))

        #compile api log
        api_log_id = create_api_log(
            db=db,
            query_log_id=query_log_id,
            search_list_finish = search_finish, 
            search_list_status = search_status,
            search_list_error = search_error,
            video_list_finish = video_finish,
            video_list_status = video_status,
            video_list_error = video_error
        )

        #create and log candidates
        if not candidate_items:
            runs.append(False)
            continue
        for candidate in candidate_items:
            if not query_id:
                runs.append(False)
                continue
            candidate_payload = {
                "run_id": run_id, 
                "query_id": query_id, 
                "source": candidate["source"], 
                "platform_id": candidate["platform_id"], 
                "title": candidate["title"], 
                "description": candidate["description"], 
                "link": candidate["link"], 
                "author_or_channel": candidate["author_or_channel"], 
                "published_at": candidate["published_at"], 
                "channel_id": candidate["channel_id"],
                "channel_title": candidate["channel_title"],
                "view_count": candidate["view_count"]
            }
            
            candidate_id = create_candidate(db, **candidate_payload)
            if candidate_id is None:
                continue
            create_candidate_log(
                db=db, 
                run_id=run_id, 
                query_id=query_id, 
                query_log_id=query_log_id,
                api_log_id=api_log_id,
                candidate_create=True,
                error_raw="None",
            )

        runs.append(True)
    if False in runs:
        return False
    else:
        return True
from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import Any

from src.backend.observability.common import DEFAULT_DB_PATH


def connect_readonly(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    uri = f"file:{path.resolve()}?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    return db


def _rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def _youtube_search_filter_stats(raw_response: str | None, candidate_count: int) -> dict[str, Any]:
    if not raw_response:
        return {
            "raw_items": 0,
            "unique_video_ids": 0,
            "duplicate_items": 0,
            "candidate_count": candidate_count,
            "filtered_out": 0,
        }

    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError:
        return {
            "raw_items": 0,
            "unique_video_ids": 0,
            "duplicate_items": 0,
            "candidate_count": candidate_count,
            "filtered_out": 0,
        }

    duration_searches = payload.get("duration_searches", {})
    raw_items = 0
    video_ids: list[str] = []
    for response in duration_searches.values():
        items = response.get("items", []) if isinstance(response, dict) else []
        raw_items += len(items)
        for item in items:
            if not isinstance(item, dict):
                continue
            video_id = item.get("id", {}).get("videoId")
            if video_id:
                video_ids.append(video_id)

    unique_video_ids = len(set(video_ids))
    return {
        "raw_items": raw_items,
        "unique_video_ids": unique_video_ids,
        "duplicate_items": max(0, len(video_ids) - unique_video_ids),
        "candidate_count": candidate_count,
        "filtered_out": max(0, unique_video_ids - candidate_count),
    }


def get_run_metadata(run_id: int, db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    with connect_readonly(db_path) as db:
        row = db.execute(
            """
            SELECT id, created_at, request
            FROM raven_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        return dict(row) if row else None


def get_query_api_candidate_summary(
    run_id: int,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with connect_readonly(db_path) as db:
        queries = _rows(
            db.execute(
                """
                SELECT id, query_index, source, status_code, query
                FROM raven_queries
                WHERE run_id = ?
                ORDER BY query_index, id
                """,
                (run_id,),
            )
        )
        api_logs = _rows(
            db.execute(
                """
                SELECT
                    ql.query,
                    al.search_list_finish,
                    al.search_list_status,
                    al.search_list_error,
                    al.video_list_finish,
                    al.video_list_status,
                    al.video_list_error
                FROM query_log ql
                LEFT JOIN api_log al ON al.query_log_id = ql.id
                WHERE ql.run_id = ?
                ORDER BY ql.id
                """,
                (run_id,),
            )
        )
        candidate_counts = _rows(
            db.execute(
                """
                SELECT q.query, COUNT(c.id) AS candidate_count
                FROM raven_queries q
                LEFT JOIN raven_candidates c ON c.query_id = q.id
                WHERE q.run_id = ?
                GROUP BY q.id
                ORDER BY q.query_index, q.id
                """,
                (run_id,),
            )
        )
        filter_stats_rows = _rows(
            db.execute(
                """
                SELECT q.query, q.raw_response, COUNT(c.id) AS candidate_count
                FROM raven_queries q
                LEFT JOIN raven_candidates c ON c.query_id = q.id
                WHERE q.run_id = ?
                GROUP BY q.id
                ORDER BY q.query_index, q.id
                """,
                (run_id,),
            )
        )
        filter_stats = [
            {
                "query": row.get("query"),
                **_youtube_search_filter_stats(
                    row.get("raw_response"),
                    int(row.get("candidate_count") or 0),
                ),
            }
            for row in filter_stats_rows
        ]
    return {
        "queries": queries,
        "api_logs": api_logs,
        "candidate_counts": candidate_counts,
        "filter_stats": filter_stats,
    }


def get_tier1_rows(run_id: int, db_path: Path | str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with connect_readonly(db_path) as db:
        return _rows(
            db.execute(
                """
                SELECT
                    c.id,
                    q.query,
                    c.source,
                    c.platform_id,
                    c.title,
                    SUBSTR(c.description, 1, 240) AS description_excerpt,
                    c.link,
                    c.author_or_channel,
                    c.channel_title,
                    c.published_at,
                    c.view_count,
                    c.final_decision,
                    c.positive_pull,
                    c.negative_push,
                    c.title_pull,
                    c.preview_pull,
                    c.final_verdict
                FROM raven_candidates c
                JOIN raven_queries q ON q.id = c.query_id
                WHERE c.run_id = ?
                ORDER BY c.id
                """,
                (run_id,),
            )
        )


def get_final_decision_rows(
    run_id: int,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    with connect_readonly(db_path) as db:
        return _rows(
            db.execute(
                """
                SELECT
                    c.id,
                    q.query,
                    c.title,
                    c.published_at,
                    c.view_count,
                    c.final_decision,
                    c.sexy_label,
                    c.final_reason
                FROM raven_candidates c
                JOIN raven_queries q ON q.id = c.query_id
                WHERE c.run_id = ?
                  AND c.sexy_label IS NOT NULL
                ORDER BY
                    CASE c.sexy_label
                        WHEN 'must_click' THEN 1
                        WHEN 'click' THEN 2
                        WHEN 'maybe' THEN 3
                        ELSE 4
                    END,
                    c.id
                """,
                (run_id,),
            )
        )


def get_run_counts(run_id: int, db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, Any]:
    with connect_readonly(db_path) as db:
        query_count = db.execute(
            "SELECT COUNT(*) FROM raven_queries WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        candidate_count = db.execute(
            "SELECT COUNT(*) FROM raven_candidates WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        tier1_decision_counts = _rows(
            db.execute(
                """
                SELECT COALESCE(final_decision, 'undecided') AS decision, COUNT(*) AS count
                FROM raven_candidates
                WHERE run_id = ?
                GROUP BY COALESCE(final_decision, 'undecided')
                ORDER BY count DESC, decision
                """,
                (run_id,),
            )
        )
        final_label_counts = _rows(
            db.execute(
                """
                SELECT COALESCE(sexy_label, 'unlabeled') AS label, COUNT(*) AS count
                FROM raven_candidates
                WHERE run_id = ?
                GROUP BY COALESCE(sexy_label, 'unlabeled')
                ORDER BY count DESC, label
                """,
                (run_id,),
            )
        )
    return {
        "query_count": query_count,
        "candidate_count": candidate_count,
        "tier1_decision_counts": tier1_decision_counts,
        "final_label_counts": final_label_counts,
    }


def summarize_run(run_id: int, db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, Any]:
    metadata = get_run_metadata(run_id, db_path)
    if metadata is None:
        return {"run_id": run_id, "found": False}

    return {
        "found": True,
        "metadata": metadata,
        "counts": get_run_counts(run_id, db_path),
        "search": get_query_api_candidate_summary(run_id, db_path),
        "tier1_rows": get_tier1_rows(run_id, db_path),
        "final_decisions": get_final_decision_rows(run_id, db_path),
    }

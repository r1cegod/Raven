import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo


def now_time() -> str:
    time_now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    formated_time = time_now.strftime("%H:%M:%S ngày %d/%m/%Y")
    return formated_time


def connect(path: str = "src/backend/data/raven.sqlite") -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def create_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS raven_runs (
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            target TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS raven_queries (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES raven_runs(id),
            created_at TEXT NOT NULL,
            raw_response TEXT,
            status_code INTEGER,
            query TEXT NOT NULL,
            query_index INTEGER NOT NULL,
            source TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS raven_candidates (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES raven_runs(id),
            query_id INTEGER NOT NULL REFERENCES raven_queries(id),
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            platform_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            link TEXT NOT NULL UNIQUE,
            author_or_channel TEXT NOT NULL,
            published_at TEXT NOT NULL,
            source_metric TEXT NOT NULL,
            UNIQUE(source, platform_id)
        );
    """)

def init(path: str) -> None:
    db = connect(path)
    create_query(db)

def create_run(
    db: sqlite3.Connection, 
    target: str
    ) -> int:

    cursor = db.execute(
        "INSERT INTO raven_runs (target, created_at) VALUES (?, ?)",
        (target, now_time())
    )
    db.commit()
    return cursor.lastrowid


def create_query(
    db: sqlite3.Connection, 
    run_id: int, 
    raw_response: str,
    status_code: int,
    query: str, 
    query_index: int, 
    source: str
    ) -> int:

    cursor = db.execute(
        "INSERT INTO raven_queries (run_id, created_at, raw_response, status_code, query, query_index, source) VALUES (?, ?, ?, ?, ?, ? ,?)",
        (run_id, now_time(), raw_response, status_code, query, query_index, source)
    )
    db.commit()
    return cursor.lastrowid


def create_candidate(
    db: sqlite3.Connection, 
    run_id: int, 
    query_id: int, 
    source: str, 
    platform_id: str, 
    title: str, 
    description: str, 
    link: str, 
    author_or_channel: str, 
    published_at: str, 
    source_metric: str
    ) -> int:

    cursor = db.execute(
        "INSERT INTO raven_candidates (run_id, query_id, created_at, source, platform_id, title, description, link, author_or_channel, published_at, source_metric) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, query_id, now_time(), source, platform_id, title, description, link, author_or_channel, published_at, source_metric)
    )
    db.commit()
    return cursor.lastrowid


def list_run_candidates(db: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    rows = db.execute(
        """SELECT 
            raven_runs.target AS run_target,
            raven_queries.source AS query_source,
            raven_queries.query AS query_text,
            raven_candidates.source AS candidate_source,
            raven_candidates.title AS candidate_title,
            raven_candidates.link AS candidate_link
        FROM raven_candidates 
        JOIN raven_runs ON raven_runs.id = raven_candidates.run_id 
        JOIN raven_queries ON raven_queries.id = raven_candidates.query_id
        WHERE raven_runs.id = ? 
        ORDER BY raven_queries.query_index, raven_candidates.id
        """,
        (run_id,)
    ).fetchall()
    return rows

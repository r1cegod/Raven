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
            channel_id TEXT NOT NULL,
            channel_title TEXT NOT NULL,
            view_count INTEGER NOT NULL,
            UNIQUE(source, platform_id)
        );
                     
        CREATE TABLE IF NOT EXISTS query_log (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES raven_runs(id),
            query_id INTEGER REFERENCES raven_queries(id),
            created_at TEXT NOT NULL,
            query TEXT NOT NULL,
            query_create BOOLEAN DEFAULT 1,
            error_raw TEXT
        );

        CREATE TABLE IF NOT EXISTS candidate_log (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES raven_runs(id),
            query_id INTEGER NOT NULL REFERENCES raven_queries(id),
            query_log_id INTEGER NOT NULL REFERENCES query_log(id),
            api_log_id INTEGER NOT NULL REFERENCES api_log(id),
            created_at TEXT NOT NULL,
            candidate_create BOOLEAN DEFAULT 1,
            error_raw TEXT
        );
                     
        CREATE TABLE IF NOT EXISTS api_log (
            id INTEGER PRIMARY KEY,
            query_log_id INTEGER REFERENCES query_log(id),
            created_at TEXT NOT NULL,
            search_list_finish BOOLEAN DEFAULT 1,
            search_list_status INTEGER NOT NULL,
            search_list_error TEXT,
            video_list_finish BOOLEAN DEFAULT 1,
            video_list_status INTEGER NOT NULL,
            video_list_error TEXT
        );  
                                  
    """)

def init(path: str = "src/backend/data/raven.sqlite") -> sqlite3.Connection:
    db = connect(path)
    create_schema(db)
    return db

#CREATEEE
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
    channel_id: str,
    channel_title: str,
    view_count: int
    ) -> int | None:

    cursor = db.execute(
        "INSERT OR IGNORE INTO raven_candidates (run_id, query_id, created_at, source, platform_id, title, description, link, author_or_channel, published_at, channel_id, channel_title, view_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? ,?)",
        (run_id, query_id, now_time(), source, platform_id, title, description, link, author_or_channel, published_at, channel_id, channel_title, view_count)
    )
    db.commit()
    
    if cursor.rowcount == 0:
        return None
    return cursor.lastrowid

def create_query_log(
    db: sqlite3.Connection, 
    run_id: int, 
    query_id: int | None, 
    query: str,
    query_create: bool,
    error_raw: str
) -> int:
    cursor = db.execute(
        "INSERT INTO query_log (run_id, query_id, created_at, query, query_create, error_raw) VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, query_id, now_time(), query, query_create, error_raw)
    )
    db.commit()
    return cursor.lastrowid

def create_candidate_log(
    db: sqlite3.Connection, 
    run_id: int, 
    query_id: int, 
    query_log_id: int,
    api_log_id: int,
    candidate_create: bool,
    error_raw: str,
) -> int:
    cursor = db.execute(
        "INSERT INTO candidate_log (run_id, query_id, query_log_id, api_log_id, created_at, candidate_create, error_raw) VALUES (?, ? ,?, ?, ?, ?, ?)",
        (run_id, query_id, query_log_id, api_log_id, now_time(), candidate_create, error_raw)
    )
    db.commit()
    return cursor.lastrowid

def create_api_log(
    db: sqlite3.Connection, 
    query_log_id: int,
    search_list_finish: bool,
    search_list_status: int,
    search_list_error: str,
    video_list_finish: bool,
    video_list_status: int,
    video_list_error:str
) -> int:
    cursor = db.execute(
        "INSERT INTO api_log (query_log_id, created_at, search_list_finish, search_list_status, search_list_error, video_list_finish, video_list_status, video_list_error) VALUES (?, ?, ?, ?, ?, ? ,? ,?)",
        (query_log_id, now_time(), search_list_finish, search_list_status, search_list_error, video_list_finish, video_list_status, video_list_error)
    )
    db.commit()
    return cursor.lastrowid
"""SQLite database initialization and connection helper."""
import aiosqlite
from app.config import settings

SQL_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS analyses (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    dataset_source  TEXT NOT NULL,
    dataset_id      TEXT NOT NULL,
    dataset_name    TEXT NOT NULL,
    dataset_url     TEXT,
    num_rows        INTEGER,
    num_columns     INTEGER,
    column_names    TEXT,
    analysis_config TEXT NOT NULL,
    analysis_result TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS visualizations (
    id              TEXT PRIMARY KEY,
    analysis_id     TEXT NOT NULL,
    chart_type      TEXT NOT NULL,
    title           TEXT NOT NULL,
    plotly_json     TEXT NOT NULL,
    display_order   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS search_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query           TEXT NOT NULL,
    result_count    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'open'
                    CHECK(status IN ('open','in_progress','solved','wont_fix')),
    priority    TEXT NOT NULL DEFAULT 'medium'
                    CHECK(priority IN ('low','medium','high','critical')),
    tags        TEXT NOT NULL DEFAULT '[]',
    resolution  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    solved_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_viz_analysis_id ON visualizations(analysis_id);
CREATE INDEX IF NOT EXISTS idx_search_query ON search_history(query);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority);
CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON tickets(created_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    is_feedback INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


async def get_db() -> aiosqlite.Connection:
    """Get a database connection."""
    db = await aiosqlite.connect(settings.database_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    """Create tables if they don't exist."""
    db = await get_db()
    try:
        await db.executescript(SQL_CREATE_TABLES)
        await db.commit()
    finally:
        await db.close()

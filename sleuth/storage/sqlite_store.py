"""SQLite drawer for jobs and runs. Stdlib only."""

from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sleuth.config import get_settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    system TEXT,
    max_tokens INTEGER DEFAULT 4096,
    temperature REAL,
    web_search INTEGER DEFAULT 1,
    schedule_label TEXT,
    cron_expr TEXT,
    sync_drive INTEGER DEFAULT 0,
    notify INTEGER DEFAULT 1,
    reddit_enabled INTEGER DEFAULT 0,
    reddit_spec_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    prompt TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    output TEXT,
    citations_json TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    search_calls INTEGER DEFAULT 0,
    error TEXT,
    gdrive_url TEXT,
    output_path TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_job ON runs(job_id);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
"""


def new_id(prefix: str = "") -> str:
    """Short, sortable-ish id. Eight hex chars is plenty for personal use."""
    rand = secrets.token_hex(4)
    return f"{prefix}{rand}" if prefix else rand


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    name: str
    prompt: str
    provider: str
    model: str
    system: Optional[str] = None
    max_tokens: int = 4096
    temperature: Optional[float] = None
    web_search: bool = True
    schedule_label: Optional[str] = None
    cron_expr: Optional[str] = None
    sync_drive: bool = False
    notify: bool = True
    reddit_enabled: bool = False
    reddit_spec: Optional[dict[str, Any]] = None
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)


@dataclass
class Run:
    id: str
    job_id: Optional[str]
    prompt: str
    provider: str
    model: str
    started_at: str
    finished_at: Optional[str] = None
    status: str = "running"  # running | done | error
    output: Optional[str] = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    search_calls: int = 0
    error: Optional[str] = None
    gdrive_url: Optional[str] = None
    output_path: Optional[str] = None


_JOB_MIGRATIONS: list[tuple[str, str]] = [
    # (column name, ALTER TABLE fragment)
    ("reddit_enabled", "reddit_enabled INTEGER DEFAULT 0"),
    ("reddit_spec_json", "reddit_spec_json TEXT"),
]


def _migrate_jobs(conn: sqlite3.Connection) -> None:
    """Idempotent ALTER TABLE for columns added after the original schema."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
    for col, ddl in _JOB_MIGRATIONS:
        if col not in cols:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {ddl}")


class SqliteStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        _migrate_jobs(self._conn)

    # --- jobs ---

    def create_job(self, job: Job) -> Job:
        self._conn.execute(
            """
            INSERT INTO jobs (id, name, prompt, provider, model, system,
                              max_tokens, temperature, web_search,
                              schedule_label, cron_expr, sync_drive, notify,
                              reddit_enabled, reddit_spec_json,
                              created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id, job.name, job.prompt, job.provider, job.model,
                job.system, job.max_tokens, job.temperature,
                int(job.web_search), job.schedule_label, job.cron_expr,
                int(job.sync_drive), int(job.notify),
                int(job.reddit_enabled),
                json.dumps(job.reddit_spec) if job.reddit_spec else None,
                job.created_at, job.updated_at,
            ),
        )
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return _row_to_job(row) if row else None

    def list_jobs(self) -> list[Job]:
        rows = self._conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_job(r) for r in rows]

    def update_job_schedule(
        self, job_id: str, schedule_label: Optional[str], cron_expr: Optional[str]
    ) -> None:
        self._conn.execute(
            """UPDATE jobs SET schedule_label = ?, cron_expr = ?, updated_at = ?
               WHERE id = ?""",
            (schedule_label, cron_expr, utcnow(), job_id),
        )

    _UPDATABLE = {
        "name", "prompt", "provider", "model", "system",
        "max_tokens", "temperature",
        "web_search", "sync_drive", "notify",
        "reddit_enabled", "reddit_spec",
    }
    _BOOL_FIELDS = {"web_search", "sync_drive", "notify", "reddit_enabled"}
    _JSON_FIELDS = {"reddit_spec"}
    _COLUMN_ALIASES = {"reddit_spec": "reddit_spec_json"}

    def update_job(self, job_id: str, **fields: Any) -> None:
        """Patch one or more fields on a saved job. Bumps updated_at."""
        if self.get_job(job_id) is None:
            raise KeyError(job_id)
        unknown = set(fields) - self._UPDATABLE
        if unknown:
            raise ValueError(f"unknown field(s): {sorted(unknown)}")

        clauses: list[str] = []
        values: list[Any] = []
        for k, v in fields.items():
            if k in self._BOOL_FIELDS and v is not None:
                v = int(bool(v))
            if k in self._JSON_FIELDS:
                v = json.dumps(v) if v is not None else None
            col = self._COLUMN_ALIASES.get(k, k)
            clauses.append(f"{col} = ?")
            values.append(v)
        clauses.append("updated_at = ?")
        values.append(utcnow())
        values.append(job_id)
        self._conn.execute(
            f"UPDATE jobs SET {', '.join(clauses)} WHERE id = ?",
            values,
        )

    def delete_job(self, job_id: str) -> None:
        self._conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    # --- runs ---

    def start_run(self, run: Run) -> Run:
        self._conn.execute(
            """
            INSERT INTO runs (id, job_id, prompt, provider, model, started_at,
                              status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.id, run.job_id, run.prompt, run.provider, run.model,
                run.started_at, run.status,
            ),
        )
        return run

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        output: Optional[str] = None,
        citations: Optional[list[dict[str, Any]]] = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        search_calls: int = 0,
        error: Optional[str] = None,
        gdrive_url: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE runs SET finished_at = ?, status = ?, output = ?,
                            citations_json = ?, tokens_in = ?, tokens_out = ?,
                            search_calls = ?, error = ?, gdrive_url = ?,
                            output_path = ?
            WHERE id = ?
            """,
            (
                utcnow(), status, output,
                json.dumps(citations or []),
                tokens_in, tokens_out, search_calls,
                error, gdrive_url, output_path,
                run_id,
            ),
        )

    def get_run(self, run_id: str) -> Optional[Run]:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        return _row_to_run(row) if row else None

    def list_runs(self, *, job_id: Optional[str] = None, limit: int = 25) -> list[Run]:
        if job_id:
            rows = self._conn.execute(
                "SELECT * FROM runs WHERE job_id = ? ORDER BY started_at DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_run(r) for r in rows]

    def close(self) -> None:
        self._conn.close()


def _row_to_job(row: sqlite3.Row) -> Job:
    reddit_spec: Optional[dict[str, Any]] = None
    raw_spec = _row_get(row, "reddit_spec_json")
    if raw_spec:
        try:
            parsed = json.loads(raw_spec)
            if isinstance(parsed, dict):
                reddit_spec = parsed
        except json.JSONDecodeError:
            reddit_spec = None
    return Job(
        id=row["id"],
        name=row["name"],
        prompt=row["prompt"],
        provider=row["provider"],
        model=row["model"],
        system=row["system"],
        max_tokens=row["max_tokens"] or 4096,
        temperature=row["temperature"],
        web_search=bool(row["web_search"]),
        schedule_label=row["schedule_label"],
        cron_expr=row["cron_expr"],
        sync_drive=bool(row["sync_drive"]),
        notify=bool(row["notify"]),
        reddit_enabled=bool(_row_get(row, "reddit_enabled") or 0),
        reddit_spec=reddit_spec,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_get(row: sqlite3.Row, key: str) -> Any:
    """sqlite3.Row.__getitem__ raises if the column is missing; we want None."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def _row_to_run(row: sqlite3.Row) -> Run:
    citations: list[dict[str, Any]] = []
    if row["citations_json"]:
        try:
            citations = json.loads(row["citations_json"])
        except json.JSONDecodeError:
            citations = []
    return Run(
        id=row["id"],
        job_id=row["job_id"],
        prompt=row["prompt"],
        provider=row["provider"],
        model=row["model"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        status=row["status"],
        output=row["output"],
        citations=citations,
        tokens_in=row["tokens_in"] or 0,
        tokens_out=row["tokens_out"] or 0,
        search_calls=row["search_calls"] or 0,
        error=row["error"],
        gdrive_url=row["gdrive_url"],
        output_path=row["output_path"],
    )


_store: Optional[SqliteStore] = None


def get_store() -> SqliteStore:
    global _store
    if _store is None:
        _store = SqliteStore(get_settings().db_path)
    return _store

"""Local-only telemetry for mcp-manager usage tracking.

Opt-in via MCP_MANAGER_TELEMETRY=1 environment variable.
All data stays on disk — never transmitted anywhere.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from mcp_manager.exceptions import McpManagerError

_ENV_VAR = "MCP_MANAGER_TELEMETRY"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    name TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
"""


def is_enabled() -> bool:
    """Check if telemetry is opt-in enabled."""
    return os.environ.get(_ENV_VAR, "").strip() == "1"


def _telemetry_dir() -> Path:
    """Get the telemetry directory."""
    from mcp_manager.config import MANAGER_CONFIG_DIR

    return MANAGER_CONFIG_DIR


class TelemetryStore:
    """SQLite WAL store for local telemetry events."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(str(db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
        except sqlite3.Error as e:
            raise McpManagerError(f"Failed to initialize telemetry database: {e}") from e

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> TelemetryStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def record(
        self,
        event_type: str,
        name: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        try:
            self._conn.execute(
                "INSERT INTO events (event_type, name, timestamp, metadata) VALUES (?, ?, ?, ?)",
                (
                    event_type,
                    name,
                    datetime.now(UTC).isoformat(),
                    json.dumps(metadata or {}),
                ),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            raise McpManagerError(f"Failed to record telemetry event: {e}") from e

    def get_command_counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT name, COUNT(*) as cnt FROM events"
            " WHERE event_type = 'command'"
            " GROUP BY name ORDER BY cnt DESC"
        ).fetchall()
        return {r["name"]: r["cnt"] for r in rows}

    def get_pro_gate_counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT name, COUNT(*) as cnt FROM events"
            " WHERE event_type = 'pro_gate'"
            " GROUP BY name ORDER BY cnt DESC"
        ).fetchall()
        return {r["name"]: r["cnt"] for r in rows}

    def get_total_events(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM events").fetchone()
        return int(row["cnt"])

    def get_first_event_time(self) -> str | None:
        row = self._conn.execute("SELECT MIN(timestamp) as ts FROM events").fetchone()
        return row["ts"] if row and row["ts"] else None

    def get_last_event_time(self) -> str | None:
        row = self._conn.execute("SELECT MAX(timestamp) as ts FROM events").fetchone()
        return row["ts"] if row and row["ts"] else None

    def get_daily_activity(self, last_n_days: int = 7) -> list[tuple[str, int]]:
        rows = self._conn.execute(
            "SELECT DATE(timestamp) as day, COUNT(*) as cnt FROM events"
            " GROUP BY DATE(timestamp) ORDER BY day DESC LIMIT ?",
            (last_n_days,),
        ).fetchall()
        return [(r["day"], r["cnt"]) for r in rows]

    def reset(self) -> None:
        self._conn.execute("DELETE FROM events")
        self._conn.commit()


# --- Module-level singleton ---

_store_instance: TelemetryStore | None = None


def _get_store() -> TelemetryStore | None:
    global _store_instance
    if not is_enabled():
        return None
    if _store_instance is None:
        db_path = _telemetry_dir() / "telemetry.db"
        _store_instance = TelemetryStore(db_path)
    return _store_instance


def reset_telemetry_store() -> None:
    global _store_instance
    if _store_instance is not None:
        _store_instance.close()
    _store_instance = None


def track_command(name: str) -> None:
    store = _get_store()
    if store is not None:
        store.record("command", name)


def track_pro_gate(feature: str) -> None:
    store = _get_store()
    if store is not None:
        store.record("pro_gate", feature)

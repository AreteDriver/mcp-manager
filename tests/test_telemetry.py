"""Tests for mcp-manager telemetry module."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_manager.exceptions import McpManagerError
from mcp_manager.telemetry import (
    TelemetryStore,
    is_enabled,
    reset_telemetry_store,
    track_command,
    track_pro_gate,
)


@pytest.fixture
def telemetry_db(tmp_path: Path) -> Path:
    return tmp_path / "telemetry.db"


@pytest.fixture
def store(telemetry_db: Path) -> TelemetryStore:
    s = TelemetryStore(telemetry_db)
    yield s
    s.close()


class TestIsEnabled:
    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_MANAGER_TELEMETRY", raising=False)
        assert is_enabled() is False

    def test_disabled_when_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_MANAGER_TELEMETRY", "0")
        assert is_enabled() is False

    def test_enabled_when_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_MANAGER_TELEMETRY", "1")
        assert is_enabled() is True

    def test_enabled_with_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_MANAGER_TELEMETRY", " 1 ")
        assert is_enabled() is True


class TestTelemetryStore:
    def test_record_command(self, store: TelemetryStore) -> None:
        store.record("command", "list")
        assert store.get_command_counts() == {"list": 1}

    def test_record_multiple(self, store: TelemetryStore) -> None:
        store.record("command", "list")
        store.record("command", "list")
        store.record("command", "health")
        counts = store.get_command_counts()
        assert counts["list"] == 2
        assert counts["health"] == 1

    def test_record_pro_gate(self, store: TelemetryStore) -> None:
        store.record("pro_gate", "export_yaml")
        assert store.get_pro_gate_counts() == {"export_yaml": 1}

    def test_total_events(self, store: TelemetryStore) -> None:
        assert store.get_total_events() == 0
        store.record("command", "list")
        store.record("pro_gate", "export_yaml")
        assert store.get_total_events() == 2

    def test_first_last_event_time(self, store: TelemetryStore) -> None:
        assert store.get_first_event_time() is None
        assert store.get_last_event_time() is None
        store.record("command", "list")
        assert store.get_first_event_time() is not None
        assert store.get_last_event_time() is not None

    def test_daily_activity(self, store: TelemetryStore) -> None:
        store.record("command", "list")
        store.record("command", "health")
        activity = store.get_daily_activity()
        assert len(activity) >= 1
        assert activity[0][1] == 2

    def test_reset(self, store: TelemetryStore) -> None:
        store.record("command", "list")
        store.reset()
        assert store.get_total_events() == 0

    def test_empty_counts(self, store: TelemetryStore) -> None:
        assert store.get_command_counts() == {}
        assert store.get_pro_gate_counts() == {}

    def test_close(self, telemetry_db: Path) -> None:
        store = TelemetryStore(telemetry_db)
        store.close()
        with pytest.raises(McpManagerError):
            store.record("command", "test")


class TestTrackHelpers:
    def test_track_command_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_MANAGER_TELEMETRY", raising=False)
        reset_telemetry_store()
        track_command("list")

    def test_track_command_enabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_MANAGER_TELEMETRY", "1")
        monkeypatch.setattr(
            "mcp_manager.telemetry._telemetry_dir",
            lambda: tmp_path,
        )
        reset_telemetry_store()
        track_command("list")
        store = TelemetryStore(tmp_path / "telemetry.db")
        try:
            assert store.get_command_counts() == {"list": 1}
        finally:
            store.close()
            reset_telemetry_store()

    def test_track_pro_gate_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_MANAGER_TELEMETRY", raising=False)
        reset_telemetry_store()
        track_pro_gate("export_yaml")

    def test_track_pro_gate_enabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_MANAGER_TELEMETRY", "1")
        monkeypatch.setattr(
            "mcp_manager.telemetry._telemetry_dir",
            lambda: tmp_path,
        )
        reset_telemetry_store()
        track_pro_gate("export_yaml")
        store = TelemetryStore(tmp_path / "telemetry.db")
        try:
            assert store.get_pro_gate_counts() == {"export_yaml": 1}
        finally:
            store.close()
            reset_telemetry_store()

    def test_reset_when_none(self) -> None:
        reset_telemetry_store()


class TestStoreCreation:
    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        db_path = tmp_path / "sub" / "dir" / "telemetry.db"
        store = TelemetryStore(db_path)
        store.record("command", "test")
        assert store.get_total_events() == 1
        store.close()

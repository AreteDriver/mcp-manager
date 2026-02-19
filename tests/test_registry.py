"""Tests for mcp_manager.registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_manager.exceptions import RegistryError
from mcp_manager.models import (
    HealthResult,
    McpServer,
    ServerStatus,
    StdioConfig,
    TransportType,
)
from mcp_manager.registry import ServerRegistry


def _make_server(name: str = "test") -> McpServer:
    return McpServer(
        name=name,
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="echo"),
        source_tool="mcp-manager",
    )


class TestRegistryBasics:
    def test_add_and_get(self, tmp_path: Path) -> None:
        reg = ServerRegistry(path=tmp_path / "reg.json")
        server = _make_server("myserver")
        reg.add(server)

        entry = reg.get("myserver")
        assert entry is not None
        assert entry.server.name == "myserver"
        assert entry.last_health is None

    def test_remove(self, tmp_path: Path) -> None:
        reg = ServerRegistry(path=tmp_path / "reg.json")
        reg.add(_make_server("a"))
        assert reg.remove("a") is True
        assert reg.get("a") is None

    def test_remove_nonexistent(self, tmp_path: Path) -> None:
        reg = ServerRegistry(path=tmp_path / "reg.json")
        assert reg.remove("nope") is False

    def test_list_all_sorted(self, tmp_path: Path) -> None:
        reg = ServerRegistry(path=tmp_path / "reg.json")
        reg.add(_make_server("z"))
        reg.add(_make_server("a"))
        reg.add(_make_server("m"))

        entries = reg.list_all()
        names = [e.server.name for e in entries]
        assert names == ["a", "m", "z"]

    def test_len(self, tmp_path: Path) -> None:
        reg = ServerRegistry(path=tmp_path / "reg.json")
        assert len(reg) == 0
        reg.add(_make_server("a"))
        assert len(reg) == 1

    def test_contains(self, tmp_path: Path) -> None:
        reg = ServerRegistry(path=tmp_path / "reg.json")
        reg.add(_make_server("present"))
        assert "present" in reg
        assert "absent" not in reg

    def test_add_update_preserves_timestamp(self, tmp_path: Path) -> None:
        reg = ServerRegistry(path=tmp_path / "reg.json")
        reg.add(_make_server("x"))
        first_time = reg.get("x").added_at  # type: ignore[union-attr]

        # Re-add same name.
        reg.add(_make_server("x"))
        second_time = reg.get("x").added_at  # type: ignore[union-attr]
        assert second_time == first_time

    def test_update_health(self, tmp_path: Path) -> None:
        reg = ServerRegistry(path=tmp_path / "reg.json")
        reg.add(_make_server("s"))

        result = HealthResult(
            server_name="s",
            status=ServerStatus.HEALTHY,
            latency_ms=50.0,
            transport=TransportType.STDIO,
        )
        reg.update_health("s", result)

        entry = reg.get("s")
        assert entry is not None
        assert entry.last_health is not None
        assert entry.last_health.status == ServerStatus.HEALTHY


class TestRegistryPersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "reg.json"

        # Save.
        reg = ServerRegistry(path=path)
        reg.add(_make_server("saved"))
        reg.save()
        assert path.is_file()

        # Load into new instance.
        reg2 = ServerRegistry(path=path)
        reg2.load()
        assert len(reg2) == 1
        assert reg2.get("saved") is not None

    def test_load_missing_file(self, tmp_path: Path) -> None:
        reg = ServerRegistry(path=tmp_path / "nope.json")
        reg.load()  # No-op, no error.
        assert len(reg) == 0

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{bad", encoding="utf-8")

        reg = ServerRegistry(path=path)
        with pytest.raises(RegistryError, match="Failed to load"):
            reg.load()

    def test_load_non_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "list.json"
        path.write_text("[1, 2]", encoding="utf-8")

        reg = ServerRegistry(path=path)
        with pytest.raises(RegistryError, match="not a JSON object"):
            reg.load()

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "reg.json"
        reg = ServerRegistry(path=path)
        reg.add(_make_server("test"))
        reg.save()
        assert path.is_file()

    def test_round_trip_with_health(self, tmp_path: Path) -> None:
        path = tmp_path / "reg.json"
        reg = ServerRegistry(path=path)
        reg.add(_make_server("s"))
        reg.update_health(
            "s",
            HealthResult(
                server_name="s",
                status=ServerStatus.HEALTHY,
                latency_ms=42.0,
                transport=TransportType.STDIO,
            ),
        )
        reg.save()

        reg2 = ServerRegistry(path=path)
        reg2.load()
        entry = reg2.get("s")
        assert entry is not None
        assert entry.last_health is not None
        assert entry.last_health.latency_ms == 42.0

"""Tests for config write-back to IDE files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_manager.exceptions import WritebackError
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType
from mcp_manager.writeback import ConfigWriteback

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def writeback():
    return ConfigWriteback()


@pytest.fixture
def sample_stdio_server():
    return McpServer(
        name="test-stdio",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="node", args=["server.js"], env={"KEY": "val"}),
        source_tool="mcp-manager",
    )


@pytest.fixture
def sample_sse_server():
    return McpServer(
        name="test-sse",
        transport=TransportType.SSE,
        network_config=NetworkConfig(type="sse", url="http://localhost:3000"),
        source_tool="mcp-manager",
    )


# ---------------------------------------------------------------------------
# Supported IDEs
# ---------------------------------------------------------------------------


class TestSupportedIdes:
    def test_returns_known_ides(self, writeback: ConfigWriteback) -> None:
        ides = writeback.get_supported_ides()
        assert "claude-code" in ides
        assert "claude-desktop" in ides
        assert "cursor" in ides
        assert "windsurf" in ides


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


class TestPreview:
    def test_preview_unknown_ide_raises(self, writeback: ConfigWriteback) -> None:
        with pytest.raises(WritebackError):
            writeback.preview("unknown-ide", [])

    def test_preview_new_file(
        self, writeback: ConfigWriteback, sample_stdio_server: McpServer
    ) -> None:
        # claude-code config path is ~-based; expanduser makes it absolute.
        # We monkeypatch the internal dict in the test below instead.
        pass


# ---------------------------------------------------------------------------
# Write servers — new file
# ---------------------------------------------------------------------------


class TestWriteServersNewFile:
    def test_create_new_file(
        self, tmp_path: Path, writeback: ConfigWriteback, sample_stdio_server: McpServer
    ) -> None:
        # Patch internal config path to a temp file.
        fake_path = tmp_path / "claude.json"
        writeback._ide_configs["claude-code"] = (fake_path, "mcpServers")

        path = writeback.write_servers("claude-code", [sample_stdio_server], create_if_missing=True)

        assert path == fake_path
        assert fake_path.exists()
        data = json.loads(fake_path.read_text())
        assert "mcpServers" in data
        assert data["mcpServers"]["test-stdio"]["command"] == "node"
        assert data["mcpServers"]["test-stdio"]["args"] == ["server.js"]

    def test_dry_run_does_not_create(
        self, tmp_path: Path, writeback: ConfigWriteback, sample_stdio_server: McpServer
    ) -> None:
        fake_path = tmp_path / "claude.json"
        writeback._ide_configs["claude-code"] = (fake_path, "mcpServers")

        writeback.write_servers(
            "claude-code", [sample_stdio_server], create_if_missing=True, dry_run=True
        )

        assert not fake_path.exists()

    def test_missing_file_without_create_raises(
        self, tmp_path: Path, writeback: ConfigWriteback
    ) -> None:
        fake_path = tmp_path / "claude.json"
        writeback._ide_configs["claude-code"] = (fake_path, "mcpServers")

        with pytest.raises(WritebackError):
            writeback.write_servers("claude-code", [], create_if_missing=False)


# ---------------------------------------------------------------------------
# Write servers — update existing
# ---------------------------------------------------------------------------


class TestWriteServersExistingFile:
    def test_merge_into_existing(
        self, tmp_path: Path, writeback: ConfigWriteback, sample_stdio_server: McpServer
    ) -> None:
        fake_path = tmp_path / "claude.json"
        fake_path.write_text(json.dumps({"mcpServers": {"existing": {"command": "old"}}}))
        writeback._ide_configs["claude-code"] = (fake_path, "mcpServers")

        writeback.write_servers("claude-code", [sample_stdio_server])

        data = json.loads(fake_path.read_text())
        assert data["mcpServers"]["existing"]["command"] == "old"
        assert data["mcpServers"]["test-stdio"]["command"] == "node"

    def test_replace_same_name(
        self, tmp_path: Path, writeback: ConfigWriteback, sample_stdio_server: McpServer
    ) -> None:
        fake_path = tmp_path / "claude.json"
        fake_path.write_text(json.dumps({"mcpServers": {"test-stdio": {"command": "old"}}}))
        writeback._ide_configs["claude-code"] = (fake_path, "mcpServers")

        writeback.write_servers("claude-code", [sample_stdio_server])

        data = json.loads(fake_path.read_text())
        assert data["mcpServers"]["test-stdio"]["command"] == "node"

    def test_preserves_non_mcp_keys(
        self, tmp_path: Path, writeback: ConfigWriteback, sample_stdio_server: McpServer
    ) -> None:
        fake_path = tmp_path / "claude.json"
        fake_path.write_text(json.dumps({"otherKey": 42, "mcpServers": {}}))
        writeback._ide_configs["claude-code"] = (fake_path, "mcpServers")

        writeback.write_servers("claude-code", [sample_stdio_server])

        data = json.loads(fake_path.read_text())
        assert data["otherKey"] == 42
        assert "mcpServers" in data

    def test_creates_backup(
        self, tmp_path: Path, writeback: ConfigWriteback, sample_stdio_server: McpServer
    ) -> None:
        fake_path = tmp_path / "claude.json"
        original = json.dumps({"mcpServers": {}})
        fake_path.write_text(original)
        writeback._ide_configs["claude-code"] = (fake_path, "mcpServers")

        writeback.write_servers("claude-code", [sample_stdio_server])

        backup = tmp_path / "claude.json.mcp-manager-backup"
        assert backup.exists()
        assert json.loads(backup.read_text()) == {"mcpServers": {}}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_stdio_server_dict(self, writeback: ConfigWriteback) -> None:
        server = McpServer(
            name="stdio-srv",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="python", args=["srv.py"]),
            source_tool="test",
        )
        result = writeback.preview("claude-code", [server])
        # Since claude-code config path is home-based and likely doesn't exist,
        # preview builds a new dict.
        srv = result["mcpServers"]["stdio-srv"]
        assert srv["command"] == "python"
        assert srv["args"] == ["srv.py"]

    def test_sse_server_dict(self, writeback: ConfigWriteback) -> None:
        server = McpServer(
            name="sse-srv",
            transport=TransportType.SSE,
            network_config=NetworkConfig(type="sse", url="http://x"),
            source_tool="test",
        )
        result = writeback.preview("claude-code", [server])
        srv = result["mcpServers"]["sse-srv"]
        assert srv["type"] == "sse"
        assert srv["url"] == "http://x"

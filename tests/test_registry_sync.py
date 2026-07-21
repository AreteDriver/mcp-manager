"""Tests for mcp_manager.registry_sync."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from mcp_manager.exceptions import WritebackError
from mcp_manager.models import McpServer, NetworkConfig, ServerStatus, StdioConfig, TransportType
from mcp_manager.registry_sync import (
    RegistryDiff,
    compute_diff,
    fetch_remote_servers,
    merge_servers,
    verify_servers,
    write_project_servers,
)


def _make_stdio(name: str = "local") -> McpServer:
    return McpServer(
        name=name,
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["-y", "pkg"]),
    )


def _make_http(name: str = "remote") -> McpServer:
    return McpServer(
        name=name,
        transport=TransportType.HTTP,
        network_config=NetworkConfig(type="http", url="https://example.com/mcp"),
    )


class TestFetchRemoteServers:
    """Tests for fetching remote server definitions."""

    def test_fetch_yaml_success(self, tmp_path: Path) -> None:
        registry = tmp_path / "registry.yaml"
        registry.write_text(
            yaml.dump({
                "servers": {
                    "fs": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                },
                    "slack": {"type": "sse", "url": "https://slack.example.com/sse"},
                }
            })
        )

        # Use file:// URL to avoid real HTTP
        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = registry.read_text()
            mock_get.return_value.raise_for_status = lambda: None

            servers = fetch_remote_servers("file://" + str(registry))

        assert len(servers) == 2
        names = {s.name for s in servers}
        assert names == {"fs", "slack"}

    def test_fetch_json_success(self, tmp_path: Path) -> None:
        registry = tmp_path / "registry.json"
        registry.write_text(
            json.dumps({
                "servers": {
                    "github": {
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-github"],
                    },
                }
            })
        )

        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = registry.read_text()
            mock_get.return_value.raise_for_status = lambda: None

            servers = fetch_remote_servers("https://example.com/registry.json")

        assert len(servers) == 1
        assert servers[0].name == "github"

    def test_fetch_http_error(self) -> None:
        from httpx import HTTPError

        with (
            patch("mcp_manager.registry_sync.httpx.get", side_effect=HTTPError("timeout")),
            pytest.raises(WritebackError, match="Failed to fetch"),
        ):
            fetch_remote_servers("https://example.com/registry.yaml")

    def test_fetch_with_headers(self, tmp_path: Path) -> None:
        """Custom headers are forwarded to httpx.get."""
        registry = tmp_path / "registry.yaml"
        registry.write_text(yaml.dump({"servers": {"srv": {"command": "npx"}}}))

        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = registry.read_text()
            mock_get.return_value.raise_for_status = lambda: None

            fetch_remote_servers(
                "https://example.com/registry.yaml",
                headers={"Authorization": "Bearer tok", "X-Custom": "val"},
            )

        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer tok"
        assert kwargs["headers"]["X-Custom"] == "val"

    def test_fetch_invalid_yaml(self) -> None:
        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = ": : :\n  - bad"
            mock_get.return_value.raise_for_status = lambda: None

            with pytest.raises(WritebackError, match="Failed to parse"):
                fetch_remote_servers("https://example.com/registry.yaml")

    def test_fetch_non_dict_root(self) -> None:
        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = "[1, 2, 3]"
            mock_get.return_value.raise_for_status = lambda: None

            with pytest.raises(WritebackError, match="must contain a mapping"):
                fetch_remote_servers("https://example.com/registry.yaml")

    def test_fetch_no_servers_key(self) -> None:
        """Registry with no 'servers' key but root is dict — returns empty list."""
        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = "project: test"
            mock_get.return_value.raise_for_status = lambda: None

            servers = fetch_remote_servers("https://example.com/registry.yaml")
            assert servers == []

    def test_fetch_servers_not_a_dict(self) -> None:
        """Registry where 'servers' is not a dict raises error."""
        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = "servers: [1, 2, 3]"
            mock_get.return_value.raise_for_status = lambda: None

            with pytest.raises(WritebackError, match="No servers found"):
                fetch_remote_servers("https://example.com/registry.yaml")

    def test_fetch_skips_non_dict_entries(self, tmp_path: Path) -> None:
        registry = tmp_path / "registry.yaml"
        registry.write_text(
            yaml.dump({
                "servers": {
                    "good": {"command": "npx"},
                    "bad": "not a dict",
                }
            })
        )

        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = registry.read_text()
            mock_get.return_value.raise_for_status = lambda: None

            servers = fetch_remote_servers("https://example.com/registry.yaml")

        assert len(servers) == 1
        assert servers[0].name == "good"


class TestComputeDiff:
    """Tests for diff computation."""

    def test_empty_both_sides(self) -> None:
        diff = compute_diff([], [])
        assert diff == RegistryDiff(added=[], updated=[], removed=[])

    def test_added_servers(self) -> None:
        local = [_make_stdio("a")]
        remote = [_make_stdio("a"), _make_http("b")]
        diff = compute_diff(local, remote)
        assert len(diff.added) == 1
        assert diff.added[0].name == "b"
        assert diff.removed == []
        assert diff.updated == []

    def test_removed_servers(self) -> None:
        local = [_make_stdio("a"), _make_http("b")]
        remote = [_make_stdio("a")]
        diff = compute_diff(local, remote)
        assert len(diff.removed) == 1
        assert diff.removed[0].name == "b"
        assert diff.added == []
        assert diff.updated == []

    def test_updated_servers(self) -> None:
        local = [_make_stdio("a")]
        remote = [McpServer(
            name="a",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="node", args=["server.js"]),
        )]
        diff = compute_diff(local, remote)
        assert len(diff.updated) == 1
        assert diff.updated[0][0].name == "a"
        assert diff.updated[0][1].name == "a"
        assert diff.added == []
        assert diff.removed == []

    def test_no_changes(self) -> None:
        local = [_make_stdio("a")]
        remote = [_make_stdio("a")]
        diff = compute_diff(local, remote)
        assert diff == RegistryDiff(added=[], updated=[], removed=[])


class TestMergeServers:
    """Tests for merge strategies."""

    def test_union_adds_new(self) -> None:
        local = [_make_stdio("a")]
        remote = [_make_stdio("a"), _make_http("b")]
        merged = merge_servers(local, remote, "union")
        assert len(merged) == 2
        names = {s.name for s in merged}
        assert names == {"a", "b"}

    def test_union_remote_wins_on_conflict(self) -> None:
        local = [_make_stdio("a")]
        remote = [McpServer(
            name="a",
            transport=TransportType.HTTP,
            network_config=NetworkConfig(type="http", url="https://remote.example.com"),
        )]
        merged = merge_servers(local, remote, "union")
        assert len(merged) == 1
        assert merged[0].transport == TransportType.HTTP

    def test_replace_replaces_all(self) -> None:
        local = [_make_stdio("a")]
        remote = [_make_http("b")]
        merged = merge_servers(local, remote, "replace")
        assert len(merged) == 1
        assert merged[0].name == "b"

    def test_union_preserves_local_only(self) -> None:
        local = [_make_stdio("a"), _make_http("b")]
        remote = [_make_stdio("a")]
        merged = merge_servers(local, remote, "union")
        assert len(merged) == 2
        names = {s.name for s in merged}
        assert names == {"a", "b"}


class TestVerifyServers:
    """Tests for remote server verification."""

    def test_verify_unreachable_stdio(self) -> None:
        servers = [
            McpServer(
                name="missing",
                transport=TransportType.STDIO,
                stdio_config=StdioConfig(command="/does/not/exist"),
            )
        ]
        results = verify_servers(servers)
        assert len(results) == 1
        assert results[0][1] == ServerStatus.UNREACHABLE


class TestWriteProjectServers:
    """Tests for writing merged servers back to disk."""

    def test_writes_servers_block(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp-manager.yml"
        config.write_text(
            "project: test\nextends: base.yml\nservers:\n  local:\n    command: node\n"
        )

        servers = [
            _make_stdio("a"),
            _make_http("b"),
        ]
        write_project_servers(config, servers)

        text = config.read_text()
        data = yaml.safe_load(text)
        assert data["project"] == "test"
        assert data["extends"] == "base.yml"
        assert "a" in data["servers"]
        assert "b" in data["servers"]

    def test_creates_backup(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp-manager.yml"
        config.write_text("project: test\nservers: {}\n")

        write_project_servers(config, [_make_stdio("a")])

        backup = tmp_path / ".mcp-manager.yml.mcp-manager-backup"
        assert backup.exists()

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(WritebackError, match="Project config not found"):
            write_project_servers(tmp_path / "nope.yml", [])

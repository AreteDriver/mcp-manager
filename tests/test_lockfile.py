"""Tests for the lockfile module."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import yaml

from mcp_manager.lockfile import (
    Lockfile,
    LockfileEntry,
    check_lockfile,
    generate_lockfile,
    read_lockfile,
    resolve_server,
    write_lockfile,
)
from mcp_manager.models import McpServer, StdioConfig, TransportType

# ---------------------------------------------------------------------------
# resolve_server / npm extraction
# ---------------------------------------------------------------------------


def test_resolve_server_npm_explicit_version() -> None:
    """When command already pins a version, use it."""
    server = McpServer(
        name="test",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["some-pkg@1.2.3"]),
    )
    entry = resolve_server(server)
    assert entry.resolved_version == "1.2.3"
    assert entry.error is None


def test_resolve_server_npm_no_version() -> None:
    """Query npm registry when no version is pinned."""
    server = McpServer(
        name="test",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["some-pkg"]),
    )
    with patch("mcp_manager.lockfile.httpx.get") as mock_get:
        mock_get.return_value.json.return_value = {"dist-tags": {"latest": "4.5.6"}}
        mock_get.return_value.raise_for_status.return_value = None

        entry = resolve_server(server)

    assert entry.resolved_version == "4.5.6"
    assert entry.error is None


def test_resolve_server_npm_scoped_package() -> None:
    """Scoped npm packages resolve correctly."""
    server = McpServer(
        name="test",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["@scope/pkg@2.0.0"]),
    )
    entry = resolve_server(server)
    assert entry.resolved_version == "2.0.0"
    assert entry.error is None


def test_resolve_server_npm_registry_failure() -> None:
    """Record error when npm registry is unreachable."""
    server = McpServer(
        name="test",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["some-pkg"]),
    )
    with patch("mcp_manager.lockfile.httpx.get", side_effect=httpx.ConnectError("network down")):
        entry = resolve_server(server)
    assert entry.resolved_version is None
    assert entry.error is not None
    assert "network down" in entry.error


def test_resolve_server_not_npx() -> None:
    """Non-npx commands return empty entry."""
    server = McpServer(
        name="test",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="python", args=["-m", "server"]),
    )
    entry = resolve_server(server)
    assert entry.resolved_version is None
    assert entry.error is not None
    assert "Non-npm" in entry.error


def test_resolve_server_no_args() -> None:
    """Server with no args returns empty entry."""
    server = McpServer(
        name="test",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="node", args=[]),
    )
    entry = resolve_server(server)
    assert entry.resolved_version is None
    assert entry.error is not None
    assert "No npm package" in entry.error


# ---------------------------------------------------------------------------
# generate_lockfile
# ---------------------------------------------------------------------------


def test_generate_lockfile_creates_expected_structure() -> None:
    """generate_lockfile produces a Lockfile with entries per server."""
    servers = [
        McpServer(
            name="a",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="npx", args=["pkg-a@1.0.0"]),
        ),
        McpServer(
            name="b",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="python", args=["-m", "b"]),
        ),
    ]
    lockfile = generate_lockfile(servers)
    assert lockfile.version == "1"
    assert "a" in lockfile.servers
    assert "b" in lockfile.servers
    assert lockfile.servers["a"].resolved_version == "1.0.0"
    assert lockfile.servers["b"].resolved_version is None


# ---------------------------------------------------------------------------
# check_lockfile
# ---------------------------------------------------------------------------


def test_check_lockfile_all_match() -> None:
    """No errors when lockfile matches current config."""
    servers = [
        McpServer(
            name="a",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="npx", args=["pkg-a@1.0.0"]),
        ),
    ]
    lockfile = Lockfile(
        version="1",
        resolved_at=datetime.now(UTC).isoformat(),
        servers={
            "a": LockfileEntry(resolved_version="1.0.0"),
        },
    )
    errors = check_lockfile(servers, lockfile)
    assert errors == []


def test_check_lockfile_version_mismatch() -> None:
    """Errors when resolved version differs."""
    servers = [
        McpServer(
            name="a",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="npx", args=["pkg-a@2.0.0"]),
        ),
    ]
    lockfile = Lockfile(
        version="1",
        resolved_at=datetime.now(UTC).isoformat(),
        servers={
            "a": LockfileEntry(resolved_version="1.0.0"),
        },
    )
    errors = check_lockfile(servers, lockfile)
    assert len(errors) == 1
    assert "a" in errors[0]
    assert "1.0.0" in errors[0]
    assert "2.0.0" in errors[0]


def test_check_lockfile_missing_server() -> None:
    """Errors when server is missing from lockfile."""
    servers = [
        McpServer(
            name="a",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="npx", args=["pkg-a@1.0.0"]),
        ),
    ]
    lockfile = Lockfile(
        version="1",
        resolved_at=datetime.now(UTC).isoformat(),
        servers={},
    )
    errors = check_lockfile(servers, lockfile)
    assert len(errors) == 1
    assert "a" in errors[0]


def test_check_lockfile_extra_server_reported() -> None:
    """Extra servers in lockfile are reported as stale."""
    servers = [
        McpServer(
            name="a",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="npx", args=["pkg-a@1.0.0"]),
        ),
    ]
    lockfile = Lockfile(
        version="1",
        resolved_at=datetime.now(UTC).isoformat(),
        servers={
            "a": LockfileEntry(resolved_version="1.0.0"),
            "b": LockfileEntry(resolved_version="2.0.0"),
        },
    )
    errors = check_lockfile(servers, lockfile)
    assert len(errors) == 1
    assert "Stale servers" in errors[0]
    assert "b" in errors[0]


def test_check_lockfile_expected_error_not_failure() -> None:
    """Non-npm servers with matching errors in lockfile are not failures."""
    servers = [
        McpServer(
            name="docs",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="python3", args=["-m", "http.server"]),
        ),
    ]
    lockfile = Lockfile(
        version="1",
        resolved_at=datetime.now(UTC).isoformat(),
        servers={
            "docs": LockfileEntry(error="Non-npm command: version not resolvable"),
        },
    )
    errors = check_lockfile(servers, lockfile)
    assert errors == []


def test_check_lockfile_different_error_reported() -> None:
    """Errors that differ between lockfile and current resolution are reported."""
    servers = [
        McpServer(
            name="a",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="npx", args=["some-pkg"]),
        ),
    ]
    lockfile = Lockfile(
        version="1",
        resolved_at=datetime.now(UTC).isoformat(),
        servers={
            "a": LockfileEntry(error="old error"),
        },
    )
    errors = check_lockfile(servers, lockfile)
    assert len(errors) == 1
    assert "old error" in errors[0]


# ---------------------------------------------------------------------------
# write / read lockfile
# ---------------------------------------------------------------------------


def test_write_and_read_lockfile_roundtrip(tmp_path: Path) -> None:
    """Serializing and deserializing yields equivalent data."""
    lockfile = Lockfile(
        version="1",
        resolved_at=datetime.now(UTC).isoformat(),
        servers={
            "a": LockfileEntry(resolved_version="1.0.0"),
            "b": LockfileEntry(resolved_version=None, error="network failure"),
        },
    )
    path = tmp_path / ".mcp-manager.lock"
    write_lockfile(path, lockfile)
    assert path.exists()

    restored = read_lockfile(path)
    assert restored.version == "1"
    assert restored.servers["a"].resolved_version == "1.0.0"
    assert restored.servers["b"].error == "network failure"


def test_read_lockfile_not_found(tmp_path: Path) -> None:
    """Raises McpManagerError when file is missing."""
    from mcp_manager.exceptions import McpManagerError

    with pytest.raises(McpManagerError):
        read_lockfile(tmp_path / ".mcp-manager.lock")


def test_read_lockfile_invalid_yaml(tmp_path: Path) -> None:
    """Raises McpManagerError when YAML is malformed."""
    from mcp_manager.exceptions import McpManagerError

    path = tmp_path / ".mcp-manager.lock"
    path.write_text("not: valid: yaml: [")
    with pytest.raises(McpManagerError):
        read_lockfile(path)


def test_read_lockfile_missing_version_defaults(tmp_path: Path) -> None:
    """Missing version field defaults to '1'."""
    path = tmp_path / ".mcp-manager.lock"
    path.write_text(yaml.dump({"servers": {}}))
    restored = read_lockfile(path)
    assert restored.version == "1"
    assert restored.servers == {}

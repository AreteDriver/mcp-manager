"""Tests for the server uninstall command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mcp_manager.cli import app
from mcp_manager.models import (
    HealthResult,
    ServerStatus,
    TransportType,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_warn_if_healthy(request: Any) -> Any:
    """Prevent real health checks from hanging in most tests."""
    if "force_bypasses_warning" in request.node.name:
        yield
    else:
        with patch("mcp_manager.commands.uninstall._warn_if_healthy"):
            yield


@pytest.fixture
def ide_configs(tmp_path: Path) -> dict[str, Path]:
    """Create temp IDE config files and patch the global paths."""
    cursor_path = tmp_path / "cursor_mcp.json"
    windsurf_path = tmp_path / "windsurf_mcp.json"
    claude_path = tmp_path / "claude.json"

    paths: list[tuple[str, str, str | None]] = [
        ("cursor", str(cursor_path), "mcpServers"),
        ("windsurf", str(windsurf_path), "mcpServers"),
        ("claude-code", str(claude_path), "mcpServers"),
    ]

    with (
        patch("mcp_manager.config.IDE_CONFIG_PATHS", paths),
        patch("mcp_manager.discovery.IDE_CONFIG_PATHS", paths),
        patch("mcp_manager.writeback.IDE_CONFIG_PATHS", paths),
    ):
        yield {"cursor": cursor_path, "windsurf": windsurf_path, "claude-code": claude_path}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_uninstall_not_found() -> None:
    with patch("mcp_manager.discovery.ConfigDiscovery.discover_all", return_value=[]):
        result = runner.invoke(app, ["server", "uninstall", "missing"])
    assert result.exit_code == 1
    assert "not found in any client config" in result.output


def test_uninstall_dry_run(ide_configs: dict[str, Path]) -> None:
    _write_config(
        ide_configs["cursor"],
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )

    result = runner.invoke(app, ["server", "uninstall", "my-srv", "--dry-run"])
    assert result.exit_code == 0
    assert "Would uninstall" in result.output
    # File unchanged.
    data = json.loads(ide_configs["cursor"].read_text(encoding="utf-8"))
    assert "my-srv" in data["mcpServers"]


def test_uninstall_from_all_ides(ide_configs: dict[str, Path]) -> None:
    _write_config(
        ide_configs["cursor"],
        {"mcpServers": {"my-srv": {"command": "npx"}, "other": {"command": "node"}}},
    )
    _write_config(
        ide_configs["windsurf"],
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )

    result = runner.invoke(app, ["server", "uninstall", "my-srv"])
    assert result.exit_code == 0
    assert "Uninstalled" in result.output

    cursor_data = json.loads(ide_configs["cursor"].read_text(encoding="utf-8"))
    assert "my-srv" not in cursor_data["mcpServers"]
    assert "other" in cursor_data["mcpServers"]

    windsurf_data = json.loads(ide_configs["windsurf"].read_text(encoding="utf-8"))
    assert "my-srv" not in windsurf_data["mcpServers"]


def test_uninstall_single_ide(ide_configs: dict[str, Path]) -> None:
    _write_config(
        ide_configs["cursor"],
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )
    _write_config(
        ide_configs["windsurf"],
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )

    result = runner.invoke(app, ["server", "uninstall", "my-srv", "--ide", "cursor"])
    assert result.exit_code == 0

    cursor_data = json.loads(ide_configs["cursor"].read_text(encoding="utf-8"))
    assert "my-srv" not in cursor_data["mcpServers"]

    windsurf_data = json.loads(ide_configs["windsurf"].read_text(encoding="utf-8"))
    assert "my-srv" in windsurf_data["mcpServers"]


def test_uninstall_force_bypasses_warning(ide_configs: dict[str, Path]) -> None:
    _write_config(
        ide_configs["cursor"],
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )

    healthy = HealthResult(
        server_name="my-srv",
        status=ServerStatus.HEALTHY,
        latency_ms=10.0,
        transport=TransportType.STDIO,
    )

    from unittest.mock import AsyncMock

    with patch(
        "mcp_manager.commands.uninstall.HealthChecker.check",
        new=AsyncMock(return_value=healthy),
    ):
        # Without --force, should warn.
        result = runner.invoke(app, ["server", "uninstall", "my-srv", "--ide", "cursor"])
    assert result.exit_code == 0
    assert "Warning" in result.output
    assert "still healthy" in result.output

    # With --force, should not show the warning.
    _write_config(
        ide_configs["cursor"],
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )
    with patch(
        "mcp_manager.commands.uninstall.HealthChecker.check",
        new=AsyncMock(return_value=healthy),
    ):
        result_force = runner.invoke(
            app, ["server", "uninstall", "my-srv", "--ide", "cursor", "--force"]
        )
    assert result_force.exit_code == 0
    # The warning should not appear with --force.
    assert "Warning" not in result_force.output


def test_uninstall_not_in_targeted_ide(ide_configs: dict[str, Path]) -> None:
    """Server is in windsurf but we target cursor — should skip cursor."""
    _write_config(
        ide_configs["cursor"],
        {"mcpServers": {"other-srv": {"command": "node"}}},
    )
    _write_config(
        ide_configs["windsurf"],
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )

    result = runner.invoke(app, ["server", "uninstall", "my-srv", "--ide", "cursor"])
    assert result.exit_code == 0
    assert "not found in this IDE config" in result.output or "skipped" in result.output


def test_uninstall_unknown_ide(ide_configs: dict[str, Path]) -> None:
    _write_config(
        ide_configs["cursor"],
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )

    result = runner.invoke(app, ["server", "uninstall", "my-srv", "--ide", "foobar"])
    assert result.exit_code == 1
    assert "Unknown IDE" in result.output


def test_uninstall_writeback_error(ide_configs: dict[str, Path]) -> None:
    _write_config(
        ide_configs["cursor"],
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )

    from mcp_manager.writeback import ConfigWriteback, WritebackError

    with patch.object(
        ConfigWriteback,
        "remove_servers",
        side_effect=WritebackError("Disk full"),
    ):
        result = runner.invoke(app, ["server", "uninstall", "my-srv", "--ide", "cursor"])

    assert result.exit_code == 0
    assert "Disk full" in result.output
    assert "skipped" in result.output.lower()


def test_uninstall_no_ide_configs() -> None:
    """When no IDE configs exist and the server isn't anywhere."""
    with patch("mcp_manager.discovery.ConfigDiscovery.discover_all", return_value=[]):
        result = runner.invoke(app, ["server", "uninstall", "my-srv"])
    assert result.exit_code == 1
    assert "not found in any client config" in result.output


def test_uninstall_all_flag(ide_configs: dict[str, Path]) -> None:
    _write_config(
        ide_configs["cursor"],
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )
    _write_config(
        ide_configs["windsurf"],
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )

    result = runner.invoke(app, ["server", "uninstall", "my-srv", "--all"])
    assert result.exit_code == 0

    for key in ("cursor", "windsurf"):
        data = json.loads(ide_configs[key].read_text(encoding="utf-8"))
        assert "my-srv" not in data["mcpServers"]


def test_uninstall_top_level_config(ide_configs: dict[str, Path]) -> None:
    """Uninstall from a config with no wrapper key (servers at top level)."""
    top_level_path = ide_configs["cursor"]
    _write_config(top_level_path, {"my-srv": {"command": "npx"}, "other": {"command": "node"}})

    # Re-patch with no wrapper key for cursor.
    paths: list[tuple[str, str, str | None]] = [
        ("cursor", str(top_level_path), None),
    ]
    with (
        patch("mcp_manager.config.IDE_CONFIG_PATHS", paths),
        patch("mcp_manager.discovery.IDE_CONFIG_PATHS", paths),
        patch("mcp_manager.writeback.IDE_CONFIG_PATHS", paths),
    ):
        result = runner.invoke(app, ["server", "uninstall", "my-srv", "--ide", "cursor"])

    assert result.exit_code == 0
    data = json.loads(top_level_path.read_text(encoding="utf-8"))
    assert "my-srv" not in data
    assert "other" in data


def test_uninstall_cursor_project_scope(tmp_path: Path) -> None:
    project_config = tmp_path / ".cursor/mcp.json"
    _write_config(
        project_config,
        {"mcpServers": {"my-srv": {"command": "npx"}}},
    )

    result = runner.invoke(
        app,
        [
            "server",
            "uninstall",
            "my-srv",
            "--ide",
            "cursor",
            "--scope",
            "project",
            "--project",
            str(tmp_path),
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert "my-srv" not in json.loads(project_config.read_text())["mcpServers"]

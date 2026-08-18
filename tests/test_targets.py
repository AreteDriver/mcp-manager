"""Tests for target inventory and doctor diagnostics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mcp_manager.adapters.codex import CodexTargetAdapter
from mcp_manager.adapters.json_target import JsonTargetAdapter
from mcp_manager.cli import app
from mcp_manager.commands.targets import _check_location

runner = CliRunner()


def test_targets_lists_codex() -> None:
    result = runner.invoke(app, ["targets", "--json"])

    assert result.exit_code == 0
    assert '"target": "codex"' in result.stdout
    assert '"format": "toml"' in result.stdout


def test_targets_renders_capability_table() -> None:
    result = runner.invoke(app, ["targets"])

    assert result.exit_code == 0
    assert "MCP Client Targets" in result.stdout
    assert "codex" in result.stdout


def test_doctor_reports_missing_absolute_command(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """\
[mcp_servers.broken]
command = "/definitely/missing/python"
args = ["/also/missing/server.py"]
"""
    )
    adapter = CodexTargetAdapter(user_path=config)

    result = _check_location(adapter, scope="user", project_dir=None)

    assert result["status"] == "error"
    messages = [issue["message"] for issue in result["issues"]]
    assert "command does not exist: /definitely/missing/python" in messages
    assert "argument path does not exist: /also/missing/server.py" in messages


def test_doctor_reports_invalid_server_shape(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    config.write_text('{"mcpServers": {"broken": {"command": "python", "args": "server.py"}}}')
    adapter = JsonTargetAdapter(
        name="cursor",
        user_path=config,
        wrapper_key="mcpServers",
    )

    result = _check_location(adapter, scope="user", project_dir=None)

    assert result["status"] == "error"
    assert "server field 'args' must be a list" in result["issues"][0]["message"]


def test_doctor_cli_fails_for_invalid_target_config(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    config.write_text('{"mcpServers": {"broken": {"type": "http"}}}')
    paths = [("cursor", str(config), "mcpServers")]

    with patch("mcp_manager.commands.targets.IDE_CONFIG_PATHS", paths):
        result = runner.invoke(app, ["doctor", "--target", "cursor", "--json"])

    assert result.exit_code == 1
    assert '"status": "error"' in result.stdout
    assert "has no url" in result.stdout


def test_doctor_checks_project_scoped_codex_config(tmp_path: Path) -> None:
    user_config = tmp_path / "missing-user.toml"
    project_config = tmp_path / ".codex/config.toml"
    project_config.parent.mkdir()
    project_config.write_text('[mcp_servers.local]\ncommand = "python"\n')
    paths = [("codex", str(user_config), "mcp_servers")]

    with patch("mcp_manager.commands.targets.IDE_CONFIG_PATHS", paths):
        result = runner.invoke(
            app,
            ["doctor", "--target", "codex", "--project", str(tmp_path), "--json"],
        )

    assert result.exit_code == 0
    assert '"scope": "project"' in result.stdout
    assert '"status": "ok"' in result.stdout


def test_doctor_rejects_unknown_target() -> None:
    result = runner.invoke(app, ["doctor", "--target", "unknown"])

    assert result.exit_code == 1


def test_doctor_does_not_print_secret_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PRIVATE_MCP_TOKEN", "super-secret-token-value")
    config = tmp_path / "config.toml"
    config.write_text(
        """\
[mcp_servers.remote]
url = "https://example.com/mcp"
bearer_token_env_var = "PRIVATE_MCP_TOKEN"
"""
    )
    adapter = CodexTargetAdapter(user_path=config)

    result = _check_location(adapter, scope="user", project_dir=None)

    assert result["status"] == "ok"
    assert "super-secret-token-value" not in str(result)

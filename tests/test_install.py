"""Tests for the server install command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mcp_manager.cli import app
from mcp_manager.models import (
    HealthResult,
    McpServer,
    NetworkConfig,
    RegistryEntry,
    ServerStatus,
    StdioConfig,
    TransportType,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_server() -> McpServer:
    return McpServer(
        name="my-server",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["-y", "my-server"]),
        source_tool="mcp-manager",
    )


@pytest.fixture
def registry_entry(sample_server: McpServer) -> RegistryEntry:
    return RegistryEntry(server=sample_server)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_fake_config(path: Path, servers: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(servers), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_install_registry_miss() -> None:
    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = None
        mock_reg.return_value = instance
        result = runner.invoke(app, ["server", "install", "missing"])
    assert result.exit_code == 1
    assert "not found in registry" in result.output


def test_install_unknown_ide() -> None:
    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        entry = MagicMock()
        entry.server = McpServer(
            name="srv",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="cmd"),
            source_tool="mcp-manager",
        )
        instance = MagicMock()
        instance.get.return_value = entry
        mock_reg.return_value = instance
        result = runner.invoke(app, ["server", "install", "srv", "--ide", "foobar"])
    assert result.exit_code == 1
    assert "Unknown IDE" in result.output


def test_install_dry_run_existing_config(tmp_path: Path, sample_server: McpServer) -> None:
    config_path = tmp_path / "cursor_mcp.json"
    _write_fake_config(config_path, {"existing": {"command": "old"}})

    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=sample_server)
        mock_reg.return_value = instance

        wb = ConfigWritebackTarget()
        wb._ide_configs = {"cursor": (config_path, None)}

        with patch(
            "mcp_manager.commands.install.ConfigWriteback",
            new=lambda: wb,
        ):
            result = runner.invoke(
                app, ["server", "install", "my-server", "--ide", "cursor", "--dry-run"]
            )

    assert result.exit_code == 0
    assert "Would install" in result.output
    # Ensure file unchanged.
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "existing" in data
    assert "my-server" not in data


class ConfigWritebackTarget:
    """Lightweight stand-in for ConfigWriteback in tests."""

    def __init__(self) -> None:
        self._ide_configs: dict[str, tuple[Path, str | None]] = {}

    def get_supported_ides(self) -> list[str]:
        return list(self._ide_configs.keys())

    def preview(self, ide: str, servers: list[Any]) -> dict[str, Any]:
        config_path, wrapper_key = self._ide_configs[ide]
        if not config_path.exists():
            return {s.name: self._server_to_dict(s) for s in servers}
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if wrapper_key is not None:
            existing = data.get(wrapper_key, {})
            if not isinstance(existing, dict):
                existing = {}
            merged = {**existing}
            for s in servers:
                merged[s.name] = self._server_to_dict(s)
            data[wrapper_key] = merged
        else:
            for s in servers:
                data[s.name] = self._server_to_dict(s)
        return data

    def write_servers(
        self,
        ide: str,
        servers: list[Any],
        *,
        create_if_missing: bool = False,
        dry_run: bool = False,
    ) -> Path:
        config_path, wrapper_key = self._ide_configs[ide]
        if dry_run:
            return config_path
        if not config_path.exists() and not create_if_missing:
            raise Exception("Config missing")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        if wrapper_key is not None:
            existing = data.get(wrapper_key, {})
            if not isinstance(existing, dict):
                existing = {}
            merged = {**existing}
            for s in servers:
                merged[s.name] = self._server_to_dict(s)
            data[wrapper_key] = merged
        else:
            for s in servers:
                data[s.name] = self._server_to_dict(s)
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return config_path

    @staticmethod
    def _server_to_dict(s: Any) -> dict[str, Any]:
        if s.transport.value == "stdio" and s.stdio_config:
            return {"command": s.stdio_config.command}
        if s.network_config:
            return {"type": s.network_config.type, "url": s.network_config.url}
        return {}


def test_install_writes_to_existing_config(tmp_path: Path, sample_server: McpServer) -> None:
    config_path = tmp_path / "cursor_mcp.json"
    _write_fake_config(config_path, {"existing": {"command": "old"}})

    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=sample_server)
        mock_reg.return_value = instance

        wb = ConfigWritebackTarget()
        wb._ide_configs = {"cursor": (config_path, None)}

        with patch("mcp_manager.commands.install.ConfigWriteback", new=lambda: wb):
            result = runner.invoke(app, ["server", "install", "my-server", "--ide", "cursor"])

    assert result.exit_code == 0
    assert "Installed" in result.output
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "my-server" in data
    assert data["my-server"]["command"] == "npx"


def test_install_auto_detect_skips_missing_configs(
    tmp_path: Path, sample_server: McpServer
) -> None:
    """Default mode: only install to IDEs whose configs exist."""
    cursor_path = tmp_path / "cursor_mcp.json"
    _write_fake_config(cursor_path, {})

    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=sample_server)
        mock_reg.return_value = instance

        # Patch discovery to simulate only cursor having a config.
        def fake_discover_tool(tool: str) -> list[McpServer]:
            if tool == "cursor":
                return [
                    McpServer(
                        name="x",
                        transport=TransportType.STDIO,
                        stdio_config=StdioConfig(command="x"),
                    )
                ]
            return []

        wb = ConfigWritebackTarget()
        wb._ide_configs = {
            "cursor": (cursor_path, None),
            "windsurf": (tmp_path / "missing.json", None),
        }

        with (
            patch("mcp_manager.commands.install.ConfigWriteback", new=lambda: wb),
            patch(
                "mcp_manager.discovery.ConfigDiscovery.discover_tool",
                side_effect=fake_discover_tool,
            ),
        ):
            result = runner.invoke(app, ["server", "install", "my-server"])

    assert result.exit_code == 0
    assert "cursor" in result.output
    # windsurf should be skipped because its config doesn't exist and we didn't pass --create.
    assert "windsurf" not in result.output or "skipped" in result.output


def test_install_all_with_create(tmp_path: Path, sample_server: McpServer) -> None:
    cursor_path = tmp_path / "cursor_mcp.json"
    windsurf_path = tmp_path / "windsurf_mcp.json"
    _write_fake_config(cursor_path, {})

    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=sample_server)
        mock_reg.return_value = instance

        wb = ConfigWritebackTarget()
        wb._ide_configs = {"cursor": (cursor_path, None), "windsurf": (windsurf_path, None)}

        with patch("mcp_manager.commands.install.ConfigWriteback", new=lambda: wb):
            result = runner.invoke(
                app, ["server", "install", "my-server", "--all", "--create"]
            )

    assert result.exit_code == 0
    assert "Installed" in result.output
    assert cursor_path.exists()
    assert windsurf_path.exists()
    data = json.loads(windsurf_path.read_text(encoding="utf-8"))
    assert "my-server" in data


def test_install_already_installed_no_force(tmp_path: Path, sample_server: McpServer) -> None:
    config_path = tmp_path / "cursor_mcp.json"
    _write_fake_config(config_path, {"my-server": {"command": "npx", "args": ["-y", "my-server"]}})

    existing_server = McpServer(
        name="my-server",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="npx", args=["-y", "my-server"]),
        source_tool="cursor",
    )

    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=sample_server)
        mock_reg.return_value = instance

        wb = ConfigWritebackTarget()
        wb._ide_configs = {"cursor": (config_path, None)}

        with patch("mcp_manager.commands.install.ConfigWriteback", new=lambda: wb), patch(
            "mcp_manager.commands.install.ConfigDiscovery.discover_tool",
            return_value=[existing_server],
        ):
            result = runner.invoke(app, ["server", "install", "my-server", "--ide", "cursor"])

    assert result.exit_code == 0
    assert "already installed" in result.output


def test_install_already_installed_with_force(tmp_path: Path, sample_server: McpServer) -> None:
    config_path = tmp_path / "cursor_mcp.json"
    _write_fake_config(config_path, {"my-server": {"command": "old"}})

    existing_server = McpServer(
        name="my-server",
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="old"),
        source_tool="cursor",
    )

    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=sample_server)
        mock_reg.return_value = instance

        wb = ConfigWritebackTarget()
        wb._ide_configs = {"cursor": (config_path, None)}

        with patch("mcp_manager.commands.install.ConfigWriteback", new=lambda: wb), patch(
            "mcp_manager.commands.install.ConfigDiscovery.discover_tool",
            return_value=[existing_server],
        ):
            result = runner.invoke(
                app, ["server", "install", "my-server", "--ide", "cursor", "--force"]
            )

    assert result.exit_code == 0
    assert "Installed" in result.output
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["my-server"]["command"] == "npx"


def test_install_verify_runs_health_check(tmp_path: Path, sample_server: McpServer) -> None:
    config_path = tmp_path / "cursor_mcp.json"
    _write_fake_config(config_path, {})

    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=sample_server)
        mock_reg.return_value = instance

        wb = ConfigWritebackTarget()
        wb._ide_configs = {"cursor": (config_path, None)}

        health_result = HealthResult(
            server_name="my-server",
            status=ServerStatus.HEALTHY,
            latency_ms=42.0,
            transport=TransportType.STDIO,
        )

        with patch("mcp_manager.commands.install.ConfigWriteback", new=lambda: wb), patch(
            "mcp_manager.commands.install.HealthChecker.check",
            return_value=health_result,
        ), patch(
            "mcp_manager.commands.install.asyncio.run",
            return_value=health_result,
        ):
            result = runner.invoke(
                app, ["server", "install", "my-server", "--ide", "cursor", "--verify"]
            )

    assert result.exit_code == 0
    assert "Verify:" in result.output
    assert "healthy" in result.output


def test_install_verify_skipped_when_no_success(tmp_path: Path, sample_server: McpServer) -> None:
    """If all installs are skipped, verify should be skipped too."""
    config_path = tmp_path / "cursor_mcp.json"
    # No config file, no --create => skipped.

    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=sample_server)
        mock_reg.return_value = instance

        wb = ConfigWritebackTarget()
        wb._ide_configs = {"cursor": (config_path, None)}

        with patch("mcp_manager.commands.install.ConfigWriteback", new=lambda: wb):
            result = runner.invoke(
                app, ["server", "install", "my-server", "--ide", "cursor", "--verify"]
            )

    assert result.exit_code == 0
    assert "Skipping verify" in result.output


def test_install_no_ide_detected(sample_server: McpServer) -> None:
    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=sample_server)
        mock_reg.return_value = instance

        wb = ConfigWritebackTarget()
        wb._ide_configs = {"cursor": (Path("/nonexistent"), None)}

        with (
            patch("mcp_manager.commands.install.ConfigWriteback", new=lambda: wb),
            patch("mcp_manager.discovery.ConfigDiscovery.discover_tool", return_value=[]),
        ):
            result = runner.invoke(app, ["server", "install", "my-server"])

    assert result.exit_code == 1
    assert "No IDE configs detected" in result.output


def test_install_network_config(tmp_path: Path) -> None:
    server = McpServer(
        name="net-srv",
        transport=TransportType.SSE,
        network_config=NetworkConfig(type="sse", url="http://localhost:3000/sse"),
        source_tool="mcp-manager",
    )
    config_path = tmp_path / "cursor_mcp.json"
    _write_fake_config(config_path, {})

    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=server)
        mock_reg.return_value = instance

        wb = ConfigWritebackTarget()
        wb._ide_configs = {"cursor": (config_path, None)}

        with patch("mcp_manager.commands.install.ConfigWriteback", new=lambda: wb):
            result = runner.invoke(app, ["server", "install", "net-srv", "--ide", "cursor"])

    assert result.exit_code == 0
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["net-srv"]["type"] == "sse"
    assert data["net-srv"]["url"] == "http://localhost:3000/sse"


def test_install_wrapper_key_merged(tmp_path: Path, sample_server: McpServer) -> None:
    """IDE configs with wrapper keys (e.g. mcpServers) are handled correctly."""
    config_path = tmp_path / "claude_code_settings.json"
    _write_fake_config(config_path, {"mcpServers": {"existing": {"command": "old"}}})

    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=sample_server)
        mock_reg.return_value = instance

        wb = ConfigWritebackTarget()
        wb._ide_configs = {"claude-code": (config_path, "mcpServers")}

        with patch("mcp_manager.commands.install.ConfigWriteback", new=lambda: wb):
            result = runner.invoke(
                app, ["server", "install", "my-server", "--ide", "claude-code"]
            )

    assert result.exit_code == 0
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert "my-server" in data["mcpServers"]
    assert "existing" in data["mcpServers"]


def test_install_writeback_error_propagated(tmp_path: Path, sample_server: McpServer) -> None:
    from mcp_manager.writeback import ConfigWriteback, WritebackError

    config_path = tmp_path / "cursor_mcp.json"
    _write_fake_config(config_path, {"existing": {"command": "old"}})

    with patch("mcp_manager.commands.install.ServerRegistry") as mock_reg:
        instance = MagicMock()
        instance.get.return_value = RegistryEntry(server=sample_server)
        mock_reg.return_value = instance

        wb = MagicMock(spec=ConfigWriteback)
        wb.get_supported_ides.return_value = ["cursor"]
        wb._ide_configs = {"cursor": (config_path, None)}
        wb.preview.return_value = {}
        wb.write_servers.side_effect = WritebackError("Disk full")

        with patch("mcp_manager.commands.install.ConfigWriteback", new=lambda: wb):
            result = runner.invoke(app, ["server", "install", "my-server", "--ide", "cursor"])

    assert result.exit_code == 0  # renders error inline, doesn't crash CLI
    assert "Disk full" in result.output
    assert "error" in result.output.lower()

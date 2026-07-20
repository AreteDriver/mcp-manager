"""Tests for mcp_manager.cli."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from mcp_manager import __version__
from mcp_manager.cli import app
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType

runner = CliRunner()


def _sample_servers() -> list[McpServer]:
    """Return a small set of servers for CLI tests."""
    return [
        McpServer(
            name="filesystem",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="npx", args=["-y", "server-fs"]),
            source_tool="claude-code",
            source_path=Path("/home/test/.claude.json"),
        ),
        McpServer(
            name="slack",
            transport=TransportType.HTTP,
            network_config=NetworkConfig(type="http", url="https://mcp.slack.com/mcp"),
            source_tool="cursor",
            source_path=Path("/home/test/.cursor/mcp.json"),
        ),
    ]


class TestVersion:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_short_version_flag(self) -> None:
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert __version__ in result.output


class TestNoArgs:
    def test_shows_help(self) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Manage MCP servers" in result.output


class TestListCommand:
    def test_list_no_servers(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=[]):
            result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No MCP servers found" in result.output

    def test_list_shows_table(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "filesystem" in result.output
        assert "slack" in result.output
        assert "claude-code" in result.output
        assert "cursor" in result.output

    def test_list_filter_transport(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["list", "--transport", "http"])
        assert result.exit_code == 0
        assert "slack" in result.output
        assert "filesystem" not in result.output

    def test_list_invalid_transport(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["list", "--transport", "invalid"])
        assert result.exit_code == 1
        assert "Unknown transport" in result.output

    def test_list_json_output(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2
        names = {s["name"] for s in data}
        assert names == {"filesystem", "slack"}


class TestMapCommand:
    def test_map_no_servers(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=[]):
            result = runner.invoke(app, ["map"])
        assert result.exit_code == 0
        assert "No MCP servers found" in result.output

    def test_map_shows_table(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["map"])
        assert result.exit_code == 0
        assert "filesystem" in result.output
        assert "slack" in result.output

    def test_map_json_output(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["map", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


class TestHealthCommand:
    def test_health_no_servers(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=[]):
            result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert "No MCP servers found" in result.output

    def test_health_shows_table(self) -> None:
        from mcp_manager.models import HealthResult, ServerStatus

        servers = _sample_servers()
        results = [
            HealthResult(
                server_name="filesystem",
                status=ServerStatus.HEALTHY,
                latency_ms=12.0,
                transport=TransportType.STDIO,
                server_info={"server_name": "fs-server"},
            ),
            HealthResult(
                server_name="slack",
                status=ServerStatus.UNREACHABLE,
                latency_ms=None,
                transport=TransportType.HTTP,
                error_message="Connection refused",
            ),
        ]
        with (
            patch("mcp_manager.cli._discover", return_value=servers),
            patch("mcp_manager.cli.HealthChecker") as mock_cls,
        ):
            mock_cls.return_value.check_all = AsyncMock(return_value=results)
            result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert "filesystem" in result.output
        assert "slack" in result.output

    def test_health_json_output(self) -> None:
        from mcp_manager.models import HealthResult, ServerStatus

        servers = _sample_servers()
        results = [
            HealthResult(
                server_name="filesystem",
                status=ServerStatus.HEALTHY,
                latency_ms=12.0,
                transport=TransportType.STDIO,
            ),
        ]
        with (
            patch("mcp_manager.cli._discover", return_value=servers),
            patch("mcp_manager.cli.HealthChecker") as mock_cls,
        ):
            mock_cls.return_value.check_all = AsyncMock(return_value=results)
            result = runner.invoke(app, ["health", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["server_name"] == "filesystem"

    def test_health_specific_server(self) -> None:
        from mcp_manager.models import HealthResult, ServerStatus

        servers = _sample_servers()
        results = [
            HealthResult(
                server_name="filesystem",
                status=ServerStatus.HEALTHY,
                latency_ms=12.0,
                transport=TransportType.STDIO,
            ),
        ]
        with (
            patch("mcp_manager.cli._discover", return_value=servers),
            patch("mcp_manager.cli.HealthChecker") as mock_cls,
        ):
            mock_cls.return_value.check_all = AsyncMock(return_value=results)
            result = runner.invoke(app, ["health", "--server", "filesystem"])
        assert result.exit_code == 0
        assert "filesystem" in result.output
        assert "slack" not in result.output

    def test_health_discovery_error(self) -> None:
        from mcp_manager.exceptions import McpManagerError

        with patch("mcp_manager.cli._discover", side_effect=McpManagerError("boom")):
            result = runner.invoke(app, ["health"])
        assert result.exit_code == 1
        assert "Discovery error" in result.output


class TestAddCommand:
    def test_add_stdio_success(self) -> None:
        mock_reg = patch("mcp_manager.cli._get_registry").start()
        mock_reg.return_value.add = lambda s: None
        mock_reg.return_value.save = lambda: None
        result = runner.invoke(app, ["add", "my-server", "--command", "node", "--arg", "server.js"])
        patch.stopall()
        assert result.exit_code == 0
        assert "Added server" in result.output
        assert "stdio" in result.output

    def test_add_network_success(self) -> None:
        mock_reg = patch("mcp_manager.cli._get_registry").start()
        mock_reg.return_value.add = lambda s: None
        mock_reg.return_value.save = lambda: None
        result = runner.invoke(app, ["add", "my-server", "--url", "http://localhost:3000"])
        patch.stopall()
        assert result.exit_code == 0
        assert "Added server" in result.output

    def test_add_both_command_and_url_fails(self) -> None:
        result = runner.invoke(
            app, ["add", "my-server", "--command", "node", "--url", "http://localhost"]
        )
        assert result.exit_code == 1
        assert "not both" in result.output

    def test_add_neither_command_nor_url_fails(self) -> None:
        result = runner.invoke(app, ["add", "my-server"])
        assert result.exit_code == 1
        assert "Specify --command" in result.output

    def test_add_unknown_transport(self) -> None:
        result = runner.invoke(app, ["add", "my-server", "--command", "node", "--transport", "ftp"])
        assert result.exit_code == 1
        assert "Unknown transport" in result.output


class TestRemoveCommand:
    def test_remove_success(self) -> None:
        mock_reg = patch("mcp_manager.cli._get_registry").start()
        mock_reg.return_value.remove = lambda name: True
        mock_reg.return_value.save = lambda: None
        result = runner.invoke(app, ["remove", "my-server"])
        patch.stopall()
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_remove_not_found(self) -> None:
        mock_reg = patch("mcp_manager.cli._get_registry").start()
        mock_reg.return_value.remove = lambda name: False
        result = runner.invoke(app, ["remove", "my-server"])
        patch.stopall()
        assert result.exit_code == 1
        assert "not found" in result.output


class TestExportCommand:
    def test_export_success(self) -> None:
        with (
            patch("mcp_manager.cli._discover", return_value=_sample_servers()),
            patch("mcp_manager.cli.export_servers") as mock_export,
        ):
            result = runner.invoke(app, ["export", "/tmp/out.yml"])
        assert result.exit_code == 0
        assert "Exported 2 server" in result.output
        mock_export.assert_called_once()

    def test_export_no_servers(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=[]):
            result = runner.invoke(app, ["export", "/tmp/out.yml"])
        assert result.exit_code == 0
        assert "No servers to export" in result.output

    def test_export_discovery_error(self) -> None:
        from mcp_manager.exceptions import McpManagerError

        with patch("mcp_manager.cli._discover", side_effect=McpManagerError("boom")):
            result = runner.invoke(app, ["export", "/tmp/out.yml"])
        assert result.exit_code == 1
        assert "Discovery error" in result.output


class TestImportCommand:
    def test_import_success(self) -> None:
        servers = _sample_servers()
        with patch("mcp_manager.cli.import_servers", return_value=servers):
            mock_reg = patch("mcp_manager.cli._get_registry").start()
            mock_reg.return_value.add = lambda s: None
            mock_reg.return_value.save = lambda: None
            result = runner.invoke(app, ["import", "/tmp/in.yml"])
            patch.stopall()
        assert result.exit_code == 0
        assert "Imported 2 server" in result.output

    def test_import_dry_run(self) -> None:
        servers = _sample_servers()
        with patch("mcp_manager.cli.import_servers", return_value=servers):
            result = runner.invoke(app, ["import", "/tmp/in.yml", "--dry-run"])
        assert result.exit_code == 0
        assert "Would import 2 server" in result.output

    def test_import_error(self) -> None:
        from mcp_manager.exceptions import McpManagerError

        with patch("mcp_manager.cli.import_servers", side_effect=McpManagerError("boom")):
            result = runner.invoke(app, ["import", "/tmp/in.yml"])
        assert result.exit_code == 1
        assert "Import error" in result.output


class TestTestCommand:
    def test_test_server_not_found(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=_sample_servers()):
            result = runner.invoke(app, ["test", "missing"])
        assert result.exit_code == 1
        assert "Server not found" in result.output

    def test_test_server_found_json(self) -> None:
        from mcp_manager.models import HealthResult, ServerStatus

        servers = _sample_servers()
        result_obj = HealthResult(
            server_name="filesystem",
            status=ServerStatus.HEALTHY,
            latency_ms=12.0,
            transport=TransportType.STDIO,
            protocol_version="2024-11-05",
            server_info={
                "server_name": "fs-server",
                "server_version": "1.0.0",
                "capabilities": {"tools": {}},
            },
        )
        with (
            patch("mcp_manager.cli._discover", return_value=servers),
            patch("mcp_manager.cli.HealthChecker") as mock_cls,
        ):
            mock_cls.return_value.check = AsyncMock(return_value=result_obj)
            result = runner.invoke(app, ["test", "filesystem", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["server_name"] == "filesystem"

    def test_test_server_found_table(self) -> None:
        from mcp_manager.models import HealthResult, ServerStatus

        servers = _sample_servers()
        result_obj = HealthResult(
            server_name="filesystem",
            status=ServerStatus.HEALTHY,
            latency_ms=12.0,
            transport=TransportType.STDIO,
        )
        with (
            patch("mcp_manager.cli._discover", return_value=servers),
            patch("mcp_manager.cli.HealthChecker") as mock_cls,
        ):
            mock_cls.return_value.check = AsyncMock(return_value=result_obj)
            result = runner.invoke(app, ["test", "filesystem"])
        assert result.exit_code == 0
        assert "filesystem" in result.output


class TestStatusCommand:
    def test_status_shows_version_and_tier(self) -> None:
        from unittest.mock import MagicMock

        from mcp_manager.licensing import Tier, TierConfig

        mock_info = MagicMock()
        mock_info.tier = Tier.FREE
        mock_info.license_key = None
        mock_info.valid = True

        tier_def = {
            Tier.FREE: TierConfig(
                name="Free",
                price_label="Free forever",
                features=["list", "health"],
            ),
        }
        with (
            patch("mcp_manager.licensing.get_license_info", return_value=mock_info),
            patch("mcp_manager.licensing.TIER_DEFINITIONS", tier_def),
        ):
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert __version__ in result.output
        assert "Free" in result.output


class TestStatsCommand:
    def test_stats_disabled(self) -> None:
        with patch("mcp_manager.telemetry.is_enabled", return_value=False):
            result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "Telemetry is disabled" in result.output

    def test_stats_no_data(self, tmp_path: Path) -> None:
        db_file = tmp_path / "telemetry.db"
        db_file.unlink(missing_ok=True)

        with (
            patch("mcp_manager.cli.track_command"),
            patch("mcp_manager.telemetry.is_enabled", return_value=True),
            patch("mcp_manager.telemetry._telemetry_dir", return_value=tmp_path),
        ):
            result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "No telemetry data" in result.output

    def test_stats_with_data(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        (tmp_path / "telemetry.db").touch()
        mock_ts = MagicMock()
        mock_ts.get_command_counts.return_value = {"health": 5, "list": 3}
        mock_ts.get_pro_gate_counts.return_value = {"sync": 2}
        mock_ts.get_total_events.return_value = 10
        mock_ts.get_first_event_time.return_value = "2026-01-01"
        mock_ts.get_last_event_time.return_value = "2026-07-01"
        mock_ts.get_daily_activity.return_value = [("2026-07-01", 5)]

        with (
            patch("mcp_manager.cli.track_command"),
            patch("mcp_manager.telemetry.is_enabled", return_value=True),
            patch("mcp_manager.telemetry._telemetry_dir", return_value=tmp_path),
            patch("mcp_manager.telemetry.TelemetryStore", return_value=mock_ts),
        ):
            result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "Total Events" in result.output
        assert "health" in result.output

    def test_stats_json_output(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        (tmp_path / "telemetry.db").touch()
        mock_ts = MagicMock()
        mock_ts.get_command_counts.return_value = {"health": 5}
        mock_ts.get_pro_gate_counts.return_value = {}
        mock_ts.get_total_events.return_value = 5
        mock_ts.get_first_event_time.return_value = "2026-01-01"
        mock_ts.get_last_event_time.return_value = "2026-07-01"
        mock_ts.get_daily_activity.return_value = []

        with (
            patch("mcp_manager.cli.track_command"),
            patch("mcp_manager.telemetry.is_enabled", return_value=True),
            patch("mcp_manager.telemetry._telemetry_dir", return_value=tmp_path),
            patch("mcp_manager.telemetry.TelemetryStore", return_value=mock_ts),
        ):
            result = runner.invoke(app, ["stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_events"] == 5


class TestSyncCommand:
    def test_sync_dry_run(self) -> None:
        servers = _sample_servers()
        with patch("mcp_manager.cli._discover", return_value=servers):
            mock_wb = MagicMock()
            mock_wb.preview.return_value = {"cursor": "preview"}
            with patch("mcp_manager.writeback.ConfigWriteback", return_value=mock_wb):
                result = runner.invoke(app, ["sync", "--ide", "cursor", "--dry-run"])
        assert result.exit_code == 0
        assert "cursor" in result.output

    def test_sync_no_servers(self) -> None:
        with patch("mcp_manager.cli._discover", return_value=[]):
            result = runner.invoke(app, ["sync", "--ide", "cursor"])
        assert result.exit_code == 0
        assert "No MCP servers found" in result.output

    def test_sync_discovery_error(self) -> None:
        from mcp_manager.exceptions import McpManagerError

        with patch("mcp_manager.cli._discover", side_effect=McpManagerError("boom")):
            result = runner.invoke(app, ["sync", "--ide", "cursor"])
        assert result.exit_code == 1
        assert "Discovery error" in result.output


class TestValidateCommand:
    def test_validate_success(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".mcp-manager.yml"
        config_file.write_text("project: test\nservers: {}\n")
        with patch("mcp_manager.project_config.validate_project_config", return_value=[]):
            result = runner.invoke(app, ["validate", "--path", str(config_file)])
        assert result.exit_code == 0
        assert "valid" in result.output

    def test_validate_not_found(self) -> None:
        with patch("mcp_manager.project_config.validate_project_config"):
            result = runner.invoke(app, ["validate", "--path", "/nonexistent"])
        assert result.exit_code == 1
        assert "Config not found" in result.output

    def test_validate_with_errors(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".mcp-manager.yml"
        config_file.write_text("project: test\nservers: {}\n")
        with patch(
            "mcp_manager.project_config.validate_project_config",
            return_value=["missing command"],
        ):
            result = runner.invoke(app, ["validate", "--path", str(config_file)])
        assert result.exit_code == 1
        assert "1 error" in result.output

    def test_validate_strict_success(self, tmp_path: Path) -> None:
        from mcp_manager.models import HealthResult, ServerStatus

        config_file = tmp_path / ".mcp-manager.yml"
        config_file.write_text("project: test\nservers: {}\n")
        servers = _sample_servers()
        results = [
            HealthResult(
                server_name="filesystem",
                status=ServerStatus.HEALTHY,
                latency_ms=12.0,
                transport=TransportType.STDIO,
            ),
        ]
        with (
            patch("mcp_manager.project_config.validate_project_config", return_value=[]),
            patch("mcp_manager.project_config.load_servers_from_config", return_value=servers),
            patch("mcp_manager.health.HealthChecker") as mock_cls,
        ):
            mock_cls.return_value.check_all = AsyncMock(return_value=results)
            result = runner.invoke(app, ["validate", "--path", str(config_file), "--strict"])
        assert result.exit_code == 0
        assert "passed deep health check" in result.output

    def test_validate_strict_fails(self, tmp_path: Path) -> None:
        from mcp_manager.models import HealthResult, ServerStatus

        config_file = tmp_path / ".mcp-manager.yml"
        config_file.write_text("project: test\nservers: {}\n")
        servers = _sample_servers()
        results = [
            HealthResult(
                server_name="filesystem",
                status=ServerStatus.UNREACHABLE,
                latency_ms=None,
                transport=TransportType.STDIO,
                error_message="timeout",
            ),
        ]
        with (
            patch("mcp_manager.project_config.validate_project_config", return_value=[]),
            patch("mcp_manager.project_config.load_servers_from_config", return_value=servers),
            patch("mcp_manager.health.HealthChecker") as mock_cls,
        ):
            mock_cls.return_value.check_all = AsyncMock(return_value=results)
            result = runner.invoke(app, ["validate", "--path", str(config_file), "--strict"])
        assert result.exit_code == 1
        assert "failed deep health check" in result.output


class TestMonitorCommand:
    def test_monitor_no_config(self, tmp_path: Path) -> None:
        # Use a temp dir that does NOT contain .mcp-manager.yml
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = runner.invoke(app, ["monitor", "--project", str(empty_dir)])
        assert result.exit_code == 1
        assert "Config not found" in result.output

    def test_monitor_no_stdio_servers(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".mcp-manager.yml"
        config_file.write_text("project: test\nservers: {}\n")
        http_only = [
            McpServer(
                name="slack",
                transport=TransportType.HTTP,
                network_config=NetworkConfig(type="http", url="https://mcp.slack.com/mcp"),
                source_tool="test",
            ),
        ]
        with patch("mcp_manager.project_config.load_servers_from_config", return_value=http_only):
            result = runner.invoke(app, ["monitor", "--project", str(tmp_path)])
        assert result.exit_code == 0
        assert "No stdio servers" in result.output

    def test_monitor_success_json(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".mcp-manager.yml"
        config_file.write_text("project: test\nservers: {}\n")
        stdio_server = McpServer(
            name="fs",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="npx"),
            source_tool="test",
        )
        summary = {"fs": {"restart_count": 0, "final_exit_code": None}}
        with (
            patch(
                "mcp_manager.project_config.load_servers_from_config",
                return_value=[stdio_server],
            ),
            patch("mcp_manager.monitor.ServerMonitor") as mock_cls,
        ):
            mock_cls.return_value.run = AsyncMock(return_value=summary)
            result = runner.invoke(app, ["monitor", "--project", str(tmp_path), "--json"])
        assert result.exit_code == 0
        assert '"restart_count": 0' in result.output
        assert '"fs"' in result.output


class TestProjectCommands:
    def test_project_init_success(self) -> None:
        with patch(
            "mcp_manager.project_config.init_project_config",
            return_value=Path("/tmp/.mcp-manager.yml"),
        ):
            result = runner.invoke(app, ["project", "init"])
        assert result.exit_code == 0
        assert "Created" in result.output

    def test_project_init_error(self) -> None:
        from mcp_manager.exceptions import McpManagerError

        with patch(
            "mcp_manager.project_config.init_project_config",
            side_effect=McpManagerError("exists"),
        ):
            result = runner.invoke(app, ["project", "init"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_project_validate_success(self) -> None:
        with patch("mcp_manager.project_config.validate_project_config", return_value=[]):
            result = runner.invoke(app, ["project", "validate", "--path", "/fake"])
        assert result.exit_code == 0
        assert "valid" in result.output

    def test_project_validate_errors(self) -> None:
        with patch(
            "mcp_manager.project_config.validate_project_config",
            return_value=["bad config"],
        ):
            result = runner.invoke(app, ["project", "validate", "--path", "/fake"])
        assert result.exit_code == 1
        assert "1 error" in result.output

    def test_project_export_success(self) -> None:
        with patch(
            "mcp_manager.project_config.export_to_ide",
            return_value=Path("/tmp/out.json"),
        ):
            result = runner.invoke(app, ["project", "export", "--ide", "cursor", "--path", "/fake"])
        assert result.exit_code == 0
        assert "Exported to" in result.output

    def test_project_export_dry_run(self) -> None:
        with patch(
            "mcp_manager.project_config.export_to_ide",
            return_value=Path("/tmp/out.json"),
        ):
            result = runner.invoke(
                app,
                [
                    "project",
                    "export",
                    "--ide",
                    "cursor",
                    "--path",
                    "/fake",
                    "--dry-run",
                ],
            )
        assert result.exit_code == 0
        assert "Dry-run" in result.output

    def test_project_export_error(self) -> None:
        from mcp_manager.exceptions import McpManagerError

        with patch(
            "mcp_manager.project_config.export_to_ide",
            side_effect=McpManagerError("boom"),
        ):
            result = runner.invoke(app, ["project", "export", "--ide", "cursor", "--path", "/fake"])
        assert result.exit_code == 1
        assert "Export error" in result.output


class TestLockCommand:
    """CLI tests for the lock command."""

    def test_lock_missing_config(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["lock", "--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "Config not found" in result.output

    def test_lock_writes_lockfile(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp-manager.yml"
        config.write_text("servers:\n  srv:\n    command: npx\n    args: [pkg@1.0.0]\n")
        result = runner.invoke(app, ["lock", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "Wrote lockfile" in result.output
        lockfile = tmp_path / ".mcp-manager.lock"
        assert lockfile.exists()

    def test_lock_json_output(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp-manager.yml"
        config.write_text("servers:\n  srv:\n    command: npx\n    args: [pkg@1.0.0]\n")
        result = runner.invoke(app, ["lock", "--path", str(tmp_path), "--json"])
        assert result.exit_code == 0
        assert '"lockfile"' in result.output

    def test_lock_check_missing_lockfile(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp-manager.yml"
        config.write_text("servers:\n  srv:\n    command: npx\n    args: [pkg@1.0.0]\n")
        result = runner.invoke(app, ["lock", "--check", "--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "Lockfile not found" in result.output

    def test_lock_check_current(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp-manager.yml"
        config.write_text("servers:\n  srv:\n    command: npx\n    args: [pkg@1.0.0]\n")
        lockfile = tmp_path / ".mcp-manager.lock"
        lockfile.write_text(
            "lockfileVersion: '1'\n"
            "resolvedAt: '2026-01-01T00:00:00+00:00'\n"
            "servers:\n"
            "  srv:\n"
            "    resolvedVersion: 1.0.0\n"
        )
        result = runner.invoke(app, ["lock", "--check", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "Lockfile is current" in result.output

    def test_lock_check_mismatch(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp-manager.yml"
        config.write_text("servers:\n  srv:\n    command: npx\n    args: [pkg@2.0.0]\n")
        lockfile = tmp_path / ".mcp-manager.lock"
        lockfile.write_text(
            "lockfileVersion: '1'\n"
            "resolvedAt: '2026-01-01T00:00:00+00:00'\n"
            "servers:\n"
            "  srv:\n"
            "    resolvedVersion: 1.0.0\n"
        )
        result = runner.invoke(app, ["lock", "--check", "--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "lockfile error" in result.output

    def test_lock_check_json_output(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp-manager.yml"
        config.write_text("servers:\n  srv:\n    command: npx\n    args: [pkg@2.0.0]\n")
        lockfile = tmp_path / ".mcp-manager.lock"
        lockfile.write_text(
            "lockfileVersion: '1'\n"
            "resolvedAt: '2026-01-01T00:00:00+00:00'\n"
            "servers:\n"
            "  srv:\n"
            "    resolvedVersion: 1.0.0\n"
        )
        result = runner.invoke(app, ["lock", "--check", "--path", str(tmp_path), "--json"])
        assert result.exit_code == 1
        assert '"errors"' in result.output

    def test_lock_check_bad_lockfile(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp-manager.yml"
        config.write_text("servers:\n  srv:\n    command: npx\n    args: [pkg@1.0.0]\n")
        lockfile = tmp_path / ".mcp-manager.lock"
        lockfile.write_text("not: yaml: [")
        result = runner.invoke(app, ["lock", "--check", "--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "Lockfile error" in result.output

    def test_lock_config_error(self, tmp_path: Path) -> None:
        config = tmp_path / ".mcp-manager.yml"
        config.write_text("bad")
        result = runner.invoke(app, ["lock", "--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "Config error" in result.output


class TestSearchCommand:
    """CLI tests for marketplace search."""

    def test_search_no_results(self) -> None:
        result = runner.invoke(app, ["search", "zzzznonexistent"])
        assert result.exit_code == 0
        assert "No marketplace servers found" in result.output

    def test_search_finds_server(self) -> None:
        result = runner.invoke(app, ["search", "filesystem", "--include-unverified"])
        assert result.exit_code == 0
        assert "Filesystem MCP" in result.output

    def test_search_category_filter(self) -> None:
        result = runner.invoke(
            app, ["search", "", "--category", "Database", "--include-unverified"]
        )
        assert result.exit_code == 0
        assert "PostgreSQL MCP" in result.output

    def test_search_unverified_hidden(self) -> None:
        result = runner.invoke(app, ["search", ""])
        # Default hides unverified; official servers are unverified in seed data.
        assert result.exit_code == 0
        assert "No marketplace servers found" in result.output

    def test_search_include_unverified(self) -> None:
        result = runner.invoke(app, ["search", "", "--include-unverified"])
        assert result.exit_code == 0
        assert "Filesystem MCP" in result.output

    def test_search_json(self) -> None:
        result = runner.invoke(app, ["search", "filesystem", "--json", "--include-unverified"])
        assert result.exit_code == 0
        assert '"servers"' in result.output


class TestInfoCommand:
    """CLI tests for marketplace info."""

    def test_info_found(self) -> None:
        result = runner.invoke(app, ["info", "filesystem"])
        assert result.exit_code == 0
        assert "Filesystem MCP" in result.output
        assert "Repository:" in result.output

    def test_info_not_found(self) -> None:
        result = runner.invoke(app, ["info", "zzzznonexistent"])
        assert result.exit_code == 1
        assert "Server not found" in result.output

    def test_info_json(self) -> None:
        result = runner.invoke(app, ["info", "filesystem", "--json"])
        assert result.exit_code == 0
        assert '"name": "filesystem"' in result.output


class TestInstallCommand:
    """CLI tests for marketplace install."""

    def test_install_adds_to_config(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["install", "puppeteer", "--path", str(tmp_path), "--no-prompt"],
        )
        assert result.exit_code == 0
        assert "Added 'puppeteer'" in result.output
        config = tmp_path / ".mcp-manager.yml"
        assert config.exists()

    def test_install_dry_run(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["install", "puppeteer", "--path", str(tmp_path), "--dry-run", "--no-prompt"],
        )
        assert result.exit_code == 0
        assert "Dry-run" in result.output
        config = tmp_path / ".mcp-manager.yml"
        assert not config.exists()

    def test_install_duplicate_fails(self, tmp_path: Path) -> None:
        runner.invoke(
            app,
            ["install", "puppeteer", "--path", str(tmp_path), "--no-prompt"],
        )
        result = runner.invoke(
            app,
            ["install", "puppeteer", "--path", str(tmp_path), "--no-prompt"],
        )
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_install_not_found(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["install", "zzzznonexistent", "--path", str(tmp_path), "--no-prompt"],
        )
        assert result.exit_code == 1
        assert "Server not found" in result.output

    def test_install_prompts_for_env(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["install", "postgres", "--path", str(tmp_path)],
            input="postgres://test\n",
        )
        assert result.exit_code == 0
        config = tmp_path / ".mcp-manager.yml"
        assert config.exists()
        import yaml

        data = yaml.safe_load(config.read_text())
        assert data["servers"]["postgres"]["env"]["DATABASE_URL"] == "postgres://test"

    def test_install_no_prompt_warns(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["install", "postgres", "--path", str(tmp_path), "--no-prompt"],
        )
        assert result.exit_code == 0
        assert "Remember to set env vars" in result.output

    def test_install_with_lock(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["install", "puppeteer", "--path", str(tmp_path), "--no-prompt", "--lock"],
        )
        assert result.exit_code == 0
        assert "Added 'puppeteer'" in result.output
        assert ".mcp-manager.lock" in result.output

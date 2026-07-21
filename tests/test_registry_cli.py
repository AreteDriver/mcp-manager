"""Tests for registry CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from mcp_manager.cli import app
from mcp_manager.models import McpServer, NetworkConfig, ServerStatus, StdioConfig, TransportType

runner = CliRunner()


def _make_registry_file(path: Path) -> None:
    path.write_text(
        yaml.dump({
            "servers": {
                "remote-fs": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                },
                "remote-slack": {"type": "sse", "url": "https://slack.example.com/sse"},
            }
        })
    )


def _make_project_file(path: Path) -> None:
    path.write_text(
        yaml.dump({
            "project": "test",
            "servers": {
                "local-fs": {"command": "node", "args": ["local.js"]},
            }
        })
    )


class TestRegistryDiff:
    """Tests for `mcp-manager registry diff`."""

    def test_diff_shows_changes(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _make_project_file(project_dir / ".mcp-manager.yml")

        registry = tmp_path / "registry.yaml"
        _make_registry_file(registry)

        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = registry.read_text()
            mock_get.return_value.raise_for_status = lambda: None

            result = runner.invoke(
                app, ["registry", "diff", str(registry), "--project-dir", str(project_dir)]
            )

        assert result.exit_code == 0
        assert "+ add" in result.output
        assert "remote-fs" in result.output
        assert "remote-slack" in result.output

    def test_diff_no_changes(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _make_project_file(project_dir / ".mcp-manager.yml")

        # Diff against a registry with only the local server
        registry = tmp_path / "registry.yaml"
        registry.write_text(
            yaml.dump({
                "servers": {
                    "local-fs": {"command": "node", "args": ["local.js"]},
                }
            })
        )

        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = registry.read_text()
            mock_get.return_value.raise_for_status = lambda: None

            result = runner.invoke(
                app, ["registry", "diff", str(registry), "--project-dir", str(project_dir)]
            )

        assert result.exit_code == 0
        assert "No changes" in result.output

    def test_diff_missing_project(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["registry", "diff", "https://example.com/reg.yaml", "--project-dir", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "Project config not found" in result.output


class TestRegistryPull:
    """Tests for `mcp-manager registry pull`."""

    def test_pull_union(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _make_project_file(project_dir / ".mcp-manager.yml")

        registry = tmp_path / "registry.yaml"
        _make_registry_file(registry)

        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = registry.read_text()
            mock_get.return_value.raise_for_status = lambda: None

            result = runner.invoke(
                app, ["registry", "pull", str(registry), "--project-dir", str(project_dir)]
            )

        assert result.exit_code == 0
        assert "Updated" in result.output
        assert "servers" in result.output

        # Verify disk
        data = yaml.safe_load((project_dir / ".mcp-manager.yml").read_text())
        assert "local-fs" in data["servers"]
        assert "remote-fs" in data["servers"]
        assert "remote-slack" in data["servers"]

    def test_pull_replace(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _make_project_file(project_dir / ".mcp-manager.yml")

        registry = tmp_path / "registry.yaml"
        _make_registry_file(registry)

        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = registry.read_text()
            mock_get.return_value.raise_for_status = lambda: None

            result = runner.invoke(
                app,
                [
                    "registry",
                    "pull",
                    str(registry),
                    "--project-dir",
                    str(project_dir),
                    "--strategy",
                    "replace",
                ],
            )

        assert result.exit_code == 0
        data = yaml.safe_load((project_dir / ".mcp-manager.yml").read_text())
        assert "local-fs" not in data["servers"]
        assert "remote-fs" in data["servers"]

    def test_pull_dry_run(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _make_project_file(project_dir / ".mcp-manager.yml")

        registry = tmp_path / "registry.yaml"
        _make_registry_file(registry)

        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = registry.read_text()
            mock_get.return_value.raise_for_status = lambda: None

            result = runner.invoke(
                app,
                ["registry", "pull", str(registry), "--project-dir", str(project_dir), "--dry-run"],
            )

        assert result.exit_code == 0
        assert "Would write" in result.output
        # Verify disk unchanged
        data = yaml.safe_load((project_dir / ".mcp-manager.yml").read_text())
        assert list(data["servers"].keys()) == ["local-fs"]

    def test_pull_unknown_strategy(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _make_project_file(project_dir / ".mcp-manager.yml")

        result = runner.invoke(
            app,
            [
                "registry",
                "pull",
                "https://example.com/reg.yaml",
                "--project-dir",
                str(project_dir),
                "--strategy",
                "bad",
            ],
        )
        assert result.exit_code == 1
        assert "Unknown strategy" in result.output

    def test_pull_verify_pass(self, tmp_path: Path) -> None:
        """--verify with mocked healthy results succeeds."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _make_project_file(project_dir / ".mcp-manager.yml")

        registry = tmp_path / "registry.yaml"
        registry.write_text(
            yaml.dump({
                "servers": {
                    "http-srv": {"type": "http", "url": "https://mcp.example.com/mcp"},
                }
            })
        )

        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = registry.read_text()
            mock_get.return_value.raise_for_status = lambda: None

            with patch("mcp_manager.commands.registry_cmd.verify_servers") as mock_verify:
                srv = McpServer(
                    name="http-srv",
                    transport=TransportType.HTTP,
                    network_config=NetworkConfig(type="http", url="https://mcp.example.com/mcp"),
                )
                mock_verify.return_value = [(srv, ServerStatus.HEALTHY, None)]

                result = runner.invoke(
                    app,
                    [
                        "registry",
                        "pull",
                        str(registry),
                        "--project-dir",
                        str(project_dir),
                        "--verify",
                    ],
                )

        assert result.exit_code == 0
        assert "passed verification" in result.output

    def test_pull_verify_fail(self, tmp_path: Path) -> None:
        """--verify with an unreachable server aborts."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _make_project_file(project_dir / ".mcp-manager.yml")

        registry = tmp_path / "registry.yaml"
        registry.write_text(
            yaml.dump({
                "servers": {
                    "bad-srv": {"command": "/does/not/exist"},
                }
            })
        )

        with patch("mcp_manager.registry_sync.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = registry.read_text()
            mock_get.return_value.raise_for_status = lambda: None

            with patch("mcp_manager.commands.registry_cmd.verify_servers") as mock_verify:
                srv = McpServer(
                    name="bad-srv",
                    transport=TransportType.STDIO,
                    stdio_config=StdioConfig(command="/does/not/exist"),
                )
                mock_verify.return_value = [(srv, ServerStatus.UNREACHABLE, "not found")]

                result = runner.invoke(
                    app,
                    [
                        "registry",
                        "pull",
                        str(registry),
                        "--project-dir",
                        str(project_dir),
                        "--verify",
                    ],
                )

        assert result.exit_code == 1
        assert "Aborting pull" in result.output

    def test_pull_missing_project(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["registry", "pull", "https://example.com/reg.yaml", "--project-dir", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "Project config not found" in result.output

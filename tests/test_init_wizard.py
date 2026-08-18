"""Tests for the onboarding wizard (`mcp-manager init`)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mcp_manager.cli import app
from mcp_manager.project_config import DEFAULT_FILENAME

runner = CliRunner()


class TestInitWizard:
    """CLI tests for `mcp-manager init`."""

    def test_init_creates_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        with patch("mcp_manager.commands.init_wizard._is_tty", return_value=False):
            result = runner.invoke(app, ["init", "--yes", "--project-name", "test-proj"])
        assert result.exit_code == 0
        config = tmp_path / DEFAULT_FILENAME
        assert config.exists()
        text = config.read_text()
        assert "project: test-proj" in text
        assert "filesystem" in text

    def test_init_overwrite_with_yes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        config = tmp_path / DEFAULT_FILENAME
        config.write_text("old")
        with patch("mcp_manager.commands.init_wizard._is_tty", return_value=False):
            result = runner.invoke(app, ["init", "--yes", "--project-name", "p"])
        assert result.exit_code == 0
        assert "Created" in result.output

    def test_init_import_existing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        cursor_config = tmp_path / ".cursor" / "mcp.json"
        cursor_config.parent.mkdir(parents=True)
        cursor_config.write_text(
            '{"mcpServers": {"fs": {"command": "npx", "args": ["server-fs"]}}}'
        )
        with (
            patch("mcp_manager.commands.init_wizard._is_tty", return_value=False),
            patch("mcp_manager.commands.init_wizard._detect_ides", return_value=["cursor"]),
            patch(
                "mcp_manager.config.IDE_CONFIG_PATHS",
                [("cursor", str(cursor_config), "mcpServers")],
            ),
        ):
            result = runner.invoke(
                app, ["init", "--yes", "--import-existing", "--project-name", "p"]
            )
        assert result.exit_code == 0
        assert "Imported" in result.output or "Added" in result.output

    def test_init_with_template(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        with patch("mcp_manager.commands.init_wizard._is_tty", return_value=False):
            result = runner.invoke(
                app, ["init", "--yes", "--template", "ai", "--project-name", "ai-proj"]
            )
        assert result.exit_code == 0
        assert "ai" in result.output or "Created" in result.output

    def test_init_unknown_template_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with patch("mcp_manager.commands.init_wizard._is_tty", return_value=False):
            result = runner.invoke(app, ["init", "--yes", "--template", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown template" in result.output

    def test_init_skips_when_no_tty_and_no_yes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        config = tmp_path / DEFAULT_FILENAME
        config.write_text("old")
        with patch("mcp_manager.commands.init_wizard._is_tty", return_value=False):
            result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "already exists" in result.output or "Use --yes" in result.output

    def test_init_preserves_gitignore(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n")
        with patch("mcp_manager.commands.init_wizard._is_tty", return_value=False):
            result = runner.invoke(app, ["init", "--yes"])
        assert result.exit_code == 0
        assert gitignore.read_text() == "*.pyc\n"

    def test_init_does_not_create_gitignore(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        with patch("mcp_manager.commands.init_wizard._is_tty", return_value=False):
            result = runner.invoke(app, ["init", "--yes"])
        assert result.exit_code == 0
        assert not (tmp_path / ".gitignore").exists()

    def test_init_warns_when_team_config_is_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(".mcp-manager.yml\n.mcp-manager.lock\n")

        with patch("mcp_manager.commands.init_wizard._is_tty", return_value=False):
            result = runner.invoke(app, ["init", "--yes"])

        assert result.exit_code == 0
        assert "Team config is ignored by Git" in result.output
        assert gitignore.read_text() == ".mcp-manager.yml\n.mcp-manager.lock\n"

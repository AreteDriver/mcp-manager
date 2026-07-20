"""Tests for project templates (`mcp-manager template`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from mcp_manager.cli import app
from mcp_manager.project_config import DEFAULT_FILENAME
from mcp_manager.templates import get_template, list_templates

runner = CliRunner()


class TestTemplateList:
    """Tests for `mcp-manager template list`."""

    def test_list_shows_templates(self) -> None:
        result = runner.invoke(app, ["template", "list"])
        assert result.exit_code == 0
        assert "python" in result.output
        assert "node" in result.output
        assert "data" in result.output
        assert "ai" in result.output


class TestTemplateUse:
    """Tests for `mcp-manager template use`."""

    def test_use_python_template(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["template", "use", "python"])
        assert result.exit_code == 0
        config = tmp_path / DEFAULT_FILENAME
        assert config.exists()
        text = config.read_text()
        assert "project:" in text
        assert "filesystem" in text

    def test_use_ai_template(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["template", "use", "ai"])
        assert result.exit_code == 0
        config = tmp_path / DEFAULT_FILENAME
        assert config.exists()
        text = config.read_text()
        assert "web-search" in text or "playwright" in text

    def test_use_custom_project_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app, ["template", "use", "python", "--project-name", "custom-name"]
        )
        assert result.exit_code == 0
        config = tmp_path / DEFAULT_FILENAME
        text = config.read_text()
        assert "custom-name" in text

    def test_use_existing_raises_without_force(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        config = tmp_path / DEFAULT_FILENAME
        config.write_text("existing")
        result = runner.invoke(app, ["template", "use", "python"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_use_existing_with_force(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        config = tmp_path / DEFAULT_FILENAME
        config.write_text("existing")
        result = runner.invoke(app, ["template", "use", "python", "--force"])
        assert result.exit_code == 0
        text = config.read_text()
        assert "project:" in text
        assert "filesystem" in text

    def test_use_unknown_template_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["template", "use", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown template" in result.output


class TestTemplateHelpers:
    """Unit tests for template helper functions."""

    def test_list_templates_sorted(self) -> None:
        names = list_templates()
        assert names == sorted(names)
        assert "python" in names

    def test_get_template_python(self) -> None:
        text = get_template("python", project_name="my-proj")
        assert "project: my-proj" in text
        assert "filesystem" in text
        assert "env: {}" in text

    def test_get_template_ai(self) -> None:
        text = get_template("ai", project_name="ai-proj")
        assert "project: ai-proj" in text
        assert "web-search" in text or "playwright" in text

    def test_get_template_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            get_template("nonexistent")

"""Reject malformed transport definitions before any import can write them."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from mcp_manager.commands.registry_cmd import registry_app
from mcp_manager.exceptions import WritebackError
from mcp_manager.project_config import _config_to_server, validate_project_config

INVALID = [
    {"command": None},
    {"command": ""},
    {"command": ["python"]},
    {"command": 123},
    {"command": "python", "type": "http"},
    {"command": "python", "url": "https://example.com"},
    {"type": "typo", "url": "https://example.com"},
    {"type": None, "url": "https://example.com"},
    {"type": "stdio", "url": "https://example.com"},
    {"url": None},
    {"url": []},
    {"url": "not-a-url"},
    {"url": "file:///private/tmp/example"},
    {"url": "https://"},
    {"command": "python", "args": "--help"},
    {"command": "python", "args": [None]},
    {"command": "python", "env": {"TOKEN": {"nested": "synthetic"}}},
    {"url": "https://example.com", "headers": {"Authorization": ["synthetic"]}},
]


@pytest.mark.parametrize("config", INVALID)
def test_invalid_project_definition_is_rejected(config):
    with pytest.raises(WritebackError):
        _config_to_server("fixture", config)


@pytest.mark.parametrize("config", INVALID)
def test_invalid_registry_definition_cannot_replace_local(tmp_path: Path, config):
    target = tmp_path / ".mcp-manager.yml"
    original = "servers:\n  keep: {command: python}\n"
    target.write_text(original)
    with (
        patch("mcp_manager.registry_sync.httpx.get") as get,
        patch("mcp_manager.telemetry.track_command"),
        patch("mcp_manager.commands.registry_cmd._build_headers", return_value=None),
    ):
        get.return_value.status_code = 200
        get.return_value.text = yaml.safe_dump({"servers": {"invalid": config}})
        get.return_value.raise_for_status = lambda: None
        result = CliRunner().invoke(
            registry_app,
            ["pull", "https://example.com/r", "-p", str(tmp_path), "--strategy", "replace"],
        )
    assert result.exit_code == 1
    assert target.read_text() == original
    assert not target.with_suffix(".yml.mcp-manager-backup").exists()


@pytest.mark.parametrize("config", INVALID)
def test_validate_reports_same_invalid_schema(tmp_path: Path, config):
    target = tmp_path / ".mcp-manager.yml"
    target.write_text(yaml.safe_dump({"servers": {"invalid": config}}))
    assert validate_project_config(target)

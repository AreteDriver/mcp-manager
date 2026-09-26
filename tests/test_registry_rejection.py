"""Registry rejection must preserve configuration and avoid echoing payloads."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mcp_manager.commands.registry_cmd import registry_app
from mcp_manager.exceptions import WritebackError
from mcp_manager.registry_sync import fetch_remote_servers


@pytest.mark.parametrize(
    "payload",
    [
        "servers:\n  existing: not-a-mapping\n",
        "servers:\n  existing: {}\n",
        "servers:\n  good: {command: python}\n  bad: {env: {TOKEN: synthetic-secret}}\n",
        "servers:\n  bad: {command: python, env: []}\n",
        "project: wrong-document\n",
    ],
)
def test_replace_rejects_partial_registry_without_writing(tmp_path: Path, payload: str) -> None:
    config = tmp_path / ".mcp-manager.yml"
    original = "project: keep\nservers:\n  existing:\n    command: python\n"
    config.write_text(original)
    with (
        patch("mcp_manager.registry_sync.httpx.get") as get,
        patch("mcp_manager.telemetry.track_command"),
        patch("mcp_manager.commands.registry_cmd._build_headers", return_value=None),
    ):
        get.return_value.status_code = 200
        get.return_value.text = payload
        get.return_value.raise_for_status = lambda: None
        result = CliRunner().invoke(
            registry_app,
            [
                "pull",
                "https://example.com/registry.yaml",
                "--project-dir",
                str(tmp_path),
                "--strategy",
                "replace",
            ],
        )
    assert result.exit_code == 1
    assert "Failed to fetch registry" in result.output
    assert config.read_text() == original
    assert not (tmp_path / ".mcp-manager.yml.mcp-manager-backup").exists()
    assert "synthetic-secret" not in result.output


def test_malformed_yaml_does_not_echo_payload_or_authenticated_url() -> None:
    marker = "synthetic-secret-canary"
    with patch("mcp_manager.registry_sync.httpx.get") as get:
        get.return_value.status_code = 200
        get.return_value.text = f"servers: [{marker}: broken"
        get.return_value.raise_for_status = lambda: None
        with pytest.raises(WritebackError) as error:
            fetch_remote_servers(f"https://example.com/registry.yaml?token={marker}")
    assert marker not in str(error.value)


def test_explicit_empty_registry_remains_valid() -> None:
    with patch("mcp_manager.registry_sync.httpx.get") as get:
        get.return_value.status_code = 200
        get.return_value.text = "servers: {}"
        get.return_value.raise_for_status = lambda: None
        assert fetch_remote_servers("https://example.com/registry.yaml") == []

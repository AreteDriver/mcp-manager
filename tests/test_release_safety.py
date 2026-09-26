"""Regressions for credential-safe registry writes and truthful health reports."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from mcp_manager.commands.registry_cmd import registry_app
from mcp_manager.health import HealthChecker
from mcp_manager.models import McpServer, NetworkConfig, ServerStatus
from mcp_manager.project_config import load_servers_from_config
from mcp_manager.registry import ServerRegistry

MARKER = "synthetic-credential-canary"
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "serverInfo": {"name": "fixture", "version": "1"},
    },
}


@pytest.mark.parametrize("verify", [False, True])
def test_pull_preserves_local_and_remote_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verify: bool,
) -> None:
    monkeypatch.setenv("RELEASE_TEST_TOKEN", MARKER)
    config = tmp_path / ".mcp-manager.yml"
    config.write_text(
        yaml.safe_dump(
            {
                "project": "fixture",
                "servers": {
                    "local": {"command": "python", "env": {"TOKEN": "${RELEASE_TEST_TOKEN}"}},
                },
            }
        )
    )
    with (
        patch("mcp_manager.registry_sync.httpx.get") as get,
        patch("mcp_manager.telemetry.track_command"),
        patch("mcp_manager.commands.registry_cmd._build_headers", return_value=None),
        patch("mcp_manager.registry_sync.HealthChecker.check_all", new_callable=AsyncMock) as check,
    ):
        from mcp_manager.models import HealthResult

        check.return_value = [
            HealthResult(server_name="remote", status=ServerStatus.HEALTHY, transport="stdio")
        ]
        get.return_value.status_code = 200
        get.return_value.text = yaml.safe_dump(
            {
                "servers": {
                    "remote": {"command": "python", "env": {"TOKEN": "${RELEASE_TEST_TOKEN}"}},
                }
            }
        )
        get.return_value.raise_for_status = lambda: None
        args = ["pull", "https://example.com/registry.yaml", "-p", str(tmp_path)]
        result = CliRunner().invoke(registry_app, args + (["--verify"] if verify else []))
        assert result.exit_code == 0, result.output
        if verify:
            assert check.call_args.args[0][0].stdio_config.env["TOKEN"] == MARKER
    data = yaml.safe_load(config.read_text())
    for name in ("local", "remote"):
        assert data["servers"][name]["env"]["TOKEN"] == "${RELEASE_TEST_TOKEN}"
    assert MARKER not in result.output
    assert MARKER not in config.read_text()
    assert MARKER not in config.with_suffix(".yml.mcp-manager-backup").read_text()


def test_invalid_local_config_rejects_pull_without_partial_write(tmp_path: Path) -> None:
    config = tmp_path / ".mcp-manager.yml"
    original = "servers:\n  keep: {command: python}\n  broken: []\n"
    config.write_text(original)
    with (
        patch("mcp_manager.telemetry.track_command"),
        patch("mcp_manager.commands.registry_cmd._build_headers", return_value=None),
        patch("mcp_manager.commands.registry_cmd.fetch_remote_servers", return_value=[]),
    ):
        result = CliRunner().invoke(
            registry_app, ["pull", "https://example.com/r", "-p", str(tmp_path)]
        )
    assert result.exit_code == 1
    assert config.read_text() == original
    assert not config.with_suffix(".yml.mcp-manager-backup").exists()


def test_rejected_local_entry_does_not_log_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = tmp_path / ".mcp-manager.yml"
    config.write_text(yaml.safe_dump({"servers": {MARKER: {"env": {"TOKEN": MARKER}}}}))
    assert load_servers_from_config(config) == []
    assert MARKER not in caplog.text


def test_rejected_cached_registry_does_not_log_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = tmp_path / "registry.json"
    config.write_text(json.dumps({MARKER: {"server": {"name": MARKER, "transport": MARKER}}}))
    ServerRegistry(config).load()
    assert MARKER not in caplog.text


@pytest.mark.parametrize(
    "body",
    [
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": MARKER}},
        {},
        [],
        None,
        {"jsonrpc": "2.0", "id": 1, "result": []},
        {**INIT, "id": 9},
        {**INIT, "result": {"serverInfo": MARKER}},
    ],
)
async def test_http_initialize_rejects_invalid_rpc(body: object) -> None:
    server = McpServer(
        name="fixture",
        transport="http",
        network_config=NetworkConfig(type="http", url="https://example.com/mcp"),
    )
    with patch("mcp_manager.health.httpx.AsyncClient") as client_type:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = httpx.Response(200, content=json.dumps(body))
        client_type.return_value = client
        result = await HealthChecker().check(server)
    assert result.status != ServerStatus.HEALTHY
    assert MARKER not in (result.error_message or "")


@pytest.mark.parametrize(
    "response",
    [
        httpx.ReadTimeout(MARKER),
        httpx.ConnectError(MARKER),
        httpx.Response(200, json={"jsonrpc": "2.0", "id": 3, "result": {"tools": MARKER}}),
        httpx.Response(200, json=[]),
        httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 9, "result": {"tools": [{"name": "ok"}]}}
        ),
        httpx.Response(200, json={"jsonrpc": "2.0", "id": 3, "error": {"message": MARKER}}),
    ],
)
async def test_deep_failure_cannot_retain_healthy(response: object) -> None:
    server = McpServer(
        name="fixture",
        transport="http",
        network_config=NetworkConfig(type="http", url="https://example.com/mcp"),
    )
    with patch("mcp_manager.health.httpx.AsyncClient") as client_type:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.side_effect = [httpx.Response(200, json=INIT), response]
        client_type.return_value = client
        result = await HealthChecker(deep=True).check(server)
    assert result.status != ServerStatus.HEALTHY
    assert MARKER not in (result.error_message or "")


async def test_valid_http_deep_result_remains_healthy() -> None:
    server = McpServer(
        name="fixture",
        transport="http",
        network_config=NetworkConfig(type="http", url="https://example.com/mcp"),
    )
    with patch("mcp_manager.health.httpx.AsyncClient") as client_type:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.side_effect = [
            httpx.Response(200, json=INIT),
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "result": {"tools": [{"name": "fixture"}]},
                },
            ),
        ]
        client_type.return_value = client
        result = await HealthChecker(deep=True).check(server)
    assert result.status == ServerStatus.HEALTHY


def test_degraded_verification_preserves_config(tmp_path: Path) -> None:
    from mcp_manager.models import HealthResult

    config = tmp_path / ".mcp-manager.yml"
    original = "servers: {}\n"
    config.write_text(original)
    server = McpServer(
        name="fixture",
        transport="http",
        network_config=NetworkConfig(type="http", url="https://example.com/mcp"),
    )
    with (
        patch("mcp_manager.telemetry.track_command"),
        patch("mcp_manager.commands.registry_cmd._build_headers", return_value=None),
        patch("mcp_manager.commands.registry_cmd.fetch_remote_servers", return_value=[server]),
        patch("mcp_manager.registry_sync.HealthChecker.check_all", new_callable=AsyncMock) as check,
    ):
        check.return_value = [
            HealthResult(server_name="fixture", transport="http", status=ServerStatus.DEGRADED)
        ]
        result = CliRunner().invoke(
            registry_app, ["pull", "https://example.com/r", "-p", str(tmp_path), "--verify"]
        )
    assert result.exit_code == 1
    assert config.read_text() == original
    assert not config.with_suffix(".yml.mcp-manager-backup").exists()


def test_malformed_local_yaml_does_not_echo_credentials(tmp_path: Path) -> None:
    from mcp_manager.exceptions import WritebackError
    from mcp_manager.project_config import parse_project_config

    config = tmp_path / ".mcp-manager.yml"
    config.write_text(f"servers: [{MARKER}: broken")
    with pytest.raises(WritebackError) as error:
        parse_project_config(config)
    assert MARKER not in str(error.value)


def test_diff_does_not_print_authenticated_url(tmp_path: Path) -> None:
    config = tmp_path / ".mcp-manager.yml"
    config.write_text("servers: {}\n")
    server = McpServer(
        name="fixture",
        transport="http",
        network_config=NetworkConfig(type="http", url="https://example.com/mcp"),
    )
    with (
        patch("mcp_manager.telemetry.track_command"),
        patch("mcp_manager.commands.registry_cmd._build_headers", return_value=None),
        patch("mcp_manager.commands.registry_cmd.fetch_remote_servers", return_value=[server]),
    ):
        result = CliRunner().invoke(
            registry_app, ["diff", f"https://example.com/r?token={MARKER}", "-p", str(tmp_path)]
        )
    assert result.exit_code == 0
    assert MARKER not in result.output

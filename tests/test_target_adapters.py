"""Tests for target-specific MCP configuration adapters."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_manager.adapters.codex import CodexTargetAdapter
from mcp_manager.adapters.json_target import JsonTargetAdapter
from mcp_manager.discovery import ConfigDiscovery
from mcp_manager.exceptions import DiscoveryError, WritebackError
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType
from mcp_manager.writeback import ConfigWriteback

CODEX_CONFIG = """\
model = "gpt-5.6-sol"

# This comment and unrelated setting must survive write-back.
[mcp_servers.arete-context]
command = "/opt/arete/bin/python"
args = ["/opt/arete/server.py"]
env_vars = ["ARETE_NOTES_DIR"]
enabled = true
required = false
enabled_tools = ["search_notes"]
disabled_tools = ["write_note"]
default_tools_approval_mode = "writes"
startup_timeout_sec = 20

[mcp_servers.arete-context.env]
MODE = "readonly"

[mcp_servers.arete-context.tools.search_notes]
approval_mode = "approve"

[mcp_servers.remote]
url = "https://mcp.example.com/mcp"
auth = "oauth"
bearer_token_env_var = "MCP_TOKEN"

[mcp_servers.remote.http_headers]
X-Region = "west"

[mcp_servers.remote.env_http_headers]
X-API-Key = "MCP_API_KEY"
"""


@pytest.fixture
def codex_adapter(tmp_path: Path) -> CodexTargetAdapter:
    return CodexTargetAdapter(
        user_path=tmp_path / "config.toml",
        project_path=Path(".codex/config.toml"),
    )


class TestCodexAdapter:
    def test_parses_stdio_policy_and_extensions(
        self, codex_adapter: CodexTargetAdapter, tmp_path: Path
    ) -> None:
        servers = codex_adapter.parse(CODEX_CONFIG, source_path=tmp_path / "config.toml")

        context = next(server for server in servers if server.name == "arete-context")
        assert context.transport == TransportType.STDIO
        assert context.stdio_config is not None
        assert context.stdio_config.env == {"MODE": "readonly"}
        assert context.stdio_config.env_vars == ["ARETE_NOTES_DIR"]
        assert context.enabled is True
        assert context.required is False
        assert context.enabled_tools == ["search_notes"]
        assert context.disabled_tools == ["write_note"]
        assert context.default_tools_approval_mode == "writes"
        assert context.tool_approval_modes == {"search_notes": "approve"}
        assert context.startup_timeout_sec == 20

    def test_parses_http_auth_and_header_refs(
        self, codex_adapter: CodexTargetAdapter, tmp_path: Path
    ) -> None:
        servers = codex_adapter.parse(CODEX_CONFIG, source_path=tmp_path / "config.toml")

        remote = next(server for server in servers if server.name == "remote")
        assert remote.transport == TransportType.HTTP
        assert remote.network_config is not None
        assert remote.network_config.auth == "oauth"
        assert remote.network_config.bearer_token_env_var == "MCP_TOKEN"
        assert remote.network_config.headers == {"X-Region": "west"}
        assert remote.network_config.env_headers == {"X-API-Key": "MCP_API_KEY"}

    def test_round_trip_preserves_comments_root_keys_and_codex_extensions(
        self, codex_adapter: CodexTargetAdapter, tmp_path: Path
    ) -> None:
        servers = codex_adapter.parse(CODEX_CONFIG, source_path=tmp_path / "config.toml")
        rendered = codex_adapter.render(CODEX_CONFIG, servers)

        assert 'model = "gpt-5.6-sol"' in rendered
        assert "# This comment and unrelated setting must survive write-back." in rendered
        assert "startup_timeout_sec = 20" in rendered
        reparsed = codex_adapter.parse(rendered, source_path=tmp_path / "config.toml")
        assert {server.name for server in reparsed} == {"arete-context", "remote"}

    def test_remove_preserves_unrelated_config(self, codex_adapter: CodexTargetAdapter) -> None:
        rendered, removed = codex_adapter.remove(CODEX_CONFIG, {"remote"})

        assert removed == ["remote"]
        assert 'model = "gpt-5.6-sol"' in rendered
        assert "[mcp_servers.arete-context]" in rendered
        assert "[mcp_servers.remote]" not in rendered

    def test_invalid_toml_raises(self, codex_adapter: CodexTargetAdapter, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError, match="Cannot parse"):
            codex_adapter.parse("[broken", source_path=tmp_path / "config.toml")

    def test_strict_parse_rejects_invalid_codex_values(
        self, codex_adapter: CodexTargetAdapter, tmp_path: Path
    ) -> None:
        invalid = """\
[mcp_servers.broken]
command = "python"
required = "yes"
"""

        with pytest.raises(DiscoveryError, match="required.*boolean"):
            codex_adapter.parse(
                invalid,
                source_path=tmp_path / "config.toml",
                strict=True,
            )

    def test_project_path_resolution(
        self, codex_adapter: CodexTargetAdapter, tmp_path: Path
    ) -> None:
        assert codex_adapter.resolve_path(scope="project", project_dir=tmp_path) == (
            tmp_path / ".codex/config.toml"
        )

    def test_rejects_sse_translation(self, codex_adapter: CodexTargetAdapter) -> None:
        server = McpServer(
            name="legacy",
            transport=TransportType.SSE,
            network_config=NetworkConfig(type="sse", url="https://example.com/sse"),
        )
        with pytest.raises(WritebackError, match="does not support transport"):
            codex_adapter.validate_servers([server])


class TestJsonAdapter:
    def test_round_trip(self, tmp_path: Path) -> None:
        adapter = JsonTargetAdapter(
            name="cursor",
            user_path=tmp_path / "mcp.json",
            wrapper_key="mcpServers",
        )
        existing = json.dumps({"theme": "dark", "mcpServers": {}})
        server = McpServer(
            name="local",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="python", args=["server.py"]),
        )

        rendered = adapter.render(existing, [server])
        parsed = adapter.parse(rendered, source_path=tmp_path / "mcp.json")

        assert json.loads(rendered)["theme"] == "dark"
        assert parsed[0].stdio_config is not None
        assert parsed[0].stdio_config.args == ["server.py"]

    def test_warns_when_codex_policy_would_be_dropped(self, tmp_path: Path) -> None:
        adapter = JsonTargetAdapter(
            name="cursor",
            user_path=tmp_path / "mcp.json",
            wrapper_key="mcpServers",
        )
        server = McpServer(
            name="guarded",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="python"),
            enabled_tools=["read"],
            default_tools_approval_mode="writes",
        )

        warnings = adapter.translation_warnings([server])
        assert len(warnings) == 2

    def test_warns_for_all_lossy_codex_fields(self, tmp_path: Path) -> None:
        adapter = JsonTargetAdapter(
            name="cursor",
            user_path=tmp_path / "mcp.json",
            wrapper_key="mcpServers",
        )
        server = McpServer(
            name="guarded",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="python", env_vars=["TOKEN"]),
            enabled=False,
            required=True,
            startup_timeout_sec=10,
        )

        warnings = adapter.translation_warnings([server])

        assert any("enabled/required" in warning for warning in warnings)
        assert any("inherited environment-variable" in warning for warning in warnings)
        assert any("timeout" in warning for warning in warnings)

    def test_round_trip_preserves_target_extensions(self, tmp_path: Path) -> None:
        adapter = JsonTargetAdapter(
            name="claude-code",
            user_path=tmp_path / "mcp.json",
            wrapper_key="mcpServers",
        )
        existing = json.dumps(
            {
                "mcpServers": {
                    "local": {
                        "command": "python",
                        "args": ["server.py"],
                        "alwaysLoad": True,
                    }
                }
            }
        )

        servers = adapter.parse(existing, source_path=tmp_path / "mcp.json")
        rendered = json.loads(adapter.render(existing, servers))

        assert rendered["mcpServers"]["local"]["alwaysLoad"] is True

    def test_windsurf_server_url_is_http(self, tmp_path: Path) -> None:
        adapter = JsonTargetAdapter(
            name="windsurf",
            user_path=tmp_path / "mcp.json",
            wrapper_key="mcpServers",
            implicit_url_transport="http",
        )
        config = json.dumps({"mcpServers": {"remote": {"serverUrl": "https://example.com/mcp"}}})

        server = adapter.parse(config, source_path=tmp_path / "mcp.json")[0]

        assert server.transport == TransportType.HTTP

    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            ("claude-code", ".mcp.json"),
            ("cursor", ".cursor/mcp.json"),
            ("codex", ".codex/config.toml"),
        ],
    )
    def test_supported_project_paths(self, target: str, expected: str, tmp_path: Path) -> None:
        writeback = ConfigWriteback()

        assert (
            writeback.get_config_path(
                target,
                scope="project",
                project_dir=tmp_path,
            )
            == tmp_path / expected
        )

    def test_windsurf_project_scope_is_rejected(self, tmp_path: Path) -> None:
        writeback = ConfigWriteback()

        with pytest.raises(WritebackError, match="does not support project-scoped"):
            writeback.get_config_path("windsurf", scope="project", project_dir=tmp_path)


class TestCodexDiscoveryAndWriteback:
    def test_discovery_uses_codex_adapter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = tmp_path / "config.toml"
        config.write_text(CODEX_CONFIG)
        monkeypatch.setattr(
            "mcp_manager.discovery.IDE_CONFIG_PATHS",
            [("codex", str(config), "mcp_servers")],
        )

        servers = ConfigDiscovery().discover_tool("codex")
        assert {server.name for server in servers} == {"arete-context", "remote"}

    def test_writeback_creates_backup_and_preserves_toml(self, tmp_path: Path) -> None:
        config = tmp_path / "config.toml"
        config.write_text(CODEX_CONFIG)
        writeback = ConfigWriteback()
        writeback._ide_configs["codex"] = (config, "mcp_servers")
        server = McpServer(
            name="new-server",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="python", args=["server.py"]),
        )

        writeback.write_servers("codex", [server])

        assert config.with_suffix(".toml.mcp-manager-backup").exists()
        assert "[mcp_servers.new-server]" in config.read_text()
        assert 'model = "gpt-5.6-sol"' in config.read_text()

    def test_project_scoped_write(self, tmp_path: Path) -> None:
        writeback = ConfigWriteback()
        server = McpServer(
            name="project-server",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="python"),
        )

        path = writeback.write_servers(
            "codex",
            [server],
            create_if_missing=True,
            scope="project",
            project_dir=tmp_path,
        )

        assert path == tmp_path / ".codex/config.toml"
        assert "[mcp_servers.project-server]" in path.read_text()

    @pytest.mark.parametrize(
        ("target", "relative_path"),
        [
            ("claude-code", Path(".mcp.json")),
            ("cursor", Path(".cursor/mcp.json")),
        ],
    )
    def test_json_project_scoped_write(
        self,
        target: str,
        relative_path: Path,
        tmp_path: Path,
    ) -> None:
        writeback = ConfigWriteback()
        server = McpServer(
            name="project-server",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="python"),
        )

        path = writeback.write_servers(
            target,
            [server],
            create_if_missing=True,
            scope="project",
            project_dir=tmp_path,
        )

        assert path == tmp_path / relative_path
        assert json.loads(path.read_text())["mcpServers"]["project-server"]["command"] == "python"

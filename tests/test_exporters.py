"""Tests for mcp_manager.exporters."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mcp_manager.exceptions import ExportError
from mcp_manager.exporters import export_servers, import_servers
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType


def _sample_servers() -> list[McpServer]:
    return [
        McpServer(
            name="filesystem",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="npx", args=["-y", "server-fs"]),
            source_tool="claude-code",
        ),
        McpServer(
            name="slack",
            transport=TransportType.HTTP,
            network_config=NetworkConfig(
                type="http",
                url="https://mcp.slack.com/mcp",
                headers={"Authorization": "Bearer token"},
            ),
            source_tool="cursor",
        ),
        McpServer(
            name="asana",
            transport=TransportType.SSE,
            network_config=NetworkConfig(type="sse", url="https://mcp.asana.com/sse"),
            source_tool="cursor",
        ),
    ]


class TestExportYaml:
    def test_creates_file(self, tmp_path: Path) -> None:
        out = tmp_path / "export.yaml"
        export_servers(_sample_servers(), out)
        assert out.is_file()

    def test_yaml_structure(self, tmp_path: Path) -> None:
        out = tmp_path / "export.yaml"
        export_servers(_sample_servers(), out)

        data = yaml.safe_load(out.read_text())
        assert data["version"] == "1"
        assert "metadata" in data
        assert "servers" in data
        assert "filesystem" in data["servers"]
        assert data["servers"]["filesystem"]["command"] == "npx"

    def test_network_server_format(self, tmp_path: Path) -> None:
        out = tmp_path / "export.yaml"
        export_servers(_sample_servers(), out)

        data = yaml.safe_load(out.read_text())
        slack = data["servers"]["slack"]
        assert slack["type"] == "http"
        assert slack["url"] == "https://mcp.slack.com/mcp"
        assert "Authorization" in slack["headers"]

    def test_empty_servers(self, tmp_path: Path) -> None:
        out = tmp_path / "export.yaml"
        export_servers([], out)
        data = yaml.safe_load(out.read_text())
        assert data["servers"] == {}

    def test_os_error_on_write(self, tmp_path: Path) -> None:
        """Export to a directory instead of file raises ExportError."""
        out = tmp_path / "is_a_dir"
        out.mkdir()
        with pytest.raises(ExportError, match="Failed to write"):
            export_servers([], out)


class TestExportJson:
    def test_creates_file(self, tmp_path: Path) -> None:
        out = tmp_path / "export.json"
        export_servers(_sample_servers(), out, fmt="json")
        assert out.is_file()

    def test_valid_json(self, tmp_path: Path) -> None:
        import json

        out = tmp_path / "export.json"
        export_servers(_sample_servers(), out, fmt="json")
        data = json.loads(out.read_text())
        assert "filesystem" in data["servers"]


class TestImport:
    def test_round_trip_yaml(self, tmp_path: Path) -> None:
        out = tmp_path / "config.yaml"
        original = _sample_servers()
        export_servers(original, out)

        imported = import_servers(out)
        assert len(imported) == len(original)
        names = {s.name for s in imported}
        assert names == {"filesystem", "slack", "asana"}

    def test_round_trip_json(self, tmp_path: Path) -> None:
        out = tmp_path / "config.json"
        export_servers(_sample_servers(), out, fmt="json")

        imported = import_servers(out)
        assert len(imported) == 3

    def test_preserves_stdio_config(self, tmp_path: Path) -> None:
        out = tmp_path / "config.yaml"
        export_servers(_sample_servers(), out)

        imported = import_servers(out)
        fs = next(s for s in imported if s.name == "filesystem")
        assert fs.transport == TransportType.STDIO
        assert fs.stdio_config is not None
        assert fs.stdio_config.command == "npx"
        assert fs.stdio_config.args == ["-y", "server-fs"]

    def test_preserves_network_config(self, tmp_path: Path) -> None:
        out = tmp_path / "config.yaml"
        export_servers(_sample_servers(), out)

        imported = import_servers(out)
        slack = next(s for s in imported if s.name == "slack")
        assert slack.transport == TransportType.HTTP
        assert slack.network_config is not None
        assert slack.network_config.url == "https://mcp.slack.com/mcp"

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ExportError, match="File not found"):
            import_servers(tmp_path / "nope.yaml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text(": : :\n  - invalid: [", encoding="utf-8")
        with pytest.raises(ExportError, match="Failed to parse"):
            import_servers(f)

    def test_non_dict_root(self, tmp_path: Path) -> None:
        f = tmp_path / "list.yaml"
        f.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ExportError, match="must be a YAML/JSON object"):
            import_servers(f)

    def test_import_source_tool_is_import(self, tmp_path: Path) -> None:
        out = tmp_path / "config.yaml"
        export_servers(_sample_servers(), out)

        imported = import_servers(out)
        for s in imported:
            assert s.source_tool == "import"

    def test_import_skips_non_dict_entries(self, tmp_path: Path) -> None:
        f = tmp_path / "mixed.yaml"
        f.write_text(
            yaml.dump(
                {
                    "version": "1",
                    "servers": {
                        "good": {"command": "npx"},
                        "bad": "not a dict",
                        "also_bad": ["list"],
                    },
                }
            ),
            encoding="utf-8",
        )
        imported = import_servers(f)
        assert len(imported) == 1
        assert imported[0].name == "good"

    def test_import_skips_invalid_server(self, tmp_path: Path) -> None:
        f = tmp_path / "partial.yaml"
        f.write_text(
            yaml.dump(
                {
                    "version": "1",
                    "servers": {
                        "good": {"command": "npx"},
                        "bad": {"command": "npx", "args": None},
                    },
                }
            ),
            encoding="utf-8",
        )
        imported = import_servers(f)
        assert len(imported) == 1
        assert imported[0].name == "good"

    def test_serialize_empty_server(self) -> None:
        """Server with no config serializes to empty dict."""
        from mcp_manager.exporters import _serialize_server

        server = McpServer(name="orphan", transport=TransportType.STDIO)
        result = _serialize_server(server)
        assert result == {}

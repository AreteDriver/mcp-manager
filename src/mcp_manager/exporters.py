"""YAML/JSON export and import for MCP server configurations."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from mcp_manager.exceptions import ExportError
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType

logger = logging.getLogger(__name__)


def export_servers(
    servers: list[McpServer],
    path: Path,
    *,
    fmt: str = "yaml",
) -> None:
    """Export servers to a portable YAML or JSON file."""
    data: dict[str, Any] = {
        "version": "1",
        "metadata": {
            "exported_at": datetime.now(UTC).isoformat(),
            "tool": "mcp-manager",
        },
        "servers": {s.name: _serialize_server(s) for s in servers},
    }

    try:
        if fmt == "json":
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        else:
            yaml_text = yaml.dump(data, default_flow_style=False, sort_keys=False)
            path.write_text(yaml_text, encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"Failed to write export file: {exc}") from exc


def import_servers(path: Path) -> list[McpServer]:
    """Import servers from a YAML or JSON file."""
    if not path.is_file():
        raise ExportError(f"File not found: {path}")

    text = path.read_text(encoding="utf-8")

    try:
        raw = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ExportError(f"Failed to parse {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ExportError("Import file must be a YAML/JSON object")

    servers_dict = raw.get("servers", raw)
    if not isinstance(servers_dict, dict):
        raise ExportError("No servers found in import file")

    results: list[McpServer] = []
    for name, config in servers_dict.items():
        if not isinstance(config, dict):
            logger.warning("Skipping non-dict entry: %r", name)
            continue
        try:
            results.append(_deserialize_server(name, config))
        except Exception as exc:
            logger.warning("Failed to import server %r: %s", name, exc)

    return results


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_server(server: McpServer) -> dict[str, Any]:
    """Convert McpServer to portable dict (native MCP config format)."""
    if server.stdio_config:
        result: dict[str, Any] = {"command": server.stdio_config.command}
        if server.stdio_config.args:
            result["args"] = server.stdio_config.args
        if server.stdio_config.env:
            result["env"] = server.stdio_config.env
        return result

    if server.network_config:
        result = {
            "type": server.network_config.type,
            "url": server.network_config.url,
        }
        if server.network_config.headers:
            result["headers"] = server.network_config.headers
        return result

    return {}


def _deserialize_server(name: str, config: dict[str, Any]) -> McpServer:
    """Convert a portable dict back to McpServer."""
    if "command" in config:
        return McpServer(
            name=name,
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(
                command=str(config["command"]),
                args=[str(a) for a in config.get("args", [])],
                env={str(k): str(v) for k, v in config.get("env", {}).items()},
            ),
            source_tool="import",
        )

    explicit_type = str(config.get("type", "sse")).lower()
    url = str(config.get("url", ""))
    if not url:
        raise ExportError(f"Server {name!r} has no command or url")

    transport = TransportType.SSE if explicit_type == "sse" else TransportType.HTTP
    return McpServer(
        name=name,
        transport=transport,
        network_config=NetworkConfig(
            type=transport.value,  # type: ignore[arg-type]
            url=url,
            headers={str(k): str(v) for k, v in config.get("headers", {}).items()},
        ),
        source_tool="import",
    )

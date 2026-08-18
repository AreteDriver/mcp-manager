"""Shared mapping helpers for client configuration adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp_manager.exceptions import DiscoveryError, WritebackError
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType

_JSON_TRANSPORT_KEYS = {
    "command",
    "args",
    "env",
    "cwd",
    "type",
    "url",
    "serverUrl",
    "headers",
}


def classify_json_transport(config: dict[str, Any]) -> TransportType:
    """Classify the transport used by a JSON-style client entry."""
    if "command" in config:
        return TransportType.STDIO

    explicit_type = str(config.get("type", "")).lower()
    if explicit_type == "sse":
        return TransportType.SSE
    if explicit_type in {"http", "streamable-http"}:
        return TransportType.HTTP
    if "serverUrl" in config:
        return TransportType.HTTP
    if "url" in config:
        return TransportType.SSE
    return TransportType.STDIO


def server_from_json_mapping(
    name: str,
    config: dict[str, Any],
    *,
    source_tool: str,
    source_path: Path,
) -> McpServer:
    """Build a canonical server from a JSON-style client entry."""
    transport = classify_json_transport(config)
    if transport == TransportType.STDIO:
        command = config.get("command", "")
        if not command:
            raise DiscoveryError(f"stdio server {name!r} has no command")
        return McpServer(
            name=name,
            transport=transport,
            stdio_config=StdioConfig(
                command=str(command),
                args=_json_string_list(config, "args"),
                env=_json_string_dict(config, "env"),
                cwd=str(config["cwd"]) if config.get("cwd") else None,
            ),
            source_tool=source_tool,
            source_path=source_path,
            extensions={source_tool: _json_extensions(config)},
        )

    url = config.get("serverUrl") or config.get("url", "")
    if not url:
        raise DiscoveryError(f"{transport} server {name!r} has no url")
    return McpServer(
        name=name,
        transport=transport,
        network_config=NetworkConfig(
            type=transport.value,  # type: ignore[arg-type]
            url=str(url),
            headers=_json_string_dict(config, "headers"),
        ),
        source_tool=source_tool,
        source_path=source_path,
        extensions={source_tool: _json_extensions(config)},
    )


def server_to_json_mapping(
    server: McpServer,
    *,
    target_name: str | None = None,
) -> dict[str, Any]:
    """Convert a canonical server to the common JSON client representation."""
    raw_extensions = server.extensions.get(target_name or "", {})
    result: dict[str, Any] = dict(raw_extensions) if isinstance(raw_extensions, dict) else {}
    for key in _JSON_TRANSPORT_KEYS:
        result.pop(key, None)

    if server.transport == TransportType.STDIO and server.stdio_config:
        result["command"] = server.stdio_config.command
        if server.stdio_config.args:
            result["args"] = server.stdio_config.args
        if server.stdio_config.env:
            result["env"] = server.stdio_config.env
        if server.stdio_config.cwd:
            result["cwd"] = server.stdio_config.cwd
        return result

    if server.network_config:
        result["type"] = server.network_config.type
        result["url"] = server.network_config.url
        if server.network_config.headers:
            result["headers"] = server.network_config.headers
        return result

    raise WritebackError(f"Server {server.name!r} has no valid transport config")


def _json_extensions(config: dict[str, Any]) -> dict[str, Any]:
    """Return target-native fields that are not part of the canonical transport."""
    return {key: value for key, value in config.items() if key not in _JSON_TRANSPORT_KEYS}


def _json_string_list(config: dict[str, Any], key: str) -> list[str]:
    value = config.get(key, [])
    if not isinstance(value, list):
        raise DiscoveryError(f"server field {key!r} must be a list")
    return [str(item) for item in value]


def _json_string_dict(config: dict[str, Any], key: str) -> dict[str, str]:
    value = config.get(key, {})
    if not isinstance(value, dict):
        raise DiscoveryError(f"server field {key!r} must be an object")
    return {str(item_key): str(item_value) for item_key, item_value in value.items()}

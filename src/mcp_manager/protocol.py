"""MCP JSON-RPC 2.0 protocol helpers."""

from __future__ import annotations

import json
from typing import Any

from mcp_manager.config import (
    MCP_CLIENT_NAME,
    MCP_CLIENT_VERSION,
    MCP_LEGACY_PROTOCOL_VERSION,
    MCP_PROTOCOL_VERSION,
)
from mcp_manager.exceptions import ProtocolError


def build_initialize_request(request_id: int = 1) -> bytes:
    """Build a legacy JSON-RPC ``initialize`` request for fallback."""
    msg = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_LEGACY_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": MCP_CLIENT_NAME,
                "version": MCP_CLIENT_VERSION,
            },
        },
    }
    return json.dumps(msg).encode("utf-8") + b"\n"


def build_initialized_notification() -> bytes:
    """Build the ``notifications/initialized`` notification."""
    msg = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    return json.dumps(msg).encode("utf-8") + b"\n"


def build_ping_request(request_id: int = 2) -> bytes:
    """Build a JSON-RPC ``ping`` request."""
    msg = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "ping",
    }
    return json.dumps(msg).encode("utf-8") + b"\n"


def build_list_tools_request(request_id: int = 3) -> bytes:
    """Build a JSON-RPC ``tools/list`` request."""
    msg = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/list",
    }
    return json.dumps(msg).encode("utf-8") + b"\n"


def build_request_meta(protocol_version: str = MCP_PROTOCOL_VERSION) -> dict[str, Any]:
    """Build the self-describing request metadata required by modern MCP."""
    return {
        "io.modelcontextprotocol/protocolVersion": protocol_version,
        "io.modelcontextprotocol/clientInfo": {
            "name": MCP_CLIENT_NAME,
            "version": MCP_CLIENT_VERSION,
        },
        "io.modelcontextprotocol/clientCapabilities": {},
    }


def build_modern_request(
    method: str,
    *,
    request_id: int | str,
    params: dict[str, Any] | None = None,
    protocol_version: str = MCP_PROTOCOL_VERSION,
) -> dict[str, Any]:
    """Build a self-contained MCP 2026 request.

    Every request receives a fresh params mapping and request metadata. This
    avoids accidentally relying on transport-session state or mutating a
    caller-owned arguments dictionary.
    """
    request_params = dict(params or {})
    request_params["_meta"] = build_request_meta(protocol_version)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": request_params,
    }


def build_discover_request(request_id: int | str = "discover-1") -> dict[str, Any]:
    """Build the modern ``server/discover`` compatibility probe."""
    return build_modern_request("server/discover", request_id=request_id)


def build_modern_list_tools_request(request_id: int | str = 2) -> dict[str, Any]:
    """Build a modern, self-contained ``tools/list`` request."""
    return build_modern_request("tools/list", request_id=request_id)


def build_call_tool_request(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    request_id: int | str = 3,
) -> dict[str, Any]:
    """Build a modern, self-contained ``tools/call`` request."""
    return build_modern_request(
        "tools/call",
        request_id=request_id,
        params={"name": name, "arguments": dict(arguments or {})},
    )


def build_http_headers(
    method: str,
    *,
    name: str | None = None,
    base_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build required Streamable HTTP routing headers for a modern request."""
    headers = dict(base_headers or {})
    headers.update(
        {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
            "Mcp-Method": method,
        }
    )
    if name is not None:
        headers["Mcp-Name"] = name
    return headers


def extract_discovery_info(response: dict[str, Any]) -> dict[str, Any]:
    """Extract normalized metadata from a ``server/discover`` response."""
    result = response.get("result", {})
    if not isinstance(result, dict):
        return {}
    meta = result.get("_meta", {})
    if not isinstance(meta, dict):
        meta = {}
    server_info = meta.get("io.modelcontextprotocol/serverInfo", {})
    if not isinstance(server_info, dict):
        server_info = {}
    return {
        "supported_versions": result.get("supportedVersions", []),
        "protocol_version": MCP_PROTOCOL_VERSION,
        "server_name": server_info.get("name"),
        "server_version": server_info.get("version"),
        "capabilities": result.get("capabilities", {}),
        "instructions": result.get("instructions"),
        "ttl_ms": result.get("ttlMs"),
        "cache_scope": result.get("cacheScope"),
    }


def parse_jsonrpc_response(data: bytes) -> dict[str, Any]:
    """Parse a JSON-RPC response from raw bytes.

    Handles newline-delimited JSON (reads the first complete JSON object).
    Raises ``ProtocolError`` on malformed data.
    """
    text = data.decode("utf-8", errors="replace").strip()
    if not text:
        raise ProtocolError("Empty response")

    # Take the first line that looks like JSON.
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

    raise ProtocolError(f"No valid JSON-RPC response found in: {text[:200]}")


def extract_server_info(init_response: dict[str, Any]) -> dict[str, Any]:
    """Extract server metadata from an ``initialize`` response."""
    result = init_response.get("result", {})
    if not isinstance(result, dict):
        return {}
    return {
        "protocol_version": result.get("protocolVersion"),
        "server_name": result.get("serverInfo", {}).get("name"),
        "server_version": result.get("serverInfo", {}).get("version"),
        "capabilities": result.get("capabilities", {}),
    }

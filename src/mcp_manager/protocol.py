"""MCP JSON-RPC 2.0 protocol helpers."""

from __future__ import annotations

import json
from typing import Any

from mcp_manager.config import MCP_CLIENT_NAME, MCP_CLIENT_VERSION, MCP_PROTOCOL_VERSION
from mcp_manager.exceptions import ProtocolError


def build_initialize_request(request_id: int = 1) -> bytes:
    """Build a JSON-RPC ``initialize`` request."""
    msg = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
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

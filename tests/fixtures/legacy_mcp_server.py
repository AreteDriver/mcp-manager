"""Minimal handshake-era MCP server used to test SDK v2 fallback."""

from __future__ import annotations

import json
import sys
from typing import Any


def respond(request_id: Any, result: dict[str, Any]) -> None:
    print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}), flush=True)


for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    request_id = message.get("id")
    if method == "server/discover":
        print(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": "Method not found"},
                }
            ),
            flush=True,
        )
    elif method == "initialize":
        respond(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "legacy-fixture", "version": "1.0.0"},
            },
        )
    elif method == "tools/list":
        respond(
            request_id,
            {
                "tools": [
                    {
                        "name": "legacy_echo",
                        "description": "Return the supplied value.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                            "required": ["value"],
                        },
                    }
                ]
            },
        )
    elif method == "tools/call":
        value = message.get("params", {}).get("arguments", {}).get("value", "")
        respond(
            request_id,
            {"content": [{"type": "text", "text": value}], "isError": False},
        )
    elif request_id is not None:
        respond(request_id, {})

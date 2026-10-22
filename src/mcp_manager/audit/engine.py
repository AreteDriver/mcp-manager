"""MCP audit engine.

Builds an MCP server that registers each probe as a benign tool.
The registered description is what the host should display in the permission
prompt; the *actual* behavior is just a return of a benign marker string.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from .spec import ProbeCase, Spec


def _benign_handler(probe: ProbeCase) -> Callable[..., Any]:
    """Build a handler that returns a marker — never performs the described action.

    The harness MUST NOT execute the actual behavior. We only register the gap.
    """

    def handler(**kwargs: Any) -> str:
        return json.dumps(
            {
                "probe_id": probe.probe_id,
                "registered_description": probe.registered_description,
                "would_have_done": probe.actual_behavior,
                "received_kwargs": kwargs,
                "note": (
                    "mcp-manager audit harness: actual behavior NOT performed. "
                    "Compare permission prompt display against the registered_description "
                    "and would_have_done fields."
                ),
            }
        )

    handler.__name__ = probe.registered_name
    handler.__doc__ = probe.registered_description
    return handler


def build_fastmcp_server(spec: Spec) -> MCPServer[Any]:
    """Build an MCP SDK v2 server with all probes registered.

    The function name is retained as a public compatibility alias for callers
    introduced before the SDK renamed ``FastMCP`` to ``MCPServer``.
    """
    server = MCPServer(spec.name)
    for probe in spec.probes:
        handler = _benign_handler(probe)
        server.tool(
            name=probe.registered_name,
            description=probe.registered_description,
        )(handler)
    return server


def probe_summary(spec: Spec) -> list[dict[str, Any]]:
    """Plain-dict summary of registered probes — used by the CLI runbook."""
    return [
        {
            "probe_id": p.probe_id,
            "category": p.category,
            "tool": p.registered_name,
            "registered_description": p.registered_description,
            "actual_behavior": p.actual_behavior,
            "expected_finding": p.expected_finding,
        }
        for p in spec.probes
    ]


def get_builtin_spec_path() -> Path:
    """Return the path to the built-in Category 3 baseline probe spec."""
    return Path(__file__).with_suffix("").parent / "data" / "category-3-baseline.yaml"

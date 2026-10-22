"""MCP 2026-07-28 wire compatibility and stateless routing tests."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from starlette.testclient import TestClient

from mcp_manager.protocol import (
    build_call_tool_request,
    build_discover_request,
    build_http_headers,
    build_modern_list_tools_request,
    extract_discovery_info,
)


def _instance(label: str) -> MCPServer[None]:
    server: MCPServer[None] = MCPServer(
        f"fixture-{label}",
        version="1.0.0",
    )

    @server.tool(name="instance_id", description="Return this stateless instance identifier.")
    def instance_id() -> str:
        return label

    return server


def _post(client: TestClient, body: dict[str, object], *, name: str | None = None):
    method = str(body["method"])
    return client.post(
        "/mcp",
        json=body,
        headers=build_http_headers(method, name=name),
    )


def test_modern_requests_route_across_independent_server_instances() -> None:
    first = _instance("a")
    second = _instance("b")
    first_app = first.streamable_http_app(
        json_response=True,
        stateless_http=True,
        host="testserver",
    )
    second_app = second.streamable_http_app(
        json_response=True,
        stateless_http=True,
        host="testserver",
    )

    with TestClient(first_app) as first_client, TestClient(second_app) as second_client:
        discover = _post(first_client, build_discover_request())
        listed = _post(second_client, build_modern_list_tools_request())
        repeated = _post(first_client, build_modern_list_tools_request(request_id=3))
        called = _post(
            second_client,
            build_call_tool_request("instance_id", request_id=4),
            name="instance_id",
        )

    assert discover.status_code == 200
    assert listed.status_code == 200
    assert repeated.status_code == 200
    assert called.status_code == 200
    assert discover.headers.get("Mcp-Session-Id") is None
    assert listed.headers.get("Mcp-Session-Id") is None
    assert repeated.headers.get("Mcp-Session-Id") is None
    assert called.headers.get("Mcp-Session-Id") is None

    discovery = extract_discovery_info(discover.json())
    assert discovery["supported_versions"] == ["2026-07-28"]
    assert discovery["server_name"] == "fixture-a"
    assert listed.json()["result"]["tools"] == repeated.json()["result"]["tools"]
    assert called.json()["result"]["content"][0]["text"] == "b"


def test_modern_http_headers_are_self_describing_and_session_free() -> None:
    headers = build_http_headers("tools/call", name="instance_id")

    assert headers["MCP-Protocol-Version"] == "2026-07-28"
    assert headers["Mcp-Method"] == "tools/call"
    assert headers["Mcp-Name"] == "instance_id"
    assert "Mcp-Session-Id" not in headers

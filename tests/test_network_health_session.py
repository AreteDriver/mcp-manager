"""Exercise the real SDK session against a deterministic HTTP transport."""

import json
from unittest.mock import patch

import httpx2
import pytest

from mcp_manager.health import HealthChecker
from mcp_manager.models import McpServer, NetworkConfig, ServerStatus

INFO = {
    "protocolVersion": "2024-11-05",
    "capabilities": {"tools": {}},
    "serverInfo": {"name": "fixture", "version": "1"},
}
TOOLS = [{"name": "fixture", "inputSchema": {"type": "object"}}]


async def check_session(*, init=INFO, tools=TOOLS, failure=None, deep=True, pages=None):
    calls = []

    def handler(request):
        if request.method == "GET":
            return httpx2.Response(405)
        if request.method == "DELETE":
            return httpx2.Response(200)
        body = json.loads(request.content)
        method = body["method"]
        calls.append(method)
        if method == "server/discover":
            return httpx2.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "error": {"code": -32601, "message": "legacy"},
                },
            )
        if method == "initialize":
            return httpx2.Response(
                200,
                headers={"mcp-session-id": "fixture-session"},
                json={"jsonrpc": "2.0", "id": body["id"], "result": init},
            )
        assert request.headers.get("mcp-session-id") == "fixture-session"
        if method == "notifications/initialized":
            return httpx2.Response(202)
        if method == failure:
            return httpx2.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "error": {"code": -32603, "message": "synthetic-secret"},
                },
            )
        result = {"tools": tools} if method == "tools/list" else {}
        if method == "tools/list" and pages is not None:
            result = pages[body.get("params", {}).get("cursor")]
        return httpx2.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    original = httpx2.AsyncClient

    def factory(**kwargs):
        return original(transport=httpx2.MockTransport(handler), **kwargs)

    server = McpServer(
        name="fixture",
        transport="http",
        network_config=NetworkConfig(type="http", url="https://example.com/mcp"),
    )
    with patch("mcp_manager.compatibility.httpx2.AsyncClient", side_effect=factory):
        result = await HealthChecker(timeout=2, deep=deep).check(server)
    assert "synthetic-secret" not in (result.error_message or "")
    return result, calls


async def test_stateful_http_session_handshake_ping_and_tools():
    result, calls = await check_session()
    assert result.status is ServerStatus.HEALTHY
    assert result.server_info == {
        "protocol_version": "2024-11-05",
        "server_name": "fixture",
        "server_version": "1",
        "capabilities": {"tools": {}},
        "tool_count": 1,
    }
    assert calls == [
        "server/discover",
        "initialize",
        "notifications/initialized",
        "ping",
        "tools/list",
    ]


@pytest.mark.parametrize(
    "info",
    [
        {},
        {**INFO, "serverInfo": {}},
        {**INFO, "serverInfo": {"name": "only"}},
        {**INFO, "capabilities": []},
    ],
)
async def test_invalid_initialize_cannot_be_healthy(info):
    result, _ = await check_session(init=info)
    assert result.status is not ServerStatus.HEALTHY


@pytest.mark.parametrize(
    "tools", [[{"name": "missing-schema"}], [{"name": "bad-schema", "inputSchema": []}], [None]]
)
async def test_invalid_tool_schema_cannot_be_healthy(tools):
    result, _ = await check_session(tools=tools)
    assert result.status is not ServerStatus.HEALTHY


@pytest.mark.parametrize("method", ["ping", "tools/list"])
async def test_protocol_failure_cannot_be_healthy(method):
    result, _ = await check_session(failure=method)
    assert result.status is not ServerStatus.HEALTHY


async def test_valid_empty_tool_list_is_degraded():
    result, _ = await check_session(tools=[])
    assert result.status is ServerStatus.DEGRADED


async def test_shallow_check_negotiates_and_pings_without_listing():
    result, calls = await check_session(deep=False)
    assert result.status is ServerStatus.HEALTHY
    assert "ping" in calls and "tools/list" not in calls
    assert "tool_count" not in result.server_info


@pytest.mark.parametrize("invalid", [False, True, "payload", "endpoint"])
async def test_sse_uses_negotiated_message_endpoint_and_closes_stream(invalid, caplog):
    import asyncio

    caplog.set_level("DEBUG")
    queue = asyncio.Queue()
    calls = []
    closed = []

    class Events(httpx2.AsyncByteStream):
        async def __aiter__(self):
            if invalid == "endpoint":
                yield b"event: endpoint\ndata: https://evil.example/synthetic-secret\n\n"
                return
            yield b"event: endpoint\ndata: /messages?sessionId=fixture\n\n"
            while True:
                yield await queue.get()

        async def aclose(self):
            closed.append(True)

    async def handler(request):
        if request.method == "GET":
            assert request.url.path == "/sse"
            return httpx2.Response(
                200, headers={"content-type": "text/event-stream"}, stream=Events()
            )
        assert request.url.path == "/messages"
        body = json.loads(request.content)
        calls.append(body["method"])
        if "id" in body:
            result = (
                INFO
                if body["method"] == "initialize"
                else {"tools": TOOLS}
                if body["method"] == "tools/list"
                else {}
            )
            if invalid is True and body["method"] == "initialize":
                result = {}
            response = {"jsonrpc": "2.0", "id": body["id"], "result": result}
            if invalid == "payload":
                response = {"synthetic-secret": "not-a-json-rpc-message"}
            await queue.put(("event: message\ndata: " + json.dumps(response) + "\n\n").encode())
        return httpx2.Response(202)

    original = httpx2.AsyncClient

    def factory(**kwargs):
        return original(transport=httpx2.MockTransport(handler), **kwargs)

    server = McpServer(
        name="fixture",
        transport="sse",
        network_config=NetworkConfig(type="sse", url="https://example.com/sse"),
    )
    with patch("mcp_manager.compatibility.httpx2.AsyncClient", side_effect=factory):
        result = await HealthChecker(timeout=2, deep=True).check(server)
    assert (result.status is ServerStatus.HEALTHY) is (not invalid)
    assert closed
    assert "synthetic-secret" not in caplog.text
    if not invalid:
        assert calls == ["initialize", "notifications/initialized", "ping", "tools/list"]


async def test_network_count_includes_all_validated_pages():
    result, calls = await check_session(
        pages={
            None: {"tools": TOOLS, "nextCursor": "second"},
            "second": {"tools": [{"name": "other", "inputSchema": {"type": "object"}}]},
        }
    )
    assert result.status is ServerStatus.HEALTHY
    assert result.server_info["tool_count"] == 2
    assert calls.count("tools/list") == 2


@pytest.mark.parametrize(
    "second",
    [
        {"tools": TOOLS, "nextCursor": "second"},
        {"tools": [{"name": "invalid"}]},
        {"tools": [{"name": "", "inputSchema": {"type": "object"}}]},
        {"tools": TOOLS},
    ],
)
async def test_incomplete_network_listing_has_no_partial_count(second):
    result, _ = await check_session(
        pages={
            None: {"tools": TOOLS, "nextCursor": "second"},
            "second": second,
        }
    )
    assert result.status is not ServerStatus.HEALTHY
    assert "tool_count" not in result.server_info


async def test_network_pagination_budget_has_no_partial_count():
    with patch("mcp_manager.health.MAX_TOOL_PAGES", 1):
        result, calls = await check_session(
            pages={
                None: {"tools": TOOLS, "nextCursor": "second"},
            }
        )
    assert result.status is not ServerStatus.HEALTHY
    assert "tool_count" not in result.server_info
    assert calls.count("tools/list") == 1

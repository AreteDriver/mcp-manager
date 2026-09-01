"""Tests for mcp_manager.protocol."""

from __future__ import annotations

import json

import pytest

from mcp_manager.exceptions import ProtocolError
from mcp_manager.protocol import (
    build_discover_request,
    build_initialize_request,
    build_initialized_notification,
    build_list_tools_request,
    build_ping_request,
    extract_server_info,
    parse_jsonrpc_response,
)


class TestBuildInitializeRequest:
    def test_is_valid_jsonrpc(self) -> None:
        data = json.loads(build_initialize_request())
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["method"] == "initialize"
        assert "params" in data
        assert "clientInfo" in data["params"]
        assert data["params"]["protocolVersion"] == "2024-11-05"

    def test_custom_id(self) -> None:
        data = json.loads(build_initialize_request(request_id=42))
        assert data["id"] == 42

    def test_ends_with_newline(self) -> None:
        raw = build_initialize_request()
        assert raw.endswith(b"\n")


class TestBuildInitializedNotification:
    def test_is_valid_notification(self) -> None:
        data = json.loads(build_initialized_notification())
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "notifications/initialized"
        assert "id" not in data


class TestBuildPingRequest:
    def test_is_valid_jsonrpc(self) -> None:
        data = json.loads(build_ping_request())
        assert data["method"] == "ping"
        assert data["id"] == 2


class TestBuildListToolsRequest:
    def test_is_valid_jsonrpc(self) -> None:
        data = json.loads(build_list_tools_request())
        assert data["method"] == "tools/list"
        assert data["id"] == 3


class TestBuildDiscoverRequest:
    def test_is_self_describing(self) -> None:
        data = build_discover_request()
        meta = data["params"]["_meta"]
        assert data["method"] == "server/discover"
        assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
        assert meta["io.modelcontextprotocol/clientInfo"]["name"] == "mcp-manager"
        assert meta["io.modelcontextprotocol/clientCapabilities"] == {}


class TestParseJsonrpcResponse:
    def test_simple_response(self) -> None:
        raw = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}).encode()
        parsed = parse_jsonrpc_response(raw)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1

    def test_newline_delimited(self) -> None:
        line1 = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        line2 = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {}})
        raw = f"{line1}\n{line2}\n".encode()
        parsed = parse_jsonrpc_response(raw)
        assert parsed["id"] == 1  # Returns first

    def test_empty_raises(self) -> None:
        with pytest.raises(ProtocolError, match="Empty response"):
            parse_jsonrpc_response(b"")

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ProtocolError, match="No valid JSON-RPC"):
            parse_jsonrpc_response(b"not json at all\n")

    def test_skips_non_json_lines(self) -> None:
        raw = b"some log output\n" + json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}).encode()
        parsed = parse_jsonrpc_response(raw)
        assert parsed["id"] == 1


class TestExtractServerInfo:
    def test_full_response(self) -> None:
        response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "test-server", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        }
        info = extract_server_info(response)
        assert info["protocol_version"] == "2024-11-05"
        assert info["server_name"] == "test-server"
        assert info["server_version"] == "1.0.0"
        assert "tools" in info["capabilities"]

    def test_missing_result(self) -> None:
        info = extract_server_info({"jsonrpc": "2.0", "id": 1})
        assert info["protocol_version"] is None
        assert info["server_name"] is None

    def test_error_response(self) -> None:
        info = extract_server_info({"jsonrpc": "2.0", "id": 1, "error": {"code": -1}})
        assert info["protocol_version"] is None

    def test_non_dict_result(self) -> None:
        info = extract_server_info({"jsonrpc": "2.0", "id": 1, "result": "string"})
        assert info == {}

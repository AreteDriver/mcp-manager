"""Tests for mcp_manager.oauth2."""

from __future__ import annotations

import httpx
import pytest
import respx

from mcp_manager.exceptions import McpManagerError
from mcp_manager.oauth2 import (
    OAuth2DeviceFlow,
    _parse_token_response,
    discover_oauth2_endpoints,
)

# ---------------------------------------------------------------------------
# Device Flow
# ---------------------------------------------------------------------------


class TestDeviceFlow:
    """Tests for the OAuth2 device flow state machine."""

    @respx.mock
    def test_request_device_code_success(self) -> None:
        respx.post("https://reg.example.com/oauth/device/code").respond(
            200,
            json={
                "device_code": "dev_abc",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://reg.example.com/oauth/device",
                "expires_in": 1800,
                "interval": 5,
            },
        )
        client = OAuth2DeviceFlow(
            "https://reg.example.com/oauth/device/code",
            "https://reg.example.com/oauth/token",
        )
        resp = client.request_device_code()
        assert resp.device_code == "dev_abc"
        assert resp.user_code == "ABCD-EFGH"
        assert resp.interval == 5

    @respx.mock
    def test_request_device_code_error(self) -> None:
        respx.post("https://reg.example.com/oauth/device/code").respond(
            400,
            json={"error": "invalid_client", "error_description": "bad client"},
        )
        client = OAuth2DeviceFlow(
            "https://reg.example.com/oauth/device/code",
            "https://reg.example.com/oauth/token",
        )
        with pytest.raises(McpManagerError, match="Device authorization error"):
            client.request_device_code()

    @respx.mock
    def test_request_device_code_network_error(self) -> None:
        respx.post("https://reg.example.com/oauth/device/code").mock(
            side_effect=httpx.ConnectError("offline"),
        )
        client = OAuth2DeviceFlow(
            "https://reg.example.com/oauth/device/code",
            "https://reg.example.com/oauth/token",
        )
        with pytest.raises(McpManagerError, match="Device authorization request failed"):
            client.request_device_code()

    @respx.mock
    def test_poll_token_success(self) -> None:
        respx.post("https://reg.example.com/oauth/token").respond(
            200,
            json={
                "access_token": "gho_xxx",
                "token_type": "bearer",
                "expires_in": 28800,
                "refresh_token": "ghr_yyy",
            },
        )
        client = OAuth2DeviceFlow(
            "https://reg.example.com/oauth/device/code",
            "https://reg.example.com/oauth/token",
        )
        resp = client.poll_token("dev_abc", interval=0)
        assert resp.access_token == "gho_xxx"
        assert resp.refresh_token == "ghr_yyy"
        assert resp.expires_in == 28800

    @respx.mock
    def test_poll_token_pending_then_success(self) -> None:
        route = respx.post("https://reg.example.com/oauth/token")
        route.side_effect = [
            httpx.Response(200, json={"error": "authorization_pending"}),
            httpx.Response(
                200,
                json={"access_token": "gho_xxx", "token_type": "bearer", "expires_in": 3600},
            ),
        ]
        client = OAuth2DeviceFlow(
            "https://reg.example.com/oauth/device/code",
            "https://reg.example.com/oauth/token",
        )
        resp = client.poll_token("dev_abc", interval=0)
        assert resp.access_token == "gho_xxx"

    @respx.mock
    def test_poll_token_slow_down(self) -> None:
        route = respx.post("https://reg.example.com/oauth/token")
        route.side_effect = [
            httpx.Response(200, json={"error": "slow_down"}),
            httpx.Response(
                200,
                json={"access_token": "gho_xxx", "token_type": "bearer"},
            ),
        ]
        client = OAuth2DeviceFlow(
            "https://reg.example.com/oauth/device/code",
            "https://reg.example.com/oauth/token",
        )
        # interval=0 should still work after slow_down increases it
        resp = client.poll_token("dev_abc", interval=0)
        assert resp.access_token == "gho_xxx"

    @respx.mock
    def test_poll_token_access_denied(self) -> None:
        respx.post("https://reg.example.com/oauth/token").respond(
            200,
            json={"error": "access_denied"},
        )
        client = OAuth2DeviceFlow(
            "https://reg.example.com/oauth/device/code",
            "https://reg.example.com/oauth/token",
        )
        with pytest.raises(McpManagerError, match="access_denied"):
            client.poll_token("dev_abc", interval=0)

    @respx.mock
    def test_poll_token_expired(self) -> None:
        respx.post("https://reg.example.com/oauth/token").respond(
            200,
            json={"error": "expired_token"},
        )
        client = OAuth2DeviceFlow(
            "https://reg.example.com/oauth/device/code",
            "https://reg.example.com/oauth/token",
        )
        with pytest.raises(McpManagerError, match="expired_token"):
            client.poll_token("dev_abc", interval=0)

    @respx.mock
    def test_refresh_success(self) -> None:
        respx.post("https://reg.example.com/oauth/token").respond(
            200,
            json={
                "access_token": "gho_new",
                "token_type": "bearer",
                "expires_in": 28800,
            },
        )
        client = OAuth2DeviceFlow(
            "https://reg.example.com/oauth/device/code",
            "https://reg.example.com/oauth/token",
        )
        resp = client.refresh("ghr_old")
        assert resp.access_token == "gho_new"
        assert resp.refresh_token is None  # server didn't rotate

    @respx.mock
    def test_refresh_error(self) -> None:
        respx.post("https://reg.example.com/oauth/token").respond(
            400,
            json={"error": "invalid_grant"},
        )
        client = OAuth2DeviceFlow(
            "https://reg.example.com/oauth/device/code",
            "https://reg.example.com/oauth/token",
        )
        with pytest.raises(McpManagerError, match="invalid_grant"):
            client.refresh("ghr_old")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    """Tests for OAuth2 endpoint discovery."""

    @respx.mock
    def test_discover_from_manifest_json(self) -> None:
        manifest = {
            "servers": [],
            "auth": {
                "type": "oauth2",
                "device_authorization_endpoint": "https://reg.example.com/device",
                "token_endpoint": "https://reg.example.com/token",
                "revocation_endpoint": "https://reg.example.com/revoke",
            },
        }
        respx.get("https://reg.example.com/mcp.yaml").respond(
            200,
            json=manifest,
            headers={"content-type": "application/json"},
        )
        endpoints = discover_oauth2_endpoints("https://reg.example.com/mcp.yaml")
        assert endpoints is not None
        assert endpoints.device_authorization == "https://reg.example.com/device"
        assert endpoints.revocation == "https://reg.example.com/revoke"

    @respx.mock
    def test_discover_from_manifest_yaml(self) -> None:
        yaml_text = """
servers: []
auth:
  type: oauth2
  device_authorization_endpoint: https://reg.example.com/device
  token_endpoint: https://reg.example.com/token
"""
        respx.get("https://reg.example.com/mcp.yaml").respond(
            200,
            text=yaml_text,
            headers={"content-type": "application/yaml"},
        )
        endpoints = discover_oauth2_endpoints("https://reg.example.com/mcp.yaml")
        assert endpoints is not None
        assert endpoints.device_authorization == "https://reg.example.com/device"

    @respx.mock
    def test_discover_from_well_known(self) -> None:
        well_known = {
            "device_authorization_endpoint": "https://reg.example.com/device",
            "token_endpoint": "https://reg.example.com/token",
            "grant_types_supported": [
                "urn:ietf:params:oauth:grant-type:device_code",
            ],
        }
        respx.get("https://reg.example.com/.well-known/oauth-authorization-server").respond(
            200,
            json=well_known,
        )
        # No manifest auth block
        respx.get("https://reg.example.com/mcp.yaml").respond(404)

        endpoints = discover_oauth2_endpoints("https://reg.example.com/mcp.yaml")
        assert endpoints is not None
        assert endpoints.device_authorization == "https://reg.example.com/device"

    @respx.mock
    def test_discover_no_device_flow_grant(self) -> None:
        well_known = {
            "device_authorization_endpoint": "https://reg.example.com/device",
            "token_endpoint": "https://reg.example.com/token",
            "grant_types_supported": ["authorization_code"],
        }
        respx.get("https://reg.example.com/.well-known/oauth-authorization-server").respond(
            200,
            json=well_known,
        )
        respx.get("https://reg.example.com/mcp.yaml").respond(404)

        endpoints = discover_oauth2_endpoints("https://reg.example.com/mcp.yaml")
        assert endpoints is None

    @respx.mock
    def test_discover_nothing_found(self) -> None:
        respx.get("https://reg.example.com/mcp.yaml").respond(404)
        respx.get("https://reg.example.com/.well-known/oauth-authorization-server").respond(404)

        endpoints = discover_oauth2_endpoints("https://reg.example.com/mcp.yaml")
        assert endpoints is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_parse_token_response() -> None:
    data = {"access_token": "tok", "token_type": "bearer", "expires_in": 3600}
    resp = _parse_token_response(data)
    assert resp.access_token == "tok"
    assert resp.expires_in == 3600
    assert resp.refresh_token is None


def test_parse_token_response_missing_access_token() -> None:
    with pytest.raises(McpManagerError, match="missing access_token"):
        _parse_token_response({"token_type": "bearer"})

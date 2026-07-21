"""OAuth2 Device Flow client (RFC 8628) for registry authentication."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from mcp_manager.exceptions import McpManagerError

logger = logging.getLogger(__name__)

_DEFAULT_CLIENT_ID = "mcp-manager-cli"
_DEFAULT_SCOPE = "registry:read"
_DEFAULT_POLL_INTERVAL = 5
_DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


@dataclass(frozen=True)
class DeviceCodeResponse:
    """Response from the device authorization endpoint."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class TokenResponse:
    """Response from the token endpoint."""

    access_token: str
    token_type: str
    expires_in: int | None
    refresh_token: str | None


@dataclass(frozen=True)
class OAuth2Endpoints:
    """Discovered OAuth2 endpoints for a registry."""

    device_authorization: str
    token: str
    revocation: str | None = None


class OAuth2DeviceFlow:
    """OAuth2 Device Flow client per RFC 8628."""

    def __init__(
        self,
        device_auth_url: str,
        token_url: str,
        client_id: str = _DEFAULT_CLIENT_ID,
        scope: str = _DEFAULT_SCOPE,
    ) -> None:
        self.device_auth_url = device_auth_url
        self.token_url = token_url
        self.client_id = client_id
        self.scope = scope

    # ------------------------------------------------------------------
    # Device flow steps
    # ------------------------------------------------------------------

    def request_device_code(self) -> DeviceCodeResponse:
        """Step 1: Request a device and user code from the registry."""
        payload = {
            "client_id": self.client_id,
            "scope": self.scope,
        }
        try:
            resp = httpx.post(
                self.device_auth_url,
                data=payload,
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise McpManagerError(f"Device authorization request failed: {exc}") from exc

        data = _parse_json_response(resp)
        if "error" in data:
            raise McpManagerError(
                f"Device authorization error: {data.get('error_description', data['error'])}"
            )

        required = {"device_code", "user_code", "verification_uri", "expires_in"}
        missing = required - set(data)
        if missing:
            raise McpManagerError(f"Device authorization response missing fields: {missing}")

        return DeviceCodeResponse(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=data["verification_uri"],
            expires_in=data["expires_in"],
            interval=data.get("interval", _DEFAULT_POLL_INTERVAL),
        )

    def poll_token(self, device_code: str, interval: int) -> TokenResponse:
        """Step 4: Poll the token endpoint until the user authorizes or the code expires.

        Returns the token response on success.

        Raises:
            McpManagerError: on terminal errors (denied, expired, etc.).
        """
        payload = {
            "grant_type": _DEVICE_CODE_GRANT,
            "device_code": device_code,
            "client_id": self.client_id,
        }
        start = time.time()
        current_interval = interval

        while True:
            time.sleep(current_interval)

            if time.time() - start > 1800:  # hard ceiling; real expiry comes from server
                raise McpManagerError("Device code polling timed out (30 min ceiling).")

            try:
                resp = httpx.post(self.token_url, data=payload, timeout=30)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise McpManagerError(f"Token request failed: {exc}") from exc

            data = _parse_json_response(resp)

            if "error" not in data:
                # Success
                return _parse_token_response(data)

            error = data["error"]
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                current_interval += 5
                logger.debug("OAuth2 slow_down: increasing interval to %s", current_interval)
                continue
            if error in ("access_denied", "expired_token"):
                desc = data.get("error_description", error)
                raise McpManagerError(f"OAuth2 device flow failed: {desc}")
            # Unknown error — abort to avoid infinite loop
            desc = data.get("error_description", error)
            raise McpManagerError(f"OAuth2 token endpoint error: {desc}")

    def refresh(self, refresh_token: str) -> TokenResponse:
        """Refresh an access token using a refresh token.

        Returns a new TokenResponse. The caller should persist the new tokens.
        """
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
        }
        try:
            resp = httpx.post(self.token_url, data=payload, timeout=30)
        except httpx.HTTPError as exc:
            raise McpManagerError(f"Token refresh failed: {exc}") from exc

        data = _parse_json_response(resp)
        if "error" in data:
            desc = data.get("error_description", data["error"])
            raise McpManagerError(f"Token refresh error: {desc}")

        return _parse_token_response(data)

    def revoke(self, token: str, token_type_hint: str = "access_token") -> bool:
        """Revoke a token via RFC 7009 revocation endpoint.

        Returns True if revocation was attempted (success or endpoint absent).
        Returns False only if the revocation endpoint is known but returns an error.
        """
        # NOTE: revocation URL is stored on the AuthProfile, not here.
        # This method is a placeholder; callers should use the endpoint from discovery.
        logger.debug("Token revocation not implemented in base client.")
        return True


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_oauth2_endpoints(registry_url: str, timeout: float = 10.0) -> OAuth2Endpoints | None:
    """Discover OAuth2 device flow endpoints for a registry.

    Tries two mechanisms in order:
    1. MCP manifest ``auth`` block in the registry's mcp.yaml
    2. RFC 8414 ``.well-known/oauth-authorization-server``

    Returns None if neither mechanism yields device flow support.
    """
    # Mechanism A: MCP manifest auth block
    endpoints = _discover_from_manifest(registry_url, timeout)
    if endpoints:
        return endpoints

    # Mechanism B: well-known endpoint
    endpoints = _discover_from_well_known(registry_url, timeout)
    if endpoints:
        return endpoints

    return None


def _discover_from_manifest(registry_url: str, timeout: float) -> OAuth2Endpoints | None:
    """Fetch the registry manifest and look for an auth block."""
    try:
        resp = httpx.get(registry_url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError:
        return None

    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        import json as _json

        try:
            data = _json.loads(resp.text)
        except Exception:
            return None
    else:
        # Assume YAML
        try:
            import yaml as _yaml

            data = _yaml.safe_load(resp.text)
        except Exception:
            return None

    auth = data.get("auth") if isinstance(data, dict) else None
    if not isinstance(auth, dict):
        return None

    device_auth = auth.get("device_authorization_endpoint")
    token = auth.get("token_endpoint")
    revocation = auth.get("revocation_endpoint")

    if device_auth and token:
        return OAuth2Endpoints(
            device_authorization=device_auth,
            token=token,
            revocation=revocation,
        )
    return None


def _discover_from_well_known(registry_url: str, timeout: float) -> OAuth2Endpoints | None:
    """Fetch RFC 8414 well-known metadata."""
    import urllib.parse

    parsed = urllib.parse.urlparse(registry_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    well_known = f"{base}/.well-known/oauth-authorization-server"

    try:
        resp = httpx.get(well_known, timeout=timeout, follow_redirects=True)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except httpx.HTTPError:
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    device_auth = data.get("device_authorization_endpoint")
    token = data.get("token_endpoint")
    revocation = data.get("revocation_endpoint")

    grant_types = data.get("grant_types_supported", [])
    if _DEVICE_CODE_GRANT not in grant_types:
        return None

    if device_auth and token:
        return OAuth2Endpoints(
            device_authorization=device_auth,
            token=token,
            revocation=revocation,
        )
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_response(resp: httpx.Response) -> dict[str, Any]:
    """Safely parse a JSON response body."""
    try:
        data = resp.json()
    except Exception as exc:
        raise McpManagerError(f"Invalid JSON from OAuth2 endpoint: {exc}") from exc
    if not isinstance(data, dict):
        raise McpManagerError("OAuth2 endpoint returned non-JSON-object response")
    return data


def _parse_token_response(data: dict[str, Any]) -> TokenResponse:
    """Parse a successful token endpoint response."""
    access_token = data.get("access_token")
    if not access_token:
        raise McpManagerError("Token response missing access_token")

    return TokenResponse(
        access_token=access_token,
        token_type=data.get("token_type", "bearer"),
        expires_in=data.get("expires_in"),
        refresh_token=data.get("refresh_token"),
    )

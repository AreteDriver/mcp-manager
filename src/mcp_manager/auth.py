"""Persistent authentication storage for mcp-manager."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from mcp_manager.config import MANAGER_CONFIG_DIR
from mcp_manager.exceptions import McpManagerError

logger = logging.getLogger(__name__)

_AUTH_FILE_OVERRIDE = os.environ.get("MCP_MANAGER_AUTH_FILE")
AUTH_FILE: Path = (
    Path(_AUTH_FILE_OVERRIDE) if _AUTH_FILE_OVERRIDE else MANAGER_CONFIG_DIR / "auth.json"
)


class AuthType(StrEnum):
    """Supported authentication types."""

    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"


@dataclass(frozen=True)
class AuthProfile:
    """A single stored authentication profile."""

    type: AuthType
    token: str | None = None
    user: str | None = None
    password: str | None = None
    refresh_token: str | None = None
    expires_at: float | None = None
    token_url: str | None = None
    added_at: float = field(default_factory=lambda: __import__("time").time())

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": self.type.value,
            "token": self.token,
            "user": self.user,
            "password": self.password,
            "added_at": self.added_at,
        }
        if self.refresh_token is not None:
            result["refresh_token"] = self.refresh_token
        if self.expires_at is not None:
            result["expires_at"] = self.expires_at
        if self.token_url is not None:
            result["token_url"] = self.token_url
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthProfile:
        return cls(
            type=AuthType(data["type"]),
            token=data.get("token"),
            user=data.get("user"),
            password=data.get("password"),
            refresh_token=data.get("refresh_token"),
            expires_at=data.get("expires_at"),
            token_url=data.get("token_url"),
            added_at=data.get("added_at", 0.0),
        )

    def to_headers(self) -> dict[str, str]:
        if self.type in (AuthType.BEARER, AuthType.OAUTH2) and self.token:
            return {"Authorization": f"Bearer {self.token}"}
        if self.type == AuthType.BASIC and self.user and self.password:
            import base64
            creds = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
            return {"Authorization": f"Basic {creds}"}
        return {}


class AuthStore:
    """Persistent JSON-backed store for registry authentication profiles."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or AUTH_FILE
        self._profiles: dict[str, AuthProfile] = {}

    def load(self) -> None:
        self._profiles.clear()
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise McpManagerError(f"Failed to load auth store: {exc}") from exc
        if not isinstance(raw, dict):
            raise McpManagerError("Auth store file is not a JSON object")
        for url, profile_data in raw.items():
            try:
                self._profiles[url] = AuthProfile.from_dict(profile_data)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping invalid auth profile %r: %s", url, exc)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {url: p.to_dict() for url, p in self._profiles.items()}
        try:
            tmp_path = self._path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            os.chmod(tmp_path, 0o600)
            tmp_path.replace(self._path)
        except OSError as exc:
            raise McpManagerError(f"Failed to save auth store: {exc}") from exc

    def add(self, url: str, profile: AuthProfile) -> None:
        self._profiles[_normalize_url(url)] = profile

    def remove(self, url: str) -> bool:
        key = _normalize_url(url)
        if key in self._profiles:
            del self._profiles[key]
            return True
        return False

    def get(self, url: str) -> AuthProfile | None:
        return self._profiles.get(_normalize_url(url))

    def list_all(self) -> list[tuple[str, AuthProfile]]:
        return [(k, self._profiles[k]) for k in sorted(self._profiles)]

    def check_permissions(self) -> tuple[bool, str]:
        if not self._path.exists():
            return (True, "")
        mode = self._path.stat().st_mode
        if mode & 0o077:
            actual = oct(mode & 0o777)
            return (
                False,
                f"Warning: auth file {self._path} has permissions {actual}. Recommend chmod 600.",
            )
        return (True, "")


def _normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if "://" in url:
        scheme, rest = url.split("://", 1)
        if "/" in rest:
            netloc, path = rest.split("/", 1)
            url = f"{scheme.lower()}://{netloc.lower()}/{path}"
        else:
            url = f"{scheme.lower()}://{rest.lower()}"
    return url


def resolve_auth_headers(
    url: str,
    *,
    cli_token: str | None = None,
    cli_user: str | None = None,
    cli_password: str | None = None,
    cli_headers: dict[str, str] | None = None,
    env_token: str | None = None,
    env_user: str | None = None,
    env_password: str | None = None,
) -> dict[str, str] | None:
    headers: dict[str, str] = {}
    if cli_token:
        headers["Authorization"] = f"Bearer {cli_token}"
    elif cli_user and cli_password:
        import base64
        creds = base64.b64encode(f"{cli_user}:{cli_password}".encode()).decode()
        headers["Authorization"] = f"Basic {creds}"
    if cli_headers:
        headers.update(cli_headers)
    if headers:
        return headers if headers else None
    store = AuthStore()
    store.load()
    profile = store.get(url)
    if profile:
        profile_headers = profile.to_headers()
        if profile_headers:
            return profile_headers
    if env_token:
        return {"Authorization": f"Bearer {env_token}"}
    if env_user and env_password:
        import base64
        creds = base64.b64encode(f"{env_user}:{env_password}".encode()).decode()
        return {"Authorization": f"Basic {creds}"}
    return None

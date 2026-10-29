"""Tests for mcp_manager.auth."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_manager.auth import (
    AuthProfile,
    AuthStore,
    AuthType,
    _normalize_url,
    resolve_auth_headers,
)


class TestAuthStore:
    """Tests for AuthStore persistence and operations."""

    def test_add_and_get_bearer(self, tmp_path: Path) -> None:
        store = AuthStore(path=tmp_path / "auth.json")
        profile = AuthProfile(type=AuthType.BEARER, token="ghp_xxx")
        store.add("https://example.com/reg.yaml", profile)
        store.save()
        store.load()
        got = store.get("https://example.com/reg.yaml")
        assert got is not None
        assert got.type == AuthType.BEARER
        assert got.token == "ghp_xxx"

    def test_add_and_get_basic(self, tmp_path: Path) -> None:
        store = AuthStore(path=tmp_path / "auth.json")
        profile = AuthProfile(type=AuthType.BASIC, user="alice", password="secret")
        store.add("https://example.com/reg.yaml", profile)
        store.save()
        store.load()
        got = store.get("https://example.com/reg.yaml")
        assert got is not None
        assert got.type == AuthType.BASIC
        assert got.user == "alice"
        assert got.password == "secret"

    def test_remove(self, tmp_path: Path) -> None:
        store = AuthStore(path=tmp_path / "auth.json")
        profile = AuthProfile(type=AuthType.BEARER, token="t")
        store.add("https://example.com/reg.yaml", profile)
        store.save()
        store.load()
        assert store.remove("https://example.com/reg.yaml") is True
        assert store.get("https://example.com/reg.yaml") is None
        assert store.remove("https://example.com/reg.yaml") is False

    def test_list_all_sorted(self, tmp_path: Path) -> None:
        store = AuthStore(path=tmp_path / "auth.json")
        store.add("https://z.com/reg.yaml", AuthProfile(type=AuthType.BEARER, token="z"))
        store.add("https://a.com/reg.yaml", AuthProfile(type=AuthType.BEARER, token="a"))
        items = store.list_all()
        assert [url for url, _ in items] == [
            "https://a.com/reg.yaml",
            "https://z.com/reg.yaml",
        ]

    def test_file_permissions_0o600(self, tmp_path: Path) -> None:
        store = AuthStore(path=tmp_path / "auth.json")
        store.add("https://example.com/reg.yaml", AuthProfile(type=AuthType.BEARER, token="t"))
        store.save()
        mode = (tmp_path / "auth.json").stat().st_mode
        if os.name != "nt":
            assert mode & 0o777 == 0o600

    def test_check_permissions_warns_on_overly_permissive(self, tmp_path: Path) -> None:
        if os.name == "nt":
            pytest.skip("Windows permissions are ACL-based")
        auth_file = tmp_path / "auth.json"
        auth_file.write_text("{}", encoding="utf-8")
        os.chmod(auth_file, 0o644)
        store = AuthStore(path=auth_file)
        ok, msg = store.check_permissions()
        assert ok is False
        assert "644" in msg

    def test_check_permissions_ok_for_0o600(self, tmp_path: Path) -> None:
        store = AuthStore(path=tmp_path / "auth.json")
        store.add("https://example.com/reg.yaml", AuthProfile(type=AuthType.BEARER, token="t"))
        store.save()
        ok, msg = store.check_permissions()
        assert ok is True

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        (tmp_path / "auth.json").write_text("not json", encoding="utf-8")
        store = AuthStore(path=tmp_path / "auth.json")
        with pytest.raises(Exception, match="Failed to load"):
            store.load()

    def test_load_non_dict(self, tmp_path: Path) -> None:
        (tmp_path / "auth.json").write_text("[1, 2, 3]", encoding="utf-8")
        store = AuthStore(path=tmp_path / "auth.json")
        with pytest.raises(Exception, match="not a JSON object"):
            store.load()


class TestNormalizeUrl:
    def test_strip_trailing_slash(self) -> None:
        assert _normalize_url("https://example.com/") == "https://example.com"
        assert _normalize_url("https://example.com/reg.yaml/") == "https://example.com/reg.yaml"

    def test_lowercase_scheme_and_host(self) -> None:
        assert _normalize_url("HTTPS://EXAMPLE.COM/reg.yaml") == "https://example.com/reg.yaml"

    def test_preserve_path_case(self) -> None:
        assert _normalize_url("https://example.com/REG.yaml") == "https://example.com/REG.yaml"


class TestAuthProfile:
    def test_bearer_to_headers(self) -> None:
        p = AuthProfile(type=AuthType.BEARER, token="tok123")
        assert p.to_headers() == {"Authorization": "Bearer tok123"}

    def test_basic_to_headers(self) -> None:
        p = AuthProfile(type=AuthType.BASIC, user="alice", password="wonderland")
        headers = p.to_headers()
        assert headers["Authorization"].startswith("Basic ")

    def test_roundtrip_dict(self) -> None:
        p = AuthProfile(type=AuthType.BEARER, token="tok")
        assert AuthProfile.from_dict(p.to_dict()) == p


class TestResolveAuthHeaders:
    def test_cli_token_highest_priority(self, tmp_path: Path, monkeypatch) -> None:
        # Store a profile that should be ignored.
        store = AuthStore(path=tmp_path / "auth.json")
        store.add("https://example.com/reg.yaml", AuthProfile(type=AuthType.BEARER, token="stored"))
        store.save()
        # Env var should also be ignored.
        monkeypatch.setenv("MCP_MANAGER_REGISTRY_TOKEN", "env")
        result = resolve_auth_headers(
            "https://example.com/reg.yaml",
            cli_token="cli",
            env_token="env",
        )
        assert result == {"Authorization": "Bearer cli"}

    def test_profile_second_priority(self, tmp_path: Path, monkeypatch) -> None:
        auth_file = tmp_path / "auth.json"
        store = AuthStore(path=auth_file)
        store.add("https://example.com/reg.yaml", AuthProfile(type=AuthType.BEARER, token="stored"))
        store.save()
        monkeypatch.delenv("MCP_MANAGER_REGISTRY_TOKEN", raising=False)
        with patch("mcp_manager.auth.AUTH_FILE", auth_file):
            result = resolve_auth_headers(
                "https://example.com/reg.yaml",
                env_token="env",
            )
        assert result == {"Authorization": "Bearer stored"}

    def test_env_var_third_priority(self, tmp_path: Path) -> None:
        with patch("mcp_manager.auth.AUTH_FILE", tmp_path / "auth.json"):
            result = resolve_auth_headers(
                "https://example.com/reg.yaml",
                env_token="envtok",
            )
        assert result == {"Authorization": "Bearer envtok"}

    def test_anonymous_when_nothing(self, tmp_path: Path) -> None:
        with patch("mcp_manager.auth.AUTH_FILE", tmp_path / "auth.json"):
            result = resolve_auth_headers("https://example.com/reg.yaml")
        assert result is None

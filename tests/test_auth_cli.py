"""Tests for registry auth CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from mcp_manager.auth import AuthProfile, AuthStore, AuthType
from mcp_manager.cli import app

runner = CliRunner()


class TestRegistryLogin:
    def test_login_bearer(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "auth.json"
        with patch("mcp_manager.auth.AUTH_FILE", auth_file):
            result = runner.invoke(
                app, ["registry", "login", "https://reg.example.com/mcp.yaml", "--token", "ghp_xxx"]
            )
        assert result.exit_code == 0
        assert "Saved bearer" in result.output
        store = AuthStore(path=auth_file)
        store.load()
        profile = store.get("https://reg.example.com/mcp.yaml")
        assert profile is not None
        assert profile.type == AuthType.BEARER
        assert profile.token == "ghp_xxx"

    def test_login_basic(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "auth.json"
        with patch("mcp_manager.auth.AUTH_FILE", auth_file):
            result = runner.invoke(
                app,
                [
                    "registry",
                    "login",
                    "https://reg.example.com/mcp.yaml",
                    "--user",
                    "alice",
                    "--password",
                    "wonderland",
                ],
            )
        assert result.exit_code == 0
        assert "Saved basic" in result.output
        store = AuthStore(path=auth_file)
        store.load()
        profile = store.get("https://reg.example.com/mcp.yaml")
        assert profile is not None
        assert profile.type == AuthType.BASIC
        assert profile.user == "alice"
        assert profile.password == "wonderland"

    def test_login_requires_token_or_password(self) -> None:
        result = runner.invoke(
            app, ["registry", "login", "https://reg.example.com/mcp.yaml"]
        )
        assert result.exit_code == 1
        assert "Provide --token" in result.output

    def test_login_overwrites_existing(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "auth.json"
        store = AuthStore(path=auth_file)
        store.add(
            "https://reg.example.com/mcp.yaml",
            AuthProfile(type=AuthType.BEARER, token="old"),
        )
        store.save()
        with patch("mcp_manager.auth.AUTH_FILE", auth_file):
            result = runner.invoke(
                app,
                [
                    "registry",
                    "login",
                    "https://reg.example.com/mcp.yaml",
                    "--token",
                    "new",
                ],
            )
        assert result.exit_code == 0
        assert "Overwriting" in result.output
        store.load()
        assert store.get("https://reg.example.com/mcp.yaml").token == "new"


class TestRegistryLogout:
    def test_logout_removes_profile(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "auth.json"
        store = AuthStore(path=auth_file)
        store.add("https://reg.example.com/mcp.yaml", AuthProfile(type=AuthType.BEARER, token="t"))
        store.save()
        with patch("mcp_manager.auth.AUTH_FILE", auth_file):
            result = runner.invoke(
                app, ["registry", "logout", "https://reg.example.com/mcp.yaml"]
            )
        assert result.exit_code == 0
        assert "Removed" in result.output
        store.load()
        assert store.get("https://reg.example.com/mcp.yaml") is None

    def test_logout_not_found(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "auth.json"
        with patch("mcp_manager.auth.AUTH_FILE", auth_file):
            result = runner.invoke(
                app, ["registry", "logout", "https://reg.example.com/mcp.yaml"]
            )
        assert result.exit_code == 0
        assert "No credentials found" in result.output


class TestRegistryAuthList:
    def test_auth_list_empty(self) -> None:
        result = runner.invoke(app, ["registry", "auth-list"])
        assert result.exit_code == 0
        assert "No stored registry credentials" in result.output

    def test_auth_list_shows_profiles(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "auth.json"
        store = AuthStore(path=auth_file)
        store.add(
            "https://reg.example.com/mcp.yaml",
            AuthProfile(type=AuthType.BEARER, token="secrettoken"),
        )
        store.save()
        with patch("mcp_manager.auth.AUTH_FILE", auth_file):
            result = runner.invoke(app, ["registry", "auth-list"])
        assert result.exit_code == 0
        assert "reg.example.com" in result.output
        assert "Bearer secr****" in result.output
        assert "secrettoken" not in result.output  # masked

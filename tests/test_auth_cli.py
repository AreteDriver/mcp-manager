"""Tests for registry auth CLI commands."""

from __future__ import annotations

import importlib
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



class TestRegistryLoginValidation:
    """Tests for credential validation in registry login."""

    def test_login_401_no_storage(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "auth.json"
        with (
            patch("mcp_manager.auth.AUTH_FILE", auth_file),
            patch("mcp_manager.commands.auth_cmd.httpx.head") as mock_head,
        ):
                mock_head.return_value.status_code = 401
                mock_head.return_value.reason_phrase = "Unauthorized"
                result = runner.invoke(
                    app,
                    [
                        "registry",
                        "login",
                        "https://reg.example.com/mcp.yaml",
                        "--token",
                        "bad",
                    ],
                )
        assert result.exit_code == 1
        assert "Authentication failed" in result.output
        assert "401" in result.output
        # Verify nothing stored.
        store = AuthStore(path=auth_file)
        store.load()
        assert store.get("https://reg.example.com/mcp.yaml") is None

    def test_login_200_stores(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "auth.json"
        with (
            patch("mcp_manager.auth.AUTH_FILE", auth_file),
            patch("mcp_manager.commands.auth_cmd.httpx.head") as mock_head,
        ):
                mock_head.return_value.status_code = 200
                mock_head.return_value.reason_phrase = "OK"
                result = runner.invoke(
                    app,
                    [
                        "registry",
                        "login",
                        "https://reg.example.com/mcp.yaml",
                        "--token",
                        "good",
                    ],
                )
        assert result.exit_code == 0
        assert "Saved bearer" in result.output
        store = AuthStore(path=auth_file)
        store.load()
        assert store.get("https://reg.example.com/mcp.yaml") is not None

    def test_login_405_warns_and_stores(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "auth.json"
        with (
            patch("mcp_manager.auth.AUTH_FILE", auth_file),
            patch("mcp_manager.commands.auth_cmd.httpx.head") as mock_head,
        ):
                mock_head.return_value.status_code = 405
                mock_head.return_value.reason_phrase = "Method Not Allowed"
                mock_head.return_value.is_success = False
                result = runner.invoke(
                    app,
                    [
                        "registry",
                        "login",
                        "https://reg.example.com/mcp.yaml",
                        "--token",
                        "tok",
                    ],
                )
        assert result.exit_code == 0
        assert "Warning" in result.output
        assert "405" in result.output
        store = AuthStore(path=auth_file)
        store.load()
        assert store.get("https://reg.example.com/mcp.yaml") is not None

    def test_login_http_error_warns_and_stores(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "auth.json"
        from httpx import HTTPError
        with (
            patch("mcp_manager.auth.AUTH_FILE", auth_file),
            patch(
                "mcp_manager.commands.auth_cmd.httpx.head",
                side_effect=HTTPError("connection refused"),
            ),
        ):
                result = runner.invoke(
                    app,
                    [
                        "registry",
                        "login",
                        "https://reg.example.com/mcp.yaml",
                        "--token",
                        "tok",
                    ],
                )
        assert result.exit_code == 0
        assert "Warning" in result.output
        store = AuthStore(path=auth_file)
        store.load()
        assert store.get("https://reg.example.com/mcp.yaml") is not None


class TestEnvVarFallback:
    """Tests for env-var auth fallback in registry commands."""

    def test_env_var_token_used(self, tmp_path: Path, monkeypatch) -> None:
        """MCP_MANAGER_REGISTRY_TOKEN is passed as Bearer when no profile exists."""
        auth_file = tmp_path / "auth.json"
        monkeypatch.setenv("MCP_MANAGER_REGISTRY_TOKEN", "envtok")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / ".mcp-manager.yml").write_text("""servers: {}
""")
        with (
            patch("mcp_manager.auth.AUTH_FILE", auth_file),
            # no stored profile
            patch("mcp_manager.registry_sync.httpx.get") as mock_get,
        ):
                mock_get.return_value.status_code = 200
                mock_get.return_value.text = "servers: {}"
                mock_get.return_value.raise_for_status = lambda: None
                result = runner.invoke(
                    app,
                    [
                        "registry",
                        "diff",
                        "https://example.com/registry.yaml",
                        "--project-dir",
                        str(project_dir),
                    ],
                )
        assert result.exit_code == 0
        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer envtok"

    def test_env_var_basic_used(self, tmp_path: Path, monkeypatch) -> None:
        """MCP_MANAGER_REGISTRY_USER/PASSWORD are passed as Basic when no profile exists."""
        auth_file = tmp_path / "auth.json"
        monkeypatch.setenv("MCP_MANAGER_REGISTRY_USER", "alice")
        monkeypatch.setenv("MCP_MANAGER_REGISTRY_PASSWORD", "wonderland")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / ".mcp-manager.yml").write_text("""servers: {}
""")
        with (
            patch("mcp_manager.auth.AUTH_FILE", auth_file),
            patch("mcp_manager.registry_sync.httpx.get") as mock_get,
        ):
                mock_get.return_value.status_code = 200
                mock_get.return_value.text = "servers: {}"
                mock_get.return_value.raise_for_status = lambda: None
                result = runner.invoke(
                    app,
                    [
                        "registry",
                        "diff",
                        "https://example.com/registry.yaml",
                        "--project-dir",
                        str(project_dir),
                    ],
                )
        assert result.exit_code == 0
        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"].startswith("Basic ")

    def test_cli_flag_overrides_env_var(self, tmp_path: Path, monkeypatch) -> None:
        """CLI --token takes precedence over env var."""
        auth_file = tmp_path / "auth.json"
        monkeypatch.setenv("MCP_MANAGER_REGISTRY_TOKEN", "envtok")
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / ".mcp-manager.yml").write_text("""servers: {}
""")
        with (
            patch("mcp_manager.auth.AUTH_FILE", auth_file),
            patch("mcp_manager.registry_sync.httpx.get") as mock_get,
        ):
                mock_get.return_value.status_code = 200
                mock_get.return_value.text = "servers: {}"
                mock_get.return_value.raise_for_status = lambda: None
                result = runner.invoke(
                    app,
                    [
                        "registry",
                        "diff",
                        "https://example.com/registry.yaml",
                        "--project-dir",
                        str(project_dir),
                        "--token",
                        "clitok",
                    ],
                )
        assert result.exit_code == 0
        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer clitok"

    def test_custom_auth_file_env_var(self, tmp_path: Path, monkeypatch) -> None:
        custom_auth = tmp_path / "custom_auth.json"
        monkeypatch.setenv("MCP_MANAGER_AUTH_FILE", str(custom_auth))

        # Need to reload auth module to pick up env var.
        import mcp_manager.auth as auth_mod
        importlib.reload(auth_mod)

        store = auth_mod.AuthStore()
        store.add(
            "https://example.com/reg.yaml",
            auth_mod.AuthProfile(type=auth_mod.AuthType.BEARER, token="t"),
        )
        store.save()
        assert custom_auth.exists()

        store2 = auth_mod.AuthStore()
        store2.load()
        assert store2.get("https://example.com/reg.yaml") is not None

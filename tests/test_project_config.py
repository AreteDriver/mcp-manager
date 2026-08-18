"""Tests for project-scoped config (project_config.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcp_manager.exceptions import WritebackError
from mcp_manager.models import McpServer, TransportType
from mcp_manager.project_config import (
    DEFAULT_FILENAME,
    _resolve_env_var,
    export_to_ide,
    init_project_config,
    load_servers_from_config,
    parse_project_config,
    validate_project_config,
)


class TestInitProjectConfig:
    """Tests for init_project_config scaffolding."""

    def test_creates_file(self, tmp_path: Path) -> None:
        target = init_project_config(tmp_path, project_name="test-proj")
        assert target.exists()
        assert target.name == DEFAULT_FILENAME
        content = target.read_text()
        assert "project: test-proj" in content

    def test_raises_if_exists(self, tmp_path: Path) -> None:
        target = tmp_path / DEFAULT_FILENAME
        target.write_text("exists")
        with pytest.raises(WritebackError, match="already exists"):
            init_project_config(tmp_path)

    def test_defaults_to_cwd(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        target = init_project_config(project_name="cwd-proj")
        assert target == tmp_path / DEFAULT_FILENAME


class TestParseProjectConfig:
    """Tests for parse_project_config."""

    def test_parses_valid_file(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {"command": "node", "args": ["index.js"]},
                        "remote": {"type": "sse", "url": "http://localhost:3000/sse"},
                    },
                }
            )
        )
        data = parse_project_config(config)
        assert data["project"] == "my-project"
        assert "local" in data["servers"]
        assert "remote" in data["servers"]

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(WritebackError, match="not found"):
            parse_project_config(tmp_path / DEFAULT_FILENAME)

    def test_raises_on_invalid_yaml(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text("{{bad yaml")
        with pytest.raises(WritebackError, match="Failed to parse"):
            parse_project_config(config)

    def test_raises_on_non_mapping(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text("- list\n- not\n- mapping")
        with pytest.raises(WritebackError, match="must contain a YAML mapping"):
            parse_project_config(config)


class TestValidateProjectConfig:
    """Tests for validate_project_config."""

    def test_valid_config_no_errors(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {"command": "python3", "args": ["server.py"]},
                    },
                }
            )
        )
        errors = validate_project_config(config)
        assert errors == []

    def test_missing_command_and_url(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "bad": {"args": []},
                    },
                }
            )
        )
        errors = validate_project_config(config)
        assert any("missing 'command' or 'url'" in e for e in errors)

    def test_env_var_not_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MISSING_VAR", raising=False)
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {
                            "command": "python3",
                            "env": {"SECRET": "$MISSING_VAR"},
                        },
                    },
                }
            )
        )
        errors = validate_project_config(config)
        assert any("MISSING_VAR" in e for e in errors)

    def test_env_var_resolved(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PRESENT_VAR", "secret_value")
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {
                            "command": "python3",
                            "env": {"SECRET": "$PRESENT_VAR"},
                        },
                    },
                }
            )
        )
        errors = validate_project_config(config)
        assert not any("PRESENT_VAR" in e for e in errors)

    def test_env_var_braced_resolved(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BRACED_VAR", "braced_value")
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {
                            "command": "python3",
                            "env": {"SECRET": "${BRACED_VAR}"},
                        },
                    },
                }
            )
        )
        errors = validate_project_config(config)
        assert errors == []
        servers = load_servers_from_config(config)
        assert servers[0].stdio_config is not None
        assert servers[0].stdio_config.env == {"SECRET": "braced_value"}

    def test_env_var_default_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("UNSET_VAR", raising=False)
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {
                            "command": "python3",
                            "env": {"SECRET": "${UNSET_VAR:-default_value}"},
                        },
                    },
                }
            )
        )
        errors = validate_project_config(config)
        assert errors == []
        servers = load_servers_from_config(config)
        assert servers[0].stdio_config is not None
        assert servers[0].stdio_config.env == {"SECRET": "default_value"}

    def test_env_var_default_uses_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SET_VAR", "from_env")
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {
                            "command": "python3",
                            "env": {"SECRET": "${SET_VAR:-default_value}"},
                        },
                    },
                }
            )
        )
        servers = load_servers_from_config(config)
        assert servers[0].stdio_config is not None
        assert servers[0].stdio_config.env == {"SECRET": "from_env"}

    def test_command_not_on_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _cmd: None)
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {"command": "nonexistent_binary_xyz"},
                    },
                }
            )
        )
        errors = validate_project_config(config)
        assert any("nonexistent_binary_xyz" in e for e in errors)


class TestLoadServersFromConfig:
    """Tests for load_servers_from_config."""

    def test_loads_stdio_server(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {
                            "command": "python3",
                            "args": ["server.py"],
                            "env": {"DEBUG": "1"},
                        },
                    },
                }
            )
        )
        servers = load_servers_from_config(config)
        assert len(servers) == 1
        s = servers[0]
        assert isinstance(s, McpServer)
        assert s.name == "local"
        assert s.transport == TransportType.STDIO
        assert s.stdio_config is not None
        assert s.stdio_config.command == "python3"
        assert s.stdio_config.args == ["server.py"]
        assert s.stdio_config.env == {"DEBUG": "1"}
        assert s.source_tool == "project"

    def test_loads_sse_server(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "remote": {
                            "type": "sse",
                            "url": "http://localhost:3000/sse",
                            "headers": {"Authorization": "Bearer token"},
                        },
                    },
                }
            )
        )
        servers = load_servers_from_config(config)
        assert len(servers) == 1
        s = servers[0]
        assert s.name == "remote"
        assert s.transport == TransportType.SSE
        assert s.network_config is not None
        assert s.network_config.url == "http://localhost:3000/sse"
        assert s.network_config.headers == {"Authorization": "Bearer token"}

    def test_skips_invalid_servers(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "good": {"command": "python3"},
                        "bad": "not a dict",
                    },
                }
            )
        )
        servers = load_servers_from_config(config)
        assert len(servers) == 1
        assert servers[0].name == "good"

    def test_env_var_resolution(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_URL", "postgres://localhost/db")
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {
                            "command": "python3",
                            "env": {"DATABASE_URL": "$DB_URL"},
                        },
                    },
                }
            )
        )
        servers = load_servers_from_config(config)
        assert servers[0].stdio_config is not None
        assert servers[0].stdio_config.env == {"DATABASE_URL": "postgres://localhost/db"}

    def test_env_var_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MISSING_VAR", raising=False)
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {
                            "command": "python3",
                            "env": {"SECRET": "$MISSING_VAR"},
                        },
                    },
                }
            )
        )
        servers = load_servers_from_config(config)
        assert servers[0].stdio_config is not None
        assert servers[0].stdio_config.env == {"SECRET": "$MISSING_VAR"}

    def test_loads_tags(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {
                            "command": "python3",
                            "tags": ["backend", "database"],
                        },
                        "remote": {
                            "type": "sse",
                            "url": "http://localhost:3000/sse",
                            "tags": ["frontend"],
                        },
                    },
                }
            )
        )
        servers = load_servers_from_config(config)
        assert len(servers) == 2
        by_name = {s.name: s for s in servers}
        assert by_name["local"].tags == ["backend", "database"]
        assert by_name["remote"].tags == ["frontend"]

    def test_skips_none_tags(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {
                            "command": "python3",
                            "tags": ["backend", None, "database"],
                        },
                    },
                }
            )
        )
        servers = load_servers_from_config(config)
        assert servers[0].tags == ["backend", "database"]


class TestExtendsInheritance:
    """Tests for ``extends:`` config inheritance."""

    def test_local_file_extends(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yml"
        base.write_text(
            yaml.dump(
                {
                    "project": "base-project",
                    "servers": {
                        "shared": {"command": "node", "args": ["shared.js"]},
                    },
                }
            )
        )
        project = tmp_path / DEFAULT_FILENAME
        project.write_text(
            yaml.dump(
                {
                    "extends": "base.yml",
                    "project": "my-project",
                    "servers": {
                        "local": {"command": "python3", "args": ["local.py"]},
                    },
                }
            )
        )
        data = parse_project_config(project)
        assert data["project"] == "my-project"
        assert "shared" in data["servers"]
        assert "local" in data["servers"]

    def test_project_overrides_base_server(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yml"
        base.write_text(
            yaml.dump(
                {
                    "servers": {
                        "shared": {"command": "node"},
                    },
                }
            )
        )
        project = tmp_path / DEFAULT_FILENAME
        project.write_text(
            yaml.dump(
                {
                    "extends": "base.yml",
                    "servers": {
                        "shared": {"command": "python3"},
                    },
                }
            )
        )
        data = parse_project_config(project)
        assert data["servers"]["shared"]["command"] == "python3"

    def test_circular_extends_raises(self, tmp_path: Path) -> None:
        a = tmp_path / "a.yml"
        b = tmp_path / "b.yml"
        a.write_text(yaml.dump({"extends": "b.yml", "servers": {}}))
        b.write_text(yaml.dump({"extends": "a.yml", "servers": {}}))
        with pytest.raises(WritebackError, match="Circular extends"):
            parse_project_config(a)

    def test_missing_extends_source_raises(self, tmp_path: Path) -> None:
        project = tmp_path / DEFAULT_FILENAME
        project.write_text(yaml.dump({"extends": "missing.yml", "servers": {}}))
        with pytest.raises(WritebackError, match="Extends source not found"):
            parse_project_config(project)

    def test_file_scheme_extends(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yml"
        base.write_text(yaml.dump({"servers": {"shared": {"command": "node"}}}))
        project = tmp_path / DEFAULT_FILENAME
        project.write_text(yaml.dump({"extends": f"file://{base}", "servers": {}}))
        data = parse_project_config(project)
        assert "shared" in data["servers"]

    def test_github_to_raw_url(self) -> None:
        from mcp_manager.project_config import _github_to_raw_url

        url = _github_to_raw_url("github:AreteDriver/mcp-manager/base.yml@v0.4.0")
        assert url == "https://raw.githubusercontent.com/AreteDriver/mcp-manager/v0.4.0/base.yml"

    def test_github_url_missing_ref_raises(self) -> None:
        from mcp_manager.project_config import _github_to_raw_url

        with pytest.raises(WritebackError, match="must include @ref"):
            _github_to_raw_url("github:AreteDriver/mcp-manager/base.yml")

    def test_remote_extends_mocked(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def mock_get(url: str, **kwargs: Any) -> Any:
            class Resp:
                text = yaml.dump({"servers": {"remote": {"command": "curl"}}})

                def raise_for_status(self) -> None: ...

            return Resp()

        monkeypatch.setattr("httpx.get", mock_get)
        project = tmp_path / DEFAULT_FILENAME
        project.write_text(yaml.dump({"extends": "https://example.com/base.yml", "servers": {}}))
        data = parse_project_config(project)
        assert "remote" in data["servers"]

    def test_list_of_extends(self, tmp_path: Path) -> None:
        base1 = tmp_path / "base1.yml"
        base2 = tmp_path / "base2.yml"
        base1.write_text(yaml.dump({"servers": {"a": {"command": "a"}}}))
        base2.write_text(yaml.dump({"servers": {"b": {"command": "b"}}}))
        project = tmp_path / DEFAULT_FILENAME
        project.write_text(yaml.dump({"extends": ["base1.yml", "base2.yml"], "servers": {}}))
        data = parse_project_config(project)
        assert "a" in data["servers"]
        assert "b" in data["servers"]

    def test_extends_preserved_other_keys(self, tmp_path: Path) -> None:
        base = tmp_path / "base.yml"
        base.write_text(yaml.dump({"servers": {"s": {"command": "node"}}}))
        project = tmp_path / DEFAULT_FILENAME
        project.write_text(
            yaml.dump(
                {
                    "extends": "base.yml",
                    "project": "p",
                    "servers": {},
                    "custom_key": 123,
                }
            )
        )
        data = parse_project_config(project)
        assert data["custom_key"] == 123


class TestExportToIde:
    """Tests for export_to_ide."""

    def test_dry_run(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {"command": "python3", "args": ["server.py"]},
                    },
                }
            )
        )
        result = export_to_ide(config, "cursor", dry_run=True)
        assert result.exists() or str(result).endswith("mcp.json")

    def test_from_directory(self, tmp_path: Path) -> None:
        config = tmp_path / DEFAULT_FILENAME
        config.write_text(
            yaml.dump(
                {
                    "project": "my-project",
                    "servers": {
                        "local": {"command": "python3", "args": ["server.py"]},
                    },
                }
            )
        )
        result = export_to_ide(tmp_path, "cursor", dry_run=True)
        assert "mcp.json" in str(result) or "cursor" in str(result).lower()


class TestResolveEnvVar:
    """Direct tests for _resolve_env_var helper."""

    def test_simple_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SIMPLE", "val")
        assert _resolve_env_var("$SIMPLE") == "val"

    def test_simple_unset_returns_literal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MISSING", raising=False)
        assert _resolve_env_var("$MISSING") == "$MISSING"

    def test_braced_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BRACED", "val")
        assert _resolve_env_var("${BRACED}") == "val"

    def test_default_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UNSET", raising=False)
        assert _resolve_env_var("${UNSET:-default}") == "default"

    def test_default_uses_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SET", "env_val")
        assert _resolve_env_var("${SET:-default}") == "env_val"

    def test_required_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REQ", raising=False)
        with pytest.raises(WritebackError, match="Required env var 'REQ' is not set"):
            _resolve_env_var("${REQ:?required}")

    def test_required_uses_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REQ", "env_val")
        assert _resolve_env_var("${REQ:?required}") == "env_val"

    def test_non_env_value_passes_through(self) -> None:
        assert _resolve_env_var("plain_string") == "plain_string"

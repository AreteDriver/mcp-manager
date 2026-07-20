"""Tests for the marketplace module."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from mcp_manager.marketplace import (
    MarketplaceError,
    MarketplaceIndex,
    MarketplaceServer,
    QualityScore,
    install_to_project,
    load_index,
    refresh_marketplace,
)
from mcp_manager.models import StdioConfig, TransportType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_server(
    name: str = "test",
    verified: bool = False,
    categories: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> MarketplaceServer:
    env = env or {}
    return MarketplaceServer(
        name=name,
        display_name=name,
        description="A test server",
        repository="https://github.com/test/test",
        categories=categories or ["Test"],
        install_spec={
            "command": "npx",
            "args": ["-y", f"@{name}/pkg"],
            "env": env,
        },
        quality=QualityScore(verified=verified),
    )


# ---------------------------------------------------------------------------
# load_index
# ---------------------------------------------------------------------------


def test_load_index_reads_yaml(tmp_path: Path) -> None:
    """load_index parses marketplace YAML correctly."""
    index_file = tmp_path / "index.yaml"
    index_file.write_text(
        yaml.dump(
            {
                "categories": [{"name": "Cat", "description": "Desc"}],
                "servers": [
                    {
                        "name": "srv",
                        "display_name": "Srv",
                        "description": "d",
                        "repository": "https://github.com/a/b",
                        "categories": ["Cat"],
                        "install_spec": {"command": "npx", "args": ["pkg"], "env": {}},
                        "quality": {
                            "health_pass_rate": 1.0,
                            "tool_count": 5,
                            "last_updated": "2026-01-01",
                            "license": "MIT",
                            "verified": True,
                        },
                    }
                ],
            }
        )
    )
    index = load_index(index_file)
    assert "srv" in index.servers
    assert index.servers["srv"].quality.verified is True
    assert index.servers["srv"].quality.health_pass_rate == 1.0


def test_load_index_missing_file(tmp_path: Path) -> None:
    """Raises MarketplaceError when file is missing."""
    with pytest.raises(MarketplaceError):
        load_index(tmp_path / "missing.yaml")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_by_name() -> None:
    index = MarketplaceIndex(
        categories=[],
        servers=[
            _make_server("alpha", verified=True),
            _make_server("beta", verified=True),
        ],
    )
    results = index.search(query="alp", verified_only=False)
    assert len(results) == 1
    assert results[0].name == "alpha"


def test_search_by_description() -> None:
    srv = _make_server("alpha", verified=True)
    srv.description = "special database handler"
    index = MarketplaceIndex(categories=[], servers=[srv, _make_server("beta", verified=True)])
    results = index.search(query="database", verified_only=False)
    assert len(results) == 1
    assert results[0].name == "alpha"


def test_search_by_category() -> None:
    index = MarketplaceIndex(
        categories=[],
        servers=[
            _make_server("alpha", categories=["DB"], verified=True),
            _make_server("beta", categories=["FS"], verified=True),
        ],
    )
    results = index.search(category="DB", verified_only=False)
    assert len(results) == 1
    assert results[0].name == "alpha"


def test_search_verified_only_default() -> None:
    index = MarketplaceIndex(
        categories=[],
        servers=[
            _make_server("verified", verified=True),
            _make_server("unverified", verified=False),
        ],
    )
    results = index.search()
    assert len(results) == 1
    assert results[0].name == "verified"


def test_search_include_unverified() -> None:
    index = MarketplaceIndex(
        categories=[],
        servers=[
            _make_server("verified", verified=True),
            _make_server("unverified", verified=False),
        ],
    )
    results = index.search(verified_only=False)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# env placeholders / build_stdio_config
# ---------------------------------------------------------------------------


def test_env_placeholders_extracted() -> None:
    srv = _make_server(env={"URL": "${DATABASE_URL}", "TOKEN": "${API_TOKEN}"})
    placeholders = srv._env_var_placeholders()
    assert set(placeholders) == {"DATABASE_URL", "API_TOKEN"}


def test_build_stdio_config_with_overrides() -> None:
    srv = _make_server(env={"URL": "${DATABASE_URL}"})
    cfg = srv.build_stdio_config({"DATABASE_URL": "postgres://localhost/db"})
    assert isinstance(cfg, StdioConfig)
    assert cfg.env["URL"] == "postgres://localhost/db"


def test_build_stdio_config_keeps_literal_values() -> None:
    srv = _make_server(env={"URL": "${DATABASE_URL}", "DEBUG": "1"})
    cfg = srv.build_stdio_config({"DATABASE_URL": "x"})
    assert cfg.env["DEBUG"] == "1"


# ---------------------------------------------------------------------------
# install_to_project
# ---------------------------------------------------------------------------


def test_install_adds_server_to_config(tmp_path: Path) -> None:
    srv = _make_server("alpha", env={"URL": "${DATABASE_URL}"})
    config_path = install_to_project(
        srv,
        tmp_path,
        interactive=False,
    )
    assert config_path.exists()
    data = yaml.safe_load(config_path.read_text())
    assert "alpha" in data["servers"]
    assert data["servers"]["alpha"]["command"] == "npx"


def test_install_dry_run_does_not_write(tmp_path: Path) -> None:
    srv = _make_server("alpha")
    config_path = install_to_project(srv, tmp_path, dry_run=True, interactive=False)
    assert not config_path.exists()


def test_install_duplicate_raises(tmp_path: Path) -> None:
    srv = _make_server("alpha")
    install_to_project(srv, tmp_path, interactive=False)
    with pytest.raises(MarketplaceError, match="already exists"):
        install_to_project(srv, tmp_path, interactive=False)


def test_install_prompts_for_env_vars(tmp_path: Path) -> None:
    srv = _make_server("alpha", env={"URL": "${DATABASE_URL}"})
    with patch(
        "mcp_manager.marketplace._env_var_prompts",
        return_value={"DATABASE_URL": "postgres://test"},
    ):
        config_path = install_to_project(srv, tmp_path, interactive=True)
    data = yaml.safe_load(config_path.read_text())
    assert data["servers"]["alpha"]["env"]["URL"] == "postgres://test"


# ---------------------------------------------------------------------------
# refresh_marketplace
# ---------------------------------------------------------------------------


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_refresh_updates_scores(tmp_path: Path) -> None:
    """refresh_marketplace updates quality scores and writes back."""
    from mcp_manager.health import HealthResult
    from mcp_manager.models import ServerStatus

    index_file = tmp_path / "index.yaml"
    index_file.write_text(
        yaml.dump(
            {
                "categories": [],
                "servers": [
                    {
                        "name": "test",
                        "display_name": "Test",
                        "description": "d",
                        "repository": "https://github.com/a/b",
                        "categories": [],
                        "install_spec": {"command": "echo", "args": ["hello"], "env": {}},
                        "quality": {
                            "health_pass_rate": 0.0,
                            "tool_count": 0,
                            "last_updated": None,
                            "license": "MIT",
                            "verified": False,
                        },
                    }
                ],
            }
        )
    )

    mock_result = HealthResult(
        server_name="test",
        status=ServerStatus.HEALTHY,
        latency_ms=10.0,
        transport=TransportType.STDIO,
        server_info={"tool_count": 3},
    )

    import asyncio

    original_run = asyncio.run

    def _mock_run(coro, *args: Any, **kwargs: Any) -> Any:
        return mock_result

    try:
        asyncio.run = _mock_run
        updated = refresh_marketplace(index_file, timeout=5)
    finally:
        asyncio.run = original_run

    assert updated is True
    restored = load_index(index_file)
    server = restored.servers["test"]
    assert server.quality.health_pass_rate == 1.0
    assert server.quality.tool_count == 3
    assert server.quality.last_updated is not None

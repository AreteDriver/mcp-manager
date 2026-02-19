"""Tests for mcp_manager.gates."""

from __future__ import annotations

from unittest.mock import patch

import typer
from typer.testing import CliRunner

from mcp_manager.gates import require_pro

runner = CliRunner()


def test_require_pro_blocks_free_user() -> None:
    """Free user gets upgrade message and exit code 1."""
    test_app = typer.Typer()

    @test_app.command()
    @require_pro("auto_health_daemon")
    def protected() -> None:
        print("should not reach here")

    with patch("mcp_manager.gates.has_feature", return_value=False):
        result = runner.invoke(test_app, [])
    assert result.exit_code == 1
    assert "auto_health_daemon" in result.output or "Pro" in result.output


def test_require_pro_allows_pro_user() -> None:
    """Pro user gets through the gate."""
    test_app = typer.Typer()

    @test_app.command()
    @require_pro("auto_health_daemon")
    def protected() -> None:
        print("access granted")

    with patch("mcp_manager.gates.has_feature", return_value=True):
        result = runner.invoke(test_app, [])
    assert result.exit_code == 0
    assert "access granted" in result.output

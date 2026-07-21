"""Tests for mcp_manager.__main__ entry point."""

from __future__ import annotations

from mcp_manager.cli import app


def test_main_entry_point() -> None:
    """__main__ module exposes app and delegates when run directly."""
    import mcp_manager.__main__ as main_module

    assert hasattr(main_module, "app")
    assert main_module.app is app

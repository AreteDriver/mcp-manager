"""Feature gating decorators for mcp-manager."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

import typer
from rich.console import Console

from mcp_manager.licensing import get_upgrade_message, has_feature

F = TypeVar("F", bound=Callable[..., Any])


def require_pro(feature: str) -> Callable[[F], F]:
    """Decorator that gates a CLI command behind Pro tier."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not has_feature(feature):
                console = Console()
                console.print(f"[yellow]{get_upgrade_message(feature)}[/yellow]")
                raise typer.Exit(1)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator

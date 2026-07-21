"""Registry authentication command implementations."""

from __future__ import annotations

from mcp_manager.auth import AuthProfile, AuthStore, AuthType
from mcp_manager.commands.common import console
from mcp_manager.exceptions import McpManagerError
from mcp_manager.telemetry import track_command


def login_impl(
    url: str,
    token: str | None,
    user: str | None,
    password: str | None,
) -> None:
    """Store authentication credentials for a registry URL."""
    track_command("registry_login")

    if token:
        profile = AuthProfile(type=AuthType.BEARER, token=token)
    elif user and password:
        profile = AuthProfile(type=AuthType.BASIC, user=user, password=password)
    else:
        console.print(
            "[red]Provide --token (Bearer) or --user + --password (Basic).[/red]"
        )
        raise McpManagerError("Provide --token or --user + --password")

    store = AuthStore()
    store.load()

    # Warn if overwriting.
    existing = store.get(url)
    if existing:
        console.print(f"[yellow]Overwriting existing credentials for {url}[/yellow]")

    store.add(url, profile)
    store.save()

    # Check permissions.
    ok, msg = store.check_permissions()
    if not ok:
        console.print(f"[yellow]{msg}[/yellow]")

    masked = "****" if token else f"{user}:****"
    console.print(f"[green]Saved {profile.type.value} credentials for {url}[/green] ({masked})")


def logout_impl(url: str) -> None:
    """Remove stored authentication for a registry URL."""
    track_command("registry_logout")

    store = AuthStore()
    store.load()

    if store.remove(url):
        store.save()
        console.print(f"[green]Removed credentials for {url}[/green]")
    else:
        console.print(f"[yellow]No credentials found for {url}[/yellow]")


def auth_list_impl() -> None:
    """List stored registry authentication profiles."""
    track_command("registry_auth_list")

    store = AuthStore()
    store.load()

    profiles = store.list_all()
    if not profiles:
        console.print("[dim]No stored registry credentials.[/dim]")
        return

    # Check permissions and warn.
    ok, msg = store.check_permissions()
    if not ok:
        console.print(f"[yellow]{msg}[/yellow]")

    console.print(f"\n[bold]Stored registry credentials ({len(profiles)}):[/bold]\n")
    for url, profile in profiles:
        if profile.type == AuthType.BEARER:
            masked = f"Bearer {profile.token[:4]}****" if profile.token else "Bearer ****"
        else:
            masked = f"Basic {profile.user}:****" if profile.user else "Basic ****"
        console.print(f"  [cyan]{url}[/cyan] — {masked} ({profile.type.value})")
    console.print()

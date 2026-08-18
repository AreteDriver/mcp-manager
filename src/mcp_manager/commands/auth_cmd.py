"""Registry authentication command implementations."""

from __future__ import annotations

import logging
import sys

import httpx

from mcp_manager.auth import AuthProfile, AuthStore, AuthType
from mcp_manager.commands.common import console
from mcp_manager.exceptions import McpManagerError
from mcp_manager.oauth2 import OAuth2DeviceFlow, discover_oauth2_endpoints
from mcp_manager.telemetry import track_command

logger = logging.getLogger(__name__)


def login_oauth2_impl(url: str, client_id: str | None = None) -> None:
    """Perform OAuth2 device flow login for a registry URL."""
    track_command("registry_login_oauth2")

    console.print(f"[dim]Discovering OAuth2 endpoints for {url}...[/dim]")
    endpoints = discover_oauth2_endpoints(url)
    if endpoints is None:
        console.print(f"[red]OAuth2 device flow is not available for {url}.[/red]")
        console.print("[dim]The registry did not advertise device flow support in its")
        console.print("manifest or .well-known/oauth-authorization-server endpoint.[/dim]")
        raise McpManagerError(f"OAuth2 device flow not available for {url}")

    # Initiate device flow
    flow = OAuth2DeviceFlow(
        device_auth_url=endpoints.device_authorization,
        token_url=endpoints.token,
        client_id=client_id or "mcp-manager-cli",
    )

    console.print("[dim]Requesting device code from registry...[/dim]")
    device = flow.request_device_code()

    console.print("[bold]Registry supports OAuth2 device flow.[/bold]")
    console.print(f"1. Visit:  [cyan]{device.verification_uri}[/cyan]")
    console.print(f"2. Enter code: [bold]{device.user_code}[/bold]")
    console.print("3. Click 'Authorize'")
    console.print("[dim]Waiting for authorization...[/dim]")

    token_resp = flow.poll_token(device.device_code, interval=device.interval)

    # Build profile
    expires_at = None
    if token_resp.expires_in is not None:
        import time as _time

        expires_at = _time.time() + token_resp.expires_in

    profile = AuthProfile(
        type=AuthType.OAUTH2,
        token=token_resp.access_token,
        refresh_token=token_resp.refresh_token,
        expires_at=expires_at,
        token_url=endpoints.token,
    )

    store = AuthStore()
    store.load()

    existing = store.get(url)
    if existing:
        console.print(f"[yellow]Overwriting existing credentials for {url}[/yellow]")

    store.add(url, profile)
    store.save()

    ok, msg = store.check_permissions()
    if not ok:
        console.print(f"[yellow]{msg}[/yellow]")

    expiry_str = ""
    if token_resp.expires_in is not None:
        expiry_str = f" (expires in {token_resp.expires_in // 3600}h)"
    console.print(f"[green]Logged in to {url} via OAuth2[/green]{expiry_str}")


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
            "[red]Provide --token (Bearer) or --user + --password (Basic).[/red]\n"
            "[dim]Use --password-stdin for secure password entry.[/dim]"
        )
        raise McpManagerError("Provide --token or --user + --password")

    # Validate credentials before storing.
    _validate_credentials(url, profile)

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

    console.print(
        "[yellow]Note:[/yellow] credentials are stored in plaintext. "
        "Encrypt at rest or use a keyring integration if your threat model requires it."
    )

    masked = "****" if token else f"{user}:****"
    console.print(f"[green]Saved {profile.type.value} credentials for {url}[/green] ({masked})")


def _validate_credentials(url: str, profile: AuthProfile) -> None:
    """Validate credentials by making a HEAD request to the registry URL.

    Aborts with an error on 401/403. Proceeds with a warning on other
    non-success statuses (e.g. 405 Method Not Allowed).
    """
    headers = profile.to_headers()
    if not headers:
        return  # Nothing to validate.

    try:
        resp = httpx.head(url, headers=headers, timeout=10, follow_redirects=False)
    except httpx.HTTPError as exc:
        console.print(f"[yellow]Warning: could not validate credentials: {exc}[/yellow]")
        return

    if resp.status_code in (401, 403):
        console.print(
            f"[red]Authentication failed: HTTP {resp.status_code} "
            f"{resp.reason_phrase}[/red]\n"
            f"[dim]Credentials NOT stored.[/dim]"
        )
        raise McpManagerError(
            f"Authentication failed: HTTP {resp.status_code} {resp.reason_phrase}"
        )

    if not resp.is_success:
        console.print(
            f"[yellow]Warning: registry returned HTTP {resp.status_code} "
            f"{resp.reason_phrase} during validation. "
            f"Proceeding anyway.[/yellow]"
        )


def _revoke_token(token: str, token_url: str) -> bool:
    """Attempt to revoke a token via RFC 7009. Returns True on success."""
    import httpx

    payload = {
        "token": token,
        "token_type_hint": "access_token",
    }
    try:
        resp = httpx.post(token_url, data=payload, timeout=10)
        if resp.status_code in (200, 204):
            return True
        logger.debug("Token revocation returned HTTP %s: %s", resp.status_code, resp.text)
    except httpx.HTTPError as exc:
        logger.debug("Token revocation failed: %s", exc)
    return False


def logout_impl(url: str) -> None:
    """Remove stored authentication for a registry URL."""
    track_command("registry_logout")

    store = AuthStore()
    store.load()

    profile = store.get(url)
    if profile is None:
        console.print(f"[yellow]No credentials found for {url}[/yellow]")
        return

    # Attempt token revocation for OAuth2 profiles
    if profile.type == AuthType.OAUTH2 and profile.token and profile.token_url:
        revoked = _revoke_token(profile.token, profile.token_url)
        if revoked:
            console.print("[dim]Revoked token on server...[/dim] ✅")
        else:
            console.print("[yellow]Warning:[/yellow] server does not support token revocation.")
            console.print("[dim]Token may remain valid on server until expiry.[/dim]")

    store.remove(url)
    store.save()
    console.print(f"[green]Removed credentials for {url}[/green]")


def _read_password_stdin() -> str | None:
    """Read a single line from stdin and return it stripped.

    Returns None if stdin is a tty (no piped input) or empty.
    """
    if sys.stdin.isatty():
        return None
    try:
        return sys.stdin.readline().strip()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Public commands
# ---------------------------------------------------------------------------


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

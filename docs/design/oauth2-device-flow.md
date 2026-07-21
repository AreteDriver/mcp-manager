# Design: OAuth2 Device Flow for Registry Authentication

**Status:** Draft  
**Author:** AreteDriver  
**Date:** 2026-07-20  
**Version:** v0.8.0  
**Related:** ROADMAP.md (repo root), [authentication.md](../authentication.md)

---

## 1. Problem

v0.7.x registry authentication supports Bearer tokens and Basic auth via `--token` and `--password-stdin`. These are fine for machine tokens and CI, but they have real problems for human users:

- **Bearer tokens** from GitHub/GitLab are long-lived personal access tokens. Leaked in shell history, `ps`, and clipboard.
- **Basic auth** with `--password-stdin` is a UX crutch — it works, but it trains users to pipe secrets into CLI tools.
- **No expiry** — stored credentials live forever in `auth.json` unless manually revoked on the server.
- **No standard** — every registry implements auth differently. OAuth2 device flow is the industry-standard answer for CLI tools that can't host a redirect server.

The goal: make `mcp-manager registry login` feel as safe as `gh auth login`.

---

## 2. Goals

1. **Secure by default** — short-lived access tokens, automatic refresh, no long-lived secrets in `auth.json`
2. **No local server** — device flow works in headless containers, SSH sessions, and CI without port binding
3. **One command** — `mcp-manager registry login <url>` detects OAuth2 support and initiates device flow automatically
4. **Graceful degradation** — if a registry doesn't support OAuth2, fall back to Bearer/Basic with clear warnings
5. **Backward compatible** — existing `auth.json` profiles continue to work; migration is optional

## 3. Non-Goals

1. **Not a generic OAuth2 client** — we support device flow only. Authorization-code flow (browser redirect to `localhost`) is out of scope.
2. **Not an identity provider** — we don't issue tokens; we consume them from existing registries.
3. **Not SSO** — no SAML, OIDC discovery, or identity federation. One registry URL = one token pair.
4. **Not team RBAC** — role assignment happens on the registry server. The CLI only sends the token.

---

## 4. User Flow

### 4.1 Happy Path: Interactive Login

```bash
$ mcp-manager registry login https://registry.example.com/mcp.yaml
Registry supports OAuth2 device flow.

1. Visit:  https://registry.example.com/oauth/device?user_code=ABCD-EFGH
2. Enter code: ABCD-EFGH
3. Click "Authorize"

Waiting for authorization...
✅ Logged in to https://registry.example.com/mcp.yaml (expires in 8h)
```

### 4.2 Headless / CI

```bash
$ mcp-manager registry login https://registry.example.com/mcp.yaml \
    --token gho_xxx
Warning: OAuth2 device flow is available. Use it for interactive sessions.
✅ Logged in (Bearer token stored)
```

### 4.3 Auto-Refresh During Operations

```bash
$ mcp-manager registry diff https://registry.example.com/mcp.yaml
# Behind the scenes:
#   access_token expired 2 minutes ago
#   → refreshes silently using refresh_token
#   → proceeds with diff
```

### 4.4 Logout

```bash
$ mcp-manager registry logout https://registry.example.com/mcp.yaml
Revoked token on registry... ✅
Removed local profile. ✅
```

---

## 5. Data Model

### 5.1 Extended `AuthProfile`

```python
@dataclass(frozen=True)
class AuthProfile:
    type: AuthType  # bearer | basic | oauth2
    token: str | None = None          # Bearer token or OAuth2 access_token
    user: str | None = None           # Basic auth username
    password: str | None = None       # Basic auth password
    refresh_token: str | None = None  # OAuth2 refresh token
    expires_at: float | None = None   # Unix timestamp (seconds)
    token_url: str | None = None      # OAuth2 token endpoint (for refresh)
    added_at: float = field(default_factory=lambda: __import__("time").time())
```

**Migration:** Existing `auth.json` entries lack `refresh_token`, `expires_at`, and `token_url`. They deserialize with `None` defaults via `from_dict()` and behave as before (no refresh, no expiry check).

### 5.2 `AuthType` Extension

```python
class AuthType(StrEnum):
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"
```

### 5.3 Storage Format (`auth.json`)

```json
{
  "https://registry.example.com/mcp.yaml": {
    "type": "oauth2",
    "token": "gho_16char...",
    "refresh_token": "ghr_16char...",
    "expires_at": 1752993600.0,
    "token_url": "https://github.com/login/oauth/access_token",
    "added_at": 1752986400.0
  }
}
```

**Security:** `auth.json` retains `0o600` permissions. Refresh tokens are sensitive — same protection level as passwords.

---

## 6. Protocol: OAuth2 Device Flow (RFC 8628)

### 6.1 Discovery

Before initiating device flow, the CLI must discover whether the registry supports it. Two mechanisms:

**Mechanism A: Well-known endpoint (preferred)**

Registry exposes `.well-known/oauth-authorization-server` per [RFC 8414](https://tools.ietf.org/html/rfc8414):

```json
{
  "device_authorization_endpoint": "https://registry.example.com/oauth/device/code",
  "token_endpoint": "https://registry.example.com/oauth/token",
  "grant_types_supported": ["urn:ietf:params:oauth:grant-type:device_code"]
}
```

**Mechanism B: Registry metadata in MCP manifest**

The registry's `mcp.yaml` includes an `auth` block:

```yaml
auth:
  type: oauth2
  device_authorization_endpoint: https://registry.example.com/oauth/device/code
  token_endpoint: https://registry.example.com/oauth/token
```

**Discovery order:**
1. Fetch registry `mcp.yaml`, look for `auth` block
2. If not present, try `.well-known/oauth-authorization-server`
3. If neither present, fall back to Bearer/Basic prompt

### 6.2 Device Flow Steps

```
Step 1: CLI → Registry   POST /oauth/device/code
                         { "client_id": "mcp-manager-cli", "scope": "registry:read" }

         Registry → CLI   { "device_code": "...", "user_code": "ABCD-EFGH",
                            "verification_uri": "https://...", "expires_in": 1800,
                            "interval": 5 }

Step 2: CLI prints user_code + verification_uri to user

Step 3: User visits URI, enters code, clicks Authorize (in browser)

Step 4: CLI → Registry   POST /oauth/token
                         { "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                           "device_code": "...", "client_id": "mcp-manager-cli" }

         Poll every `interval` seconds. If "authorization_pending", retry.
         If "slow_down", increase interval by 5s.
         If "access_denied" or "expired_token", abort.

Step 5: Registry → CLI   { "access_token": "gho_...", "token_type": "bearer",
                            "refresh_token": "ghr_...", "expires_in": 28800 }

Step 6: CLI stores access_token, refresh_token, expires_at, token_url in auth.json
```

### 6.3 Token Refresh

```
CLI → Registry   POST /oauth/token
                  { "grant_type": "refresh_token",
                    "refresh_token": "ghr_...",
                    "client_id": "mcp-manager-cli" }

Registry → CLI   { "access_token": "gho_new...", "expires_in": 28800 }
                 (refresh_token may or may not rotate)
```

**Trigger conditions:**
- Before every `registry diff`, `registry pull`, or `registry info` if `expires_at - now() < 300` (5-minute buffer)
- On 401 responses during registry operations → attempt refresh once, then fail

**Failure handling:**
- Refresh token revoked or expired → prompt user to re-run `registry login`
- Network failure → log warning, use stale token (may 401, handled downstream)

---

## 7. CLI Changes

### 7.1 New Commands / Options

```python
# Auto-detect OAuth2 and initiate device flow
@app.command(name="registry-login")
def registry_login(
    url: str = typer.Argument(...),
    token: str | None = typer.Option(None, "--token"),
    user: str | None = typer.Option(None, "--user"),
    password: str | None = typer.Option(None, "--password"),
    password_stdin: bool = typer.Option(False, "--password-stdin"),
    oauth2: bool = typer.Option(False, "--oauth2", help="Force OAuth2 device flow"),
    no_oauth2: bool = typer.Option(False, "--no-oauth2", help="Skip OAuth2 discovery, use token/password"),
):
```

**Logic:**
- If `--oauth2`: initiate device flow unconditionally
- If `--no-oauth2`: skip discovery, require `--token` or `--user + --password`
- If neither: discover registry capabilities
  - Supports OAuth2 → ask user: "Registry supports OAuth2. Use it? [Y/n]"
  - User says yes → device flow
  - User says no or registry doesn't support → Bearer/Basic fallback

### 7.2 `auth-list` Output

```
$ mcp-manager registry auth-list
Registry                                    Type     Expires                  Masked
──────────────────────────────────────────  ───────  ───────────────────────  ─────────
https://registry.example.com/mcp.yaml        oauth2   2026-07-21 02:00 UTC     gho_••••xYz9
https://legacy.example.com/mcp.yaml        bearer   —                        ghp_••••AbC1
```

### 7.3 New Internal Modules

```
src/mcp_manager/
├── oauth2.py          # Device flow client + refresh logic
├── auth.py            # Extended AuthProfile (existing)
└── commands/
    ├── auth_cmd.py    # Updated login_impl with OAuth2 branch
    └── ...
```

---

## 8. Security Considerations

| Risk | Mitigation |
|------|------------|
| Refresh token leaked from `auth.json` | Same `0o600` file permissions as passwords |
| Device code phishing | Print `verification_uri` exactly as received from server; never construct it client-side |
| Token refresh loop on revocation | After one refresh failure + 401, abort and instruct user to re-login |
| Short `expires_in` from registry | Respect server value; if absent, default to 1 hour |
| `client_secret` required by some token endpoints | Use `client_id` only (public client per RFC 8628 §2). If registry requires secret, document it as unsupported. |
| Token transmission over HTTP | Discovery fails with warning if token endpoint is HTTP. Require HTTPS. |

---

## 9. Error Handling

| Scenario | Behavior |
|----------|----------|
| Registry doesn't support device flow | Fallback to Bearer/Basic with warning |
| User denies authorization | Print "Authorization denied by user." Exit 1 |
| Device code expires | Print "Login timed out. Try again." Exit 1 |
| Network error during polling | Retry with exponential backoff up to 3×, then fail |
| Refresh token expired/revoked | Print "Session expired. Run: mcp-manager registry login <url>" Exit 1 |
| Registry returns invalid JSON in discovery | Warn, skip OAuth2, fallback to manual token entry |

---

## 10. Testing Strategy

### 10.1 Unit Tests (`tests/test_oauth2.py`)

- Device flow state machine: `authorization_pending` → success
- `slow_down` interval increase
- `access_denied` and `expired_token` terminal states
- Token refresh: success, rotation, revocation
- Discovery: well-known endpoint, manifest auth block, neither
- `AuthProfile` serialization round-trip with new fields

### 10.2 Integration Tests

- Mock OAuth2 server (FastAPI or `respx`) with full device flow + refresh endpoints
- End-to-end: `registry login --oauth2` → mock user approval → verify stored profile
- Auto-refresh: expire token → trigger diff → verify refresh POST before diff GET

### 10.3 Manual QA

- Real GitHub OAuth2 device flow (if they expose it for apps) or mock registry
- Headless container (`docker run` without TTY)
- SSH session with `export TERM=xterm`

---

## 11. Dependencies

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    ...
    "respx>=0.22",  # already present for HTTP mocking
]
```

No new runtime dependencies. Device flow is pure HTTP POST + polling; we use `httpx` (already a dependency).

---

## 12. Rollout Plan

| Week | Milestone | Deliverable |
|------|-----------|-------------|
| 1 | Discovery + Data Model | `oauth2.py` module, extended `AuthProfile`, discovery logic, unit tests |
| 2 | Device Flow + Login | `registry login --oauth2`, polling loop, user output, error handling, integration tests |
| 3 | Auto-Refresh + Polish | `resolve_auth_headers()` refresh trigger, `auth-list` expiry column, docs, ROADMAP |
| 4 | Release | Version bump to v0.8.0, CHANGELOG, tag, release workflow |

---

## 13. Open Questions

1. **Do we need a `client_id` registry?** Should `mcp-manager` use a single hardcoded `client_id="mcp-manager-cli"`, or should each registry vendor register their own? (Lean: single hardcoded, per `gh` and `glab` precedent.)
2. **Token revocation on logout?** Should `registry logout` POST to a revocation endpoint if the registry advertises one? (Lean: yes, best-effort, don't fail logout if revocation fails.)
3. **Scope negotiation?** Should the CLI request `registry:read registry:write` or just `registry:read`? (Lean: minimal scope, document extensibility.)

---

*End of document*

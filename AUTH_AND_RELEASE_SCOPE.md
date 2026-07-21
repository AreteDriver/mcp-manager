# v0.7.0 Scope: Authentication Hardening + Release Automation

## Problem Statement

v0.6.0 shipped registry auth (`--token`, `--user/--password`, `--header`) but tokens passed as CLI args are **insecure by default** — they appear in:
- Shell history (`~/.bash_history`)
- Process listings (`ps aux`)
- CI logs
- Terminal scrollback

There is no persistent credential store, no env-var fallback, and no validation that credentials work before they're used.

## v0.7.0 Goals

1. **Credential Storage** — secure profiles for registry auth
2. **Env-Var Fallback** — `MCP_MANAGER_REGISTRY_TOKEN` etc.
3. **Credential Validation** — `registry login` verifies before storing
4. **Release Automation** — PyPI publish + GitHub release notes from CHANGELOG

---

## Week 1: Auth Profiles + `registry login/logout`

### CLI Surface

```bash
# Store credentials for a registry URL
mcp-manager registry login https://reg.example.com/mcp.yaml --token ghp_xxx
mcp-manager registry login https://reg.example.com/mcp.yaml --user alice --password secret

# List stored profiles
mcp-manager registry auth-list

# Remove a profile
mcp-manager registry logout https://reg.example.com/mcp.yaml
```

### Storage

- **Location:** `~/.mcp-manager/auth.json`
- **Format:** JSON mapping `normalized_url` → `{type, credentials, added_at}`
- **Permissions:** `0o600` (owner read/write only)
- **Types:** `bearer`, `basic`
- **Normalization:** strip trailing slash, lowercase scheme+host

```json
{
  "https://reg.example.com/mcp.yaml": {
    "type": "bearer",
    "token": "ghp_xxx",
    "added_at": 1753027200.0
  }
}
```

### Security

- Warn if file permissions are too permissive on load
- Never print credentials in output
- `--token` on CLI still works but prints a one-line stderr warning:
  `[yellow]Warning: passing tokens via CLI is insecure. Use `registry login` instead.[/yellow]`

### Integration

- `registry diff` and `registry pull` automatically load matching auth profile
- CLI flags (`--token`, `--user`) override stored profile
- No profile + no flags → anonymous request (backward compatible)

### Tests (~10)

1. `login` stores bearer token correctly
2. `login` stores basic auth correctly
3. `auth-list` shows stored profiles (masks credentials)
4. `logout` removes profile
5. `diff` auto-loads matching profile
6. CLI `--token` overrides stored profile
7. File created with `0o600`
8. Warn on overly permissive file
9. Normalize URL matching (trailing slash insensitive)
10. `login` with invalid URL → error

---

## Week 2: Env-Var Fallback + Credential Validation

### Env Vars

| Var | Used When |
|-----|-----------|
| `MCP_MANAGER_REGISTRY_TOKEN` | Default Bearer token when no profile or CLI flag |
| `MCP_MANAGER_REGISTRY_USER` / `MCP_MANAGER_REGISTRY_PASSWORD` | Default Basic auth |
| `MCP_MANAGER_AUTH_FILE` | Override auth.json path |

Priority (highest first):
1. CLI flag (`--token`, `--user`)
2. Stored profile for URL
3. Env var
4. Anonymous

### Credential Validation

`registry login` does a HEAD request to the registry URL with the provided credentials before storing. If `401` or `403`, abort with error and do NOT write to auth.json.

```
$ mcp-manager registry login https://bad.example.com --token wrong
[red]Authentication failed: HTTP 401 Unauthorized[/red]
Credentials NOT stored.
```

### Tests (~6)

1. Env-var token used when no profile
2. Env-var basic auth used when no profile
3. CLI flag > profile > env var priority
4. `login` with 401 → no storage
5. `login` with 200 → storage
6. Custom `MCP_MANAGER_AUTH_FILE` respected

---

## Week 3: Release Automation

### PyPI Publish Workflow

`.github/workflows/release.yml`:
- Trigger: tag push `v*.*.*`
- Steps:
  1. Checkout
  2. Set up Python 3.11
  3. `pip install build twine`
  4. `python -m build`
  5. `twine upload dist/*` (via OIDC / trusted publisher)

### GitHub Release Notes

`.github/workflows/release.yml` (same workflow):
- Extract version section from CHANGELOG.md
- Create GitHub Release with auto-generated + CHANGELOG body
- Uses `gh release create` or `softprops/action-gh-release`

### Version Guard

CI gate: `__version__` in `__init__.py` must match the tag being pushed (minus `v` prefix).

### Tests (~4)

1. Build succeeds (`python -m build`)
2. Version guard detects mismatch
3. CHANGELOG extraction parses correctly
4. Release workflow YAML valid (schema lint)

---

## Week 4: Polish, Docs, v0.7.0 Release

### Polish

- `--help` text for all new commands
- README section: "Private Registries & Authentication"
- MkDocs page: `docs/authentication.md`
- `mcp-manager registry login --help` includes security warning

### Coverage

- Maintain ≥90% coverage
- New auth module: `src/mcp_manager/auth.py` (~8 tests)
- New auth commands: `src/mcp_manager/commands/auth_cmd.py` (~6 tests)

### Release

- Version bump: `0.6.0` → `0.7.0`
- CHANGELOG entry
- Tag + push → auto-publish to PyPI + GitHub Release

---

## Files to Create

- `src/mcp_manager/auth.py` — `AuthStore`, `AuthProfile`, `load_auth_for_url()`
- `src/mcp_manager/commands/auth_cmd.py` — `login`, `logout`, `auth_list` implementations
- `tests/test_auth.py` — auth store tests
- `tests/test_auth_cli.py` — auth CLI tests
- `.github/workflows/release.yml` — publish + release notes

## Files to Modify

- `src/mcp_manager/commands/registry_cmd.py` — auto-load auth profiles
- `src/mcp_manager/cli.py` — add `auth-list`, `login`, `logout` commands under `registry_app`
- `README.md` — auth section
- `CHANGELOG.md` — v0.7.0 entry
- `pyproject.toml` / `__init__.py` — version bump

## Estimate

- Week 1 (auth profiles): ~4 hrs
- Week 2 (env var + validation): ~3 hrs
- Week 3 (release automation): ~3 hrs
- Week 4 (polish + release): ~2 hrs
- **Total: ~12 hrs**

## Out of Scope (v0.8.0+)

- OAuth2 / device code flow
- Keyring / system credential store integration
- Token refresh / expiration handling
- Role-based access control (RBAC) for team registries
- Encrypted-at-rest credential storage (Fernet / age)

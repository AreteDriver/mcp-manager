# Authentication

Authenticate against private registries so `mcp-manager registry diff` and `registry pull` can fetch server definitions behind HTTP Basic or Bearer auth.

---

## Quickstart

```bash
# Store a Bearer token — validates before saving via HEAD request
mcp-manager registry login https://reg.example.com/mcp.yaml --token ghp_xxx

# Store Basic auth credentials
mcp-manager registry login https://reg.example.com/mcp.yaml --user alice --password secret

# List stored profiles (credentials are masked)
mcp-manager registry auth-list

# Remove a profile
mcp-manager registry logout https://reg.example.com/mcp.yaml
```

---

## Storage

Credentials live in `~/.mcp-manager/auth.json`:

- **Permissions:** `0o600` (owner read/write only)
- **Format:** JSON mapping normalized URL → `{type, credentials, added_at}`
- **Override:** set `MCP_MANAGER_AUTH_FILE` to use a custom path

Example file:

```json
{
  "https://reg.example.com/mcp.yaml": {
    "type": "bearer",
    "token": "ghp_xxx",
    "added_at": 1753027200.0
  }
}
```

---

## Auth Priority Chain

When `registry diff` or `registry pull` needs credentials, the following priority applies (highest wins):

1. **CLI flag** — `--token` or `--user` + `--password`
2. **Stored profile** — matching registry URL in `auth.json`
3. **Environment variable** — `MCP_MANAGER_REGISTRY_TOKEN` (Bearer) or `MCP_MANAGER_REGISTRY_USER` / `MCP_MANAGER_REGISTRY_PASSWORD` (Basic)
4. **Anonymous** — no authentication headers sent

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `MCP_MANAGER_REGISTRY_TOKEN` | Default Bearer token |
| `MCP_MANAGER_REGISTRY_USER` | Default Basic auth username |
| `MCP_MANAGER_REGISTRY_PASSWORD` | Default Basic auth password |
| `MCP_MANAGER_AUTH_FILE` | Override `~/.mcp-manager/auth.json` path |

These are useful in CI pipelines where you don't want to run `registry login` interactively.

---

## Security

- **Never commit tokens.** `auth.json` is already in your `~/.mcp-manager/` directory, outside any repo.
- **CLI flags are insecure.** `--token` appears in shell history (`~/.bash_history`) and process listings (`ps aux`). Prefer stored credentials or env vars.
- **Validation on login.** `registry login` makes a `HEAD` request before storing. If the server returns `401` or `403`, credentials are **not** saved.
- **File permissions.** `auth.json` is created with `0o600`. A warning is printed if the file is too permissive.

---

## Troubleshooting

### Login fails with "Authentication failed: HTTP 401"

The credentials were rejected by the registry. Double-check the token or username/password. Credentials are **not** stored on failure.

### "Warning: registry returned HTTP 405 during validation"

Some registries don't support `HEAD` requests. The warning is informational — credentials are still stored if you trust the URL.

### Registry diff doesn't use my stored profile

- Ensure the URL matches exactly (trailing slashes are normalized, but paths must match).
- Check with `mcp-manager registry auth-list` that the profile exists.
- Verify `MCP_MANAGER_AUTH_FILE` isn't pointing to a different file.

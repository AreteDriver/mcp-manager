# Configuration Reference

Everything you can put in `.mcp-manager.yml`.

---

## Top-Level Keys

```yaml
project: my-project          # Required: project name
extends: base.yml            # Optional: inherit from another config
servers: {}                  # Required: server definitions
```

---

## Servers

### stdio Server

```yaml
servers:
  my-local-server:
    command: node
    args: ["./dist/index.js"]
    env:
      DATABASE_URL: ${DATABASE_URL}
    tags: [backend, database]
```

### SSE Server

```yaml
servers:
  my-remote-server:
    type: sse
    url: http://localhost:3000/sse
    headers:
      Authorization: Bearer ${API_KEY}
    tags: [frontend]
```

### HTTP Server

```yaml
servers:
  slack-webhook:
    type: http
    url: https://hooks.slack.com/services/xxx
    headers:
      Content-Type: application/json
    tags: [communication]
```

---

## Environment Variable Syntax

Values in `env:` support shell-compatible resolution:

| Syntax | Behavior | Example |
|--------|----------|---------|
| `$VAR` | Replaced with env var value, or literal if unset | `DATABASE_URL: $DB_URL` |
| `${VAR}` | Same as above | `DATABASE_URL: ${DB_URL}` |
| `${VAR:-default}` | Falls back to default if unset | `SECRET: ${API_KEY:-dev-key}` |
| `${VAR:?error}` | Raises error if unset (blocks CI) | `SECRET: ${API_KEY:?required}` |

Validation skips `${VAR:-default}` (it has an explicit fallback) but flags bare `$VAR` and `${VAR:?required}` if unset.

---

## Tags

Add `tags:` to any server to group and filter:

```yaml
servers:
  postgres:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-postgres"]
    tags: [backend, database]
```

Filter commands by tag:

```bash
mcp-manager health --tag backend
mcp-manager sync --ide cursor --exclude-tag experimental
mcp-manager monitor --tag production
```

---

## Config Inheritance (`extends:`)

Share common server definitions across projects:

```yaml
# .mcp-manager.yml
extends: github:AreteDriver/mcp-manager/base.yml@v0.5.0

project: my-service
servers:
  my-local-server:
    command: node
    args: ["./dist/index.js"]
```

Resolution order (last wins):

1. Base config (from `extends:`)
2. Project `.mcp-manager.yml`
3. Environment variable overrides

Supported `extends` formats:

| Format | Example |
|--------|---------|
| Relative file | `extends: base.yml` |
| Absolute file | `extends: file:///home/user/base.yml` |
| GitHub | `extends: github:AreteDriver/mcp-manager/base.yml@v0.5.0` |
| HTTPS | `extends: https://example.com/base.yml` |
| List | `extends: [base1.yml, base2.yml]` |

---

## Validation

Run `mcp-manager validate` to check your config:

- YAML syntax valid
- Every server has `command` or `url`
- Referenced env vars are present (skips `:-` syntax)
- Commands exist on PATH (best-effort)

With `--strict`, also runs deep health checks on all servers.

---

## Lockfile

Pin exact versions for reproducible CI:

```bash
mcp-manager lock                    # Generate .mcp-manager.lock
mcp-manager lock --check            # CI gate: fail if out of date
```

Example `.mcp-manager.lock`:

```json
{
  "version": "1",
  "servers": {
    "filesystem": {
      "resolved_version": "2025.1.15",
      "last_checked": "2026-07-20T14:30:00Z"
    }
  }
}
```

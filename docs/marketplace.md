# MCP Manager Marketplace

The **MCP Manager Marketplace** is a curated directory of MCP servers that you can discover, inspect, and install directly from the CLI.

---

## Quick Start

```bash
# Search for servers
mcp-manager search filesystem
mcp-manager search --category Database

# View details before installing
mcp-manager info postgres

# Install a server into your project
mcp-manager install postgres

# Install and auto-generate lockfile
mcp-manager install postgres --lock
```

---

## Commands

### `search`

Search the marketplace by name, description, or category.

```bash
mcp-manager search <query> [options]
```

**Options:**
- `--category, -c <name>` — Filter by category (e.g., `Database`, `Filesystem`)
- `--include-unverified` — Show servers that haven't been manually verified
- `--json` — Output results as JSON

**Examples:**

```bash
# Search by keyword
mcp-manager search postgres

# List all servers in a category
mcp-manager search "" --category Database

# Include unverified servers
mcp-manager search filesystem --include-unverified
```

**Default behavior:** Only verified servers are shown. Use `--include-unverified` to browse the full catalog.

---

### `info`

Show detailed information about a specific marketplace server.

```bash
mcp-manager info <name> [options]
```

**Options:**
- `--json` — Output as JSON

**Example:**

```bash
mcp-manager info postgres
# Name:        PostgreSQL MCP
# Repository:  https://github.com/modelcontextprotocol/server-postgres
# License:     MIT
# Install:
#   command: npx
#   args: ["-y", "@modelcontextprotocol/server-postgres"]
#   env:
#     DATABASE_URL: ${DATABASE_URL}
```

---

### `install`

Add a marketplace server to your project's `.mcp-manager.yml`.

```bash
mcp-manager install <name> [options]
```

**Options:**
- `--path, -p <dir>` — Target project directory (default: current directory)
- `--dry-run` — Preview changes without writing
- `--no-prompt` — Skip interactive env var prompts
- `--lock` — Auto-generate `.mcp-manager.lock` after install

**Examples:**

```bash
# Interactive install (prompts for env vars)
mcp-manager install postgres

# Non-interactive (keeps ${VAR} placeholders)
mcp-manager install postgres --no-prompt

# Install and pin versions
mcp-manager install postgres --lock

# Preview only
mcp-manager install postgres --dry-run
```

**Environment variables:** If a server requires env vars like `${DATABASE_URL}`, the CLI will prompt you interactively. Use `--no-prompt` to keep placeholders and set them later.

---

### `marketplace-refresh`

Refresh quality scores for all marketplace servers. This is typically run by CI, not manually.

```bash
mcp-manager marketplace-refresh --output marketplace/index.yaml
```

**Options:**
- `--output, -o <path>` — Path to `index.yaml` (required)
- `--timeout, -t <seconds>` — Health check timeout (default: 30)
- `--dry-run` — Preview score changes without writing

---

## Quality Scores

Each marketplace server carries a quality score computed by automated health checks:

| Score | Badge | Meaning |
|---|---|---|
| ≥0.9 | 🟢 Verified | Deep check passes, updated recently |
| ≥0.5 | 🟡 Functional | Deep check passes, may be stale |
| <0.5 | 🔴 Unstable | Fails deep check |
| Unmeasured | ⬜ Unknown | Not yet evaluated |

Scores are refreshed automatically via the `marketplace-refresh` CI job.

---

## Curated Servers

The marketplace ships with official MCP reference servers:

| Name | Category | Description |
|---|---|---|
| `filesystem` | Filesystem | Secure filesystem access |
| `postgres` | Database | PostgreSQL database queries |
| `sqlite` | Database | SQLite database operations |
| `github` | Git | GitHub repo and PR management |
| `slack` | Communication | Slack workspace messaging |
| `puppeteer` | Browser | Web browser automation |

---

## Security

- **Curated only:** Only maintainers can add entries via PR
- **Install is config-only:** `mcp-manager install` writes YAML, it never executes `npm install` or clones repositories
- **Transparent scoring:** All quality data is in the repo; audit CI logs for verification

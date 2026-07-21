# Quickstart

Get mcp-manager running in under 2 minutes.

---

## 1. Install

```bash
pip install arete-mcp
```

Verify it works:

```bash
mcp-manager --version
```

---

## 2. Discover Your Servers

See every MCP server configured across all your IDEs:

```bash
mcp-manager list
```

Example output:

```text
 Name        Transport   Source         Tags           Target
 ─────────────────────────────────────────────────────────────
 filesystem  stdio       claude-code    core, fs       npx -y @modelcontextprotocol/server-filesystem
 postgres    stdio       project        backend, db    npx -y @modelcontextprotocol/server-postgres
 slack       http        cursor         communication  https://mcp.slack.com/mcp
```

---

## 3. Check Health

Make sure they actually work:

```bash
mcp-manager health --deep
```

This spawns each stdio server, runs the MCP handshake, calls `tools/list`, and validates dependencies are on PATH.

---

## 4. Scaffold a Project Config

For a new project, use the onboarding wizard:

```bash
cd my-project
mcp-manager init
```

This will:

1. Detect your installed IDE
2. Offer to import existing servers
3. Create `.mcp-manager.yml` with a template
4. Update `.gitignore`

Or skip the wizard and use a template directly:

```bash
mcp-manager template use python
```

---

## 5. Sync to Your IDE

Preview changes without touching anything:

```bash
mcp-manager sync --ide cursor --dry-run
```

Then commit:

```bash
mcp-manager sync --ide cursor
```

Your Cursor config (`~/.cursor/mcp.json`) is updated atomically with a backup created first.

---

## 6. Validate in CI

Add this to `.github/workflows/mcp-validate.yml`:

```yaml
name: MCP Validate
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install arete-mcp
      - run: mcp-manager validate --strict
```

Catches missing env vars, broken commands, and failing servers before merge.

---

## Next Steps

- Read the [Configuration Reference](configuration.md)
- Learn about [Team Features](team.md)
- Check [IDE Support](ide-support.md) for per-IDE specifics

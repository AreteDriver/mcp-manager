# Team Features

mcp-manager is built for teams. Here's how to use it at scale.

---

## Onboarding Wizard

New team members run one command:

```bash
mcp-manager init
```

This:

1. Detects their client targets (Codex, Claude Code, Cursor, Windsurf)
2. Imports existing servers from client-native config
3. Creates `.mcp-manager.yml` from a template
4. Leaves `.mcp-manager.yml` and `.mcp-manager.lock` ready to commit for team sharing

Non-interactive mode (for CI or scripts):

```bash
mcp-manager init --yes --template python --project-name my-service
```

---

## Shared Configs with `extends:`

Create a base config in your organization repo:

```yaml
# github:your-org/mcp-configs/base.yml@main
project: base
servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem"]
    tags: [core]
  git:
    command: uvx
    args: ["mcp-server-git", "--repository", "."]
    tags: [core]
```

Then in each project:

```yaml
# .mcp-manager.yml
extends: github:your-org/mcp-configs/base.yml@main

project: api-service
servers:
  postgres:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-postgres"]
    env:
      DATABASE_URL: ${DATABASE_URL}
    tags: [backend, database]
```

The project config inherits from base and can override servers with the same name.

---

## Server Tags

Tag servers by environment, team, or purpose:

```yaml
servers:
  postgres:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-postgres"]
    tags: [backend, database, production]
  stripe-mcp:
    command: npx
    args: ["-y", "@stripe/mcp"]
    tags: [backend, payment, production]
  playwright:
    command: npx
    args: ["-y", "@anthropic-ai/playwright-mcp"]
    tags: [frontend, experimental]
```

Then filter across commands:

```bash
# Health check only production servers
mcp-manager health --tag production

# Sync only stable servers to Cursor
mcp-manager sync --ide cursor --exclude-tag experimental

# Monitor backend servers only
mcp-manager monitor --tag backend
```

---

## Project Templates

Standardize new repos with built-in templates:

```bash
mcp-manager template list
# python  — filesystem + git (mypy + ruff CI gate)
# node    — filesystem + git (npm audit CI gate)
# data    — postgres + filesystem + git
# ai      — web search + browser automation

mcp-manager template use data --project-name analytics-pipeline
```

---

## CI Integration

Validate `.mcp-manager.yml` on every PR:

```yaml
# .github/workflows/mcp-validate.yml
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

With `--strict`, also runs deep health checks (spawns servers, validates tools/list).

---

## Version Pinning

Ensure every team member uses identical server versions:

```bash
# Generate lockfile
mcp-manager lock

# Commit .mcp-manager.lock to git
# CI validates it hasn't drifted
mcp-manager lock --check
```

The lockfile records resolved npm versions for `npx`-based servers.

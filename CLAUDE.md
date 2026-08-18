# Claude Code Notes

Follow the canonical repository guidance in `AGENTS.md`.

Claude Code uses `~/.claude.json` for user-scoped MCP servers and `.mcp.json`
with an `mcpServers` wrapper for shared project-scoped servers. Preserve support
for the legacy top-level project form when changing discovery, but always write
the official wrapped form.

Before handing off a change, run the verification commands in `AGENTS.md` and
confirm that no config preview or diagnostic output exposes credential values.

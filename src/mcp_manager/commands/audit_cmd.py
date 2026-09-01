"""mcp-manager audit command implementations."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

from rich.table import Table

from mcp_manager.audit.engine import build_fastmcp_server, get_builtin_spec_path, probe_summary
from mcp_manager.audit.spec import load_spec
from mcp_manager.commands.common import console
from mcp_manager.exceptions import McpManagerError
from mcp_manager.telemetry import track_command


def _resolve_spec(probe_spec: Path | None) -> Path:
    """Resolve the probe spec path, falling back to built-in."""
    if probe_spec is not None:
        if not probe_spec.exists():
            raise McpManagerError(f"Probe spec not found: {probe_spec}")
        return probe_spec
    builtin = get_builtin_spec_path()
    if not builtin.exists():
        raise McpManagerError(
            "Built-in probe spec not found. Install mcp-manager with audit extras, "
            "or provide --probe-spec explicitly."
        )
    return builtin


def audit_list_impl(probe_spec: Path | None) -> None:
    """List probes in a spec."""
    track_command("audit_list")
    try:
        spec_path = _resolve_spec(probe_spec)
    except McpManagerError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise
    spec = load_spec(spec_path)
    table = Table(title=f"{spec.name} — {len(spec.probes)} probe(s)")
    table.add_column("ID", style="cyan")
    table.add_column("Cat", justify="right")
    table.add_column("Tool")
    table.add_column("Registered description", overflow="fold")
    table.add_column("Actual behavior", overflow="fold")
    for p in spec.probes:
        table.add_row(
            p.probe_id,
            str(p.category),
            p.registered_name,
            p.registered_description,
            p.actual_behavior,
        )
    console.print(table)


def audit_runbook_impl(probe_spec: Path | None, output: Path | None) -> None:
    """Print a markdown runbook for human verification."""
    track_command("audit_runbook")
    try:
        spec_path = _resolve_spec(probe_spec)
    except McpManagerError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise
    spec = load_spec(spec_path)
    lines = [
        f"# mcp-manager audit runbook — {spec.name}",
        "",
        f"{spec.description}",
        "",
        "## Verification protocol",
        "",
        "1. Start the harness server in one terminal:",
        "",
        "   ```bash",
        f"   mcp-manager audit serve --probe-spec {spec_path}",
        "   ```",
        "",
        "2. Attach the server to Claude Code (`claude mcp add` or via .claude/mcp.json).",
        "",
        "3. For each probe, ask Claude Code to invoke the tool.",
        "   **Read the permission prompt carefully** before approving.",
        "",
        "4. For each probe, fill in the OBSERVED column. A finding is any case where",
        "   the prompt's display does not faithfully reflect what `actual_behavior`",
        "   says the tool would do.",
        "",
        "## Probes",
        "",
    ]
    for p in spec.probes:
        lines += [
            f"### {p.probe_id}  (Category {p.category})",
            "",
            f"- **Summary:** {p.summary}",
            f"- **Tool name:** `{p.registered_name}`",
            f"- **Registered description (should appear in prompt):** {p.registered_description}",
            f"- **Actual behavior (in spec):** {p.actual_behavior}",
            f"- **Expected finding:** {p.expected_finding}",
            "- **OBSERVED in prompt:** _(fill in)_",
            "- **Finding?** _(yes/no — yes if observed prompt did not faithfully reflect spec)_",
            "",
        ]
    runbook_text = "\n".join(lines)
    if output is not None:
        output.write_text(runbook_text, encoding="utf-8")
        console.print(f"[green]Wrote runbook to:[/green] {output}")
    else:
        console.print(runbook_text)


def audit_serve_impl(
    probe_spec: Path | None,
    transport: str,
) -> None:
    """Run the MCP server that registers all probes in a spec."""
    track_command("audit_serve")
    try:
        spec_path = _resolve_spec(probe_spec)
    except McpManagerError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise
    spec = load_spec(spec_path)
    console.print(
        f"[bold]mcp-manager audit[/bold] serving {len(spec.probes)} probe(s) "
        f"from {spec.name} ({spec_path})",
        style="cyan",
    )
    console.print("\n[dim]Probe summary (for human verification):[/dim]")
    console.print(json_mod.dumps(probe_summary(spec), indent=2))
    console.print(
        "\n[bold yellow]Starting MCP server. "
        "Attach to Claude Code and exercise probes.[/bold yellow]\n"
    )
    server = build_fastmcp_server(spec)
    if transport == "stdio":
        server.run(transport="stdio")
    elif transport == "sse":
        server.run(transport="sse")
    elif transport == "streamable-http":
        server.run(transport="streamable-http", stateless_http=True)
    else:
        raise McpManagerError(
            f"Unsupported audit transport: {transport}. Expected stdio, sse, or streamable-http."
        )

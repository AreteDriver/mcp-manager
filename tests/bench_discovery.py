"""Benchmarks for config discovery operations."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_manager.discovery import ConfigDiscovery


def _make_claude_config(servers: int) -> dict:
    return {
        "mcpServers": {
            f"server-{i}": {
                "command": "npx",
                "args": ["-y", f"pkg{i}"],
            }
            for i in range(servers)
        }
    }


def test_bench_discover_tool_20_servers(benchmark, tmp_path: Path) -> None:
    """Benchmark scanning a single IDE config with 20 servers."""
    config_path = tmp_path / "claude.json"
    config_path.write_text(json.dumps(_make_claude_config(20)))

    discovery = ConfigDiscovery()
    # Monkeypatch the IDE path to our temp file
    discovery._scan_config = lambda tool, path, wrapper: discovery.__class__._scan_config(
        discovery, tool, config_path, "mcpServers"
    )

    def _run() -> list:
        return discovery.discover_tool("claude-code")

    result = benchmark(_run)
    assert len(result) == 20


def test_bench_discover_all_with_project(benchmark, tmp_path: Path) -> None:
    """Benchmark scanning all IDE configs plus project configs."""
    # Set up a fake claude config
    claude_path = tmp_path / "claude.json"
    claude_path.write_text(json.dumps(_make_claude_config(10)))

    # Set up a fake project config (flat server dict, no wrapper key)
    project_path = tmp_path / ".mcp.json"
    project_path.write_text(json.dumps(_make_claude_config(5)["mcpServers"]))

    discovery = ConfigDiscovery()
    # Override IDE path
    original_scan = discovery._scan_config

    def _patched_scan(tool: str, path: Path, wrapper: str | None) -> list:
        if tool == "claude-code":
            return original_scan(tool, claude_path, wrapper)
        if tool == "project":
            return original_scan(tool, path, wrapper)
        return []

    discovery._scan_config = _patched_scan

    def _run() -> list:
        return discovery.discover_all(project_dir=tmp_path)

    result = benchmark(_run)
    assert len(result) == 15

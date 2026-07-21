"""Benchmarks for sync/export/import operations."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mcp_manager.exporters import export_servers, import_servers
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType
from mcp_manager.writeback import ConfigWriteback


def _make_servers(n: int) -> list[McpServer]:
    servers: list[McpServer] = []
    for i in range(n):
        if i % 3 == 0:
            servers.append(
                McpServer(
                    name=f"stdio-{i}",
                    transport=TransportType.STDIO,
                    stdio_config=StdioConfig(command="npx", args=["-y", f"pkg{i}"]),
                )
            )
        elif i % 3 == 1:
            servers.append(
                McpServer(
                    name=f"http-{i}",
                    transport=TransportType.HTTP,
                    network_config=NetworkConfig(type="http", url=f"https://api{i}.example.com/mcp"),
                )
            )
        else:
            servers.append(
                McpServer(
                    name=f"sse-{i}",
                    transport=TransportType.SSE,
                    network_config=NetworkConfig(type="sse", url=f"https://sse{i}.example.com/events"),
                )
            )
    return servers


def test_bench_export_yaml_50(benchmark, tmp_path: Path) -> None:
    servers = _make_servers(50)
    out = tmp_path / "export.yaml"

    def _run() -> None:
        export_servers(servers, out)

    benchmark(_run)
    assert out.exists()


def test_bench_export_json_50(benchmark, tmp_path: Path) -> None:
    servers = _make_servers(50)
    out = tmp_path / "export.json"

    def _run() -> None:
        export_servers(servers, out, fmt="json")

    benchmark(_run)
    assert out.exists()


def test_bench_import_yaml_50(benchmark, tmp_path: Path) -> None:
    servers = _make_servers(50)
    out = tmp_path / "export.yaml"
    export_servers(servers, out)

    def _run() -> list[McpServer]:
        return import_servers(out)

    result = benchmark(_run)
    assert len(result) == 50


def test_bench_writeback_preview_20(benchmark, tmp_path: Path) -> None:
    servers = _make_servers(20)
    writeback = ConfigWriteback()
    # Point to a non-existent path so preview builds a fresh dict
    writeback._ide_configs["claude-code"] = (tmp_path / "nonexistent.json", "mcpServers")

    def _run() -> dict:
        return writeback.preview("claude-code", servers)

    result = benchmark(_run)
    assert len(result["mcpServers"]) == 20

"""Tests for server monitor (monitor.py)."""

from __future__ import annotations

import asyncio

import pytest

from mcp_manager.models import McpServer, StdioConfig, TransportType
from mcp_manager.monitor import ServerMonitor


class TestServerMonitorInit:
    """Unit tests for monitor initialization."""

    def test_filters_non_stdio(self) -> None:
        servers = [
            McpServer(
                name="stdio",
                transport=TransportType.STDIO,
                stdio_config=StdioConfig(command="python3", args=["-c", "pass"]),
            ),
            McpServer(
                name="sse",
                transport=TransportType.SSE,
                network_config={"type": "sse", "url": "http://localhost:3000/sse"},  # type: ignore[arg-type]
            ),
        ]
        monitor = ServerMonitor(servers)
        assert "stdio" in monitor._states
        assert "sse" not in monitor._states

    def test_empty_servers(self) -> None:
        monitor = ServerMonitor([])
        assert monitor._states == {}

    def test_stdio_without_config(self) -> None:
        server = McpServer(name="bad", transport=TransportType.STDIO)
        monitor = ServerMonitor([server])
        assert "bad" not in monitor._states


class TestServerMonitorRun:
    """Integration-style tests for monitor run/stop."""

    @pytest.mark.asyncio
    async def test_exits_immediately_with_no_servers(self) -> None:
        monitor = ServerMonitor([])
        result = await monitor.run()
        assert result == {}

    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        server = McpServer(
            name="sleep",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="sleep", args=["30"]),
        )
        monitor = ServerMonitor([server], restart_delay=0.1)

        # Start monitoring in background.
        task = asyncio.create_task(monitor.run())
        await asyncio.sleep(0.3)

        # Should have started the process.
        state = monitor._states["sleep"]
        assert state.running
        assert state.proc is not None
        assert state.proc.returncode is None

        # Signal shutdown and stop all.
        monitor._shutdown_event.set()
        await monitor.stop_all()
        await asyncio.sleep(0.2)

        # Process should have exited.
        assert not state.running
        assert state.proc is None or state.proc.returncode is not None

        # Wait for monitor task to finish (shutdown event causes clean exit).
        await asyncio.wait_for(task, timeout=2.0)

    @pytest.mark.asyncio
    async def test_status_api(self) -> None:
        server = McpServer(
            name="sleep",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="sleep", args=["30"]),
        )
        monitor = ServerMonitor([server], restart_delay=0.1)
        task = asyncio.create_task(monitor.run())
        await asyncio.sleep(0.3)

        status = monitor.get_status()
        assert "sleep" in status
        assert status["sleep"]["running"] is True
        assert status["sleep"]["restart_count"] == 0

        monitor._shutdown_event.set()
        await monitor.stop_all()
        await asyncio.sleep(0.2)
        await asyncio.wait_for(task, timeout=2.0)


class TestServerMonitorSummary:
    """Tests for summary generation."""

    def test_summary_empty(self) -> None:
        monitor = ServerMonitor([])
        assert monitor._summary() == {}

    def test_summary_with_state(self) -> None:
        server = McpServer(
            name="test",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="sleep", args=["1"]),
        )
        monitor = ServerMonitor([server])
        monitor._states["test"].restart_count = 3
        monitor._states["test"].exit_code = 1
        monitor._states["test"].error_message = "crashed"

        summary = monitor._summary()
        assert summary["test"]["restart_count"] == 3
        assert summary["test"]["final_exit_code"] == 1
        assert summary["test"]["final_error"] == "crashed"

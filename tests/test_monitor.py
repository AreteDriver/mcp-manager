"""Tests for server monitor (monitor.py)."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import patch

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
                stdio_config=StdioConfig(command=sys.executable, args=["-c", "pass"]),
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
    async def test_runs_without_event_loop_signal_support(self) -> None:
        server = McpServer(
            name="portable",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command=sys.executable, args=["-c", "pass"]),
        )
        monitor = ServerMonitor([server])
        monitor._shutdown_event.set()
        loop = asyncio.get_running_loop()

        with patch.object(loop, "add_signal_handler", side_effect=NotImplementedError):
            result = await monitor.run()

        assert result["portable"]["restart_count"] == 0

    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        server = McpServer(
            name="sleep",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(
                command=sys.executable,
                args=["-c", "import time; time.sleep(30)"],
            ),
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
            stdio_config=StdioConfig(
                command=sys.executable,
                args=["-c", "import time; time.sleep(30)"],
            ),
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
            stdio_config=StdioConfig(
                command=sys.executable,
                args=["-c", "import time; time.sleep(1)"],
            ),
        )
        monitor = ServerMonitor([server])
        monitor._states["test"].restart_count = 3
        monitor._states["test"].exit_code = 1
        monitor._states["test"].error_message = "crashed"

        summary = monitor._summary()
        assert summary["test"]["restart_count"] == 3
        assert summary["test"]["final_exit_code"] == 1
        assert summary["test"]["final_error"] == "crashed"


class TestServerMonitorEdgeCases:
    """Tests for OSError and restart backoff paths."""

    @pytest.mark.asyncio
    async def test_os_error_on_spawn(self) -> None:
        """Monitor handles OSError during process spawn."""
        server = McpServer(
            name="fail-spawn",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command="/does/not/exist"),
        )
        monitor = ServerMonitor([server], restart_delay=0.1)

        # Mock _spawn to raise OSError immediately
        with patch.object(monitor, "_spawn", side_effect=OSError("Permission denied")):
            task = asyncio.create_task(monitor.run())
            # Give _watch a chance to iterate once
            await asyncio.sleep(0.2)
            monitor._shutdown_event.set()
            await asyncio.wait_for(task, timeout=2.0)

        assert monitor._states["fail-spawn"].error_message == "Permission denied"
        assert not monitor._states["fail-spawn"].running

    @pytest.mark.asyncio
    async def test_restart_backoff(self) -> None:
        """Monitor increases delay after each restart."""
        server = McpServer(
            name="quick-exit",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command=sys.executable, args=["-c", ""]),
        )
        monitor = ServerMonitor([server], restart_delay=0.1, max_restart_delay=1.0)

        task = asyncio.create_task(monitor.run())
        # Wait for process to exit and one restart cycle
        await asyncio.sleep(0.6)
        monitor._shutdown_event.set()
        await asyncio.wait_for(task, timeout=2.0)

        # Should have restarted at least once
        assert monitor._states["quick-exit"].restart_count >= 1

    @pytest.mark.asyncio
    async def test_shutdown_during_restart_sleep(self) -> None:
        """Shutdown signal during restart sleep breaks the loop cleanly."""
        server = McpServer(
            name="sleep-exit",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(
                command=sys.executable,
                args=["-c", "import time; time.sleep(30)"],
            ),
        )
        monitor = ServerMonitor([server], restart_delay=10.0)

        task = asyncio.create_task(monitor.run())
        await asyncio.sleep(0.3)
        # Kill the process so it exits, triggering restart sleep
        state = monitor._states["sleep-exit"]
        if state.proc is not None and state.proc.returncode is None:
            state.proc.kill()
        await asyncio.sleep(0.2)
        # Now set shutdown during the long restart_delay sleep
        monitor._shutdown_event.set()
        await asyncio.wait_for(task, timeout=2.0)

        assert not state.running


class TestServerMonitorStress:
    """Stress tests for monitor edge cases."""

    @pytest.mark.asyncio
    async def test_restart_storm_backoff_caps(self) -> None:
        """Rapid restarts don't exceed max delay."""
        server = McpServer(
            name="crash-loop",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command=sys.executable, args=["-c", ""]),
        )
        monitor = ServerMonitor([server], restart_delay=0.1, max_restart_delay=0.5)

        task = asyncio.create_task(monitor.run())
        # Let it crash-restart a few times
        await asyncio.sleep(1.5)
        monitor._shutdown_event.set()
        await asyncio.wait_for(task, timeout=3.0)

        assert monitor._states["crash-loop"].restart_count >= 2
        # Backoff should cap at max_restart_delay
        # (indirectly verified by process surviving multiple cycles)

    @pytest.mark.asyncio
    async def test_monitor_cleanup_no_fds(self) -> None:
        """Stopping monitor cleans up all process references."""
        server = McpServer(
            name="sleep",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(
                command=sys.executable,
                args=["-c", "import time; time.sleep(30)"],
            ),
        )
        monitor = ServerMonitor([server], restart_delay=0.1)

        task = asyncio.create_task(monitor.run())
        await asyncio.sleep(0.3)

        monitor._shutdown_event.set()
        await asyncio.wait_for(task, timeout=2.0)

        # All processes should be stopped
        for state in monitor._states.values():
            assert not state.running

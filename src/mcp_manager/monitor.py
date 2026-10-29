"""Process monitor for MCP stdio servers with auto-restart.

Keeps configured stdio servers alive by spawning them, watching for
exit, and restarting with exponential backoff.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from dataclasses import dataclass
from typing import Any

from mcp_manager.models import McpServer, StdioConfig, TransportType

logger = logging.getLogger(__name__)

DEFAULT_RESTART_DELAY = 1.0
MAX_RESTART_DELAY = 30.0
BACKOFF_MULTIPLIER = 2.0


@dataclass
class MonitorState:
    """Runtime state of a monitored server."""

    server: McpServer
    proc: asyncio.subprocess.Process | None = None
    restart_count: int = 0
    running: bool = False
    exit_code: int | None = None
    error_message: str | None = None


class ServerMonitor:
    """Monitor and auto-restart stdio MCP servers.

    Usage:
        monitor = ServerMonitor(servers)
        asyncio.run(monitor.run())  # blocks until SIGINT/SIGTERM
    """

    def __init__(
        self,
        servers: list[McpServer],
        *,
        restart_delay: float = DEFAULT_RESTART_DELAY,
        max_restart_delay: float = MAX_RESTART_DELAY,
    ) -> None:
        self._states: dict[str, MonitorState] = {}
        for s in servers:
            if s.transport == TransportType.STDIO and s.stdio_config:
                self._states[s.name] = MonitorState(server=s)
            else:
                logger.warning("Skipping non-stdio server %r", s.name)
        self._restart_delay = restart_delay
        self._max_restart_delay = max_restart_delay
        self._shutdown_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> dict[str, Any]:
        """Start all servers and monitor until shutdown signal.

        Returns:
            Summary dict with restart counts and final exit codes.
        """
        if not self._states:
            logger.warning("No stdio servers to monitor")
            return {}

        # Register signal handlers for graceful shutdown.
        loop = asyncio.get_running_loop()
        registered_signals: list[signal.Signals] = []
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown_event.set)
            except (NotImplementedError, RuntimeError):
                # ProactorEventLoop on Windows does not implement asyncio
                # signal handlers. Programmatic shutdown remains available.
                logger.debug("Event loop does not support signal handler %s", sig)
            else:
                registered_signals.append(sig)

        try:
            tasks = [asyncio.create_task(self._watch(name)) for name in self._states]
            await self._shutdown_event.wait()
            logger.info("Shutdown signal received, stopping servers...")
        finally:
            for sig in registered_signals:
                loop.remove_signal_handler(sig)

        # Stop all servers.
        await self.stop_all()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        return self._summary()

    async def start_all(self) -> None:
        """Start all servers without blocking (for programmatic use)."""
        for name in self._states:
            asyncio.create_task(self._watch(name))

    async def stop_all(self) -> None:
        """Stop all monitored servers."""
        for state in self._states.values():
            state.running = False
            if state.proc is not None and state.proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    state.proc.kill()

    def get_status(self) -> dict[str, dict[str, Any]]:
        """Return current status of all monitored servers."""
        return {
            name: {
                "running": s.running,
                "restart_count": s.restart_count,
                "exit_code": s.exit_code,
                "error": s.error_message,
            }
            for name, s in self._states.items()
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _watch(self, name: str) -> None:
        """Watch a single server, restarting it on failure."""
        state = self._states[name]
        delay = self._restart_delay

        while not self._shutdown_event.is_set():
            try:
                state.running = True
                state.exit_code = None
                state.error_message = None
                proc = await self._spawn(state.server.stdio_config)
                state.proc = proc

                logger.info("Started %s (pid %s)", name, proc.pid)
                await proc.wait()

                state.exit_code = proc.returncode
                state.running = False
                state.proc = None

                if self._shutdown_event.is_set():
                    logger.info("Server %s exited (code %s) during shutdown", name, proc.returncode)
                    break

                logger.warning(
                    "Server %s exited (code %s), restarting in %.1fs",
                    name,
                    proc.returncode,
                    delay,
                )
                state.restart_count += 1
                state.error_message = f"Exited with code {proc.returncode}"

                await asyncio.wait_for(self._shutdown_event.wait(), timeout=delay)
                break  # shutdown happened during sleep
            except TimeoutError:
                delay = min(delay * BACKOFF_MULTIPLIER, self._max_restart_delay)
            except OSError as exc:
                logger.exception("Error monitoring %s", name)
                state.error_message = str(exc)
                state.running = False
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=delay)
                break

    @staticmethod
    async def _spawn(cfg: StdioConfig | None) -> asyncio.subprocess.Process:
        if cfg is None:
            raise RuntimeError("stdio_config is None")
        env = cfg.env if cfg.env else None
        return await asyncio.create_subprocess_exec(
            cfg.command,
            *cfg.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

    def _summary(self) -> dict[str, Any]:
        return {
            name: {
                "restart_count": s.restart_count,
                "final_exit_code": s.exit_code,
                "final_error": s.error_message,
            }
            for name, s in self._states.items()
        }

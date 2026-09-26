"""SDK log shielding must remain local across overlapping sessions."""

import asyncio
import logging

from mcp_manager.session_logging import private_session_logs


async def test_overlapping_sessions_do_not_suppress_unrelated_tasks(caplog):
    log = logging.getLogger("mcp.client.sse")
    entered = asyncio.Event()
    finished = asyncio.Event()
    caplog.set_level(logging.DEBUG)

    async def private():
        with private_session_logs():
            entered.set()
            await finished.wait()
            log.error("synthetic-secret", exc_info=True)
            with private_session_logs():
                log.warning("nested-secret")

    task = asyncio.create_task(private())
    await entered.wait()
    log.warning("unrelated-visible")
    finished.set()
    await task
    log.warning("after-visible")
    assert "secret" not in caplog.text
    assert "unrelated-visible" in caplog.text
    assert "after-visible" in caplog.text

"""Crash-safe helpers for replacing sensitive configuration files."""

from __future__ import annotations

import logging
import os
import stat
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def atomic_write_text(path: Path, text: str, *, mode: int | None = None) -> None:
    """Durably replace *path* with UTF-8 *text* from the same directory.

    Existing permissions are preserved unless ``mode`` is supplied. The temp
    file is flushed and synced before the atomic replace, and is removed after
    every failure path.
    """
    target_mode = mode
    if target_mode is None and path.exists():
        target_mode = stat.S_IMODE(path.stat().st_mode)

    fd: int | None = None
    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}-tmp-",
            suffix=path.suffix or ".tmp",
        )
        tmp_path = Path(tmp_name)
        # Windows uses ACLs rather than POSIX permission bits. os.chmod there
        # only toggles the read-only flag and cannot enforce modes like 0o600.
        if target_mode is not None and os.name != "nt":
            os.chmod(tmp_path, target_mode)

        file_obj = os.fdopen(fd, "w", encoding="utf-8", newline="")
        fd = None
        with file_obj as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove temporary file %s", tmp_path)

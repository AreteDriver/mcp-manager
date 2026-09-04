"""Tests for crash-safe atomic text writes."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_manager.atomic import atomic_write_text


def test_atomic_write_replaces_content_and_preserves_mode(tmp_path: Path) -> None:
    target = tmp_path / "config.json"
    target.write_text("old\n", encoding="utf-8")
    os.chmod(target, 0o640)

    atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert target.stat().st_mode & 0o777 == 0o640


def test_atomic_write_applies_explicit_private_mode(tmp_path: Path) -> None:
    target = tmp_path / "auth.json"

    atomic_write_text(target, "{}\n", mode=0o600)

    assert target.stat().st_mode & 0o777 == 0o600


def test_atomic_write_cleans_up_temp_file_after_replace_failure(tmp_path: Path) -> None:
    target = tmp_path / "config.yml"
    target.write_text("old\n", encoding="utf-8")

    with (
        patch("mcp_manager.atomic.os.replace", side_effect=OSError("disk failure")),
        pytest.raises(OSError, match="disk failure"),
    ):
        atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "old\n"
    assert list(tmp_path.glob(".config.yml-tmp-*")) == []

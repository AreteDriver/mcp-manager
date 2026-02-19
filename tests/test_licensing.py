"""Tests for mcp_manager.licensing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mcp_manager.licensing import (
    Tier,
    _compute_check_segment,
    _validate_key_checksum,
    _validate_key_format,
    get_license_info,
    get_upgrade_message,
    has_feature,
    is_pro,
)


def _make_valid_key() -> str:
    """Generate a valid MCPM license key."""
    body = "ABCD-EFGH"
    check = _compute_check_segment(body)
    return f"MCPM-{body}-{check}"


class TestKeyFormat:
    def test_valid_format(self) -> None:
        assert _validate_key_format("MCPM-ABCD-EFGH-IJKL") is True

    def test_wrong_prefix(self) -> None:
        assert _validate_key_format("CMDF-ABCD-EFGH-IJKL") is False

    def test_too_few_segments(self) -> None:
        assert _validate_key_format("MCPM-ABCD-EFGH") is False

    def test_too_many_segments(self) -> None:
        assert _validate_key_format("MCPM-ABCD-EFGH-IJKL-MNOP") is False

    def test_lowercase_rejected(self) -> None:
        assert _validate_key_format("MCPM-abcd-EFGH-IJKL") is False

    def test_wrong_length_segment(self) -> None:
        assert _validate_key_format("MCPM-ABC-EFGH-IJKL") is False

    def test_whitespace_stripped(self) -> None:
        assert _validate_key_format("  MCPM-ABCD-EFGH-IJKL  ") is True


class TestKeyChecksum:
    def test_valid_checksum(self) -> None:
        key = _make_valid_key()
        assert _validate_key_checksum(key) is True

    def test_invalid_checksum(self) -> None:
        assert _validate_key_checksum("MCPM-ABCD-EFGH-ZZZZ") is False

    def test_checksum_is_deterministic(self) -> None:
        seg1 = _compute_check_segment("ABCD-EFGH")
        seg2 = _compute_check_segment("ABCD-EFGH")
        assert seg1 == seg2

    def test_different_bodies_different_checksums(self) -> None:
        seg1 = _compute_check_segment("AAAA-BBBB")
        seg2 = _compute_check_segment("CCCC-DDDD")
        assert seg1 != seg2


class TestGetLicenseInfo:
    def test_no_key_returns_free(self) -> None:
        with patch("mcp_manager.licensing._find_license_key", return_value=None):
            info = get_license_info()
        assert info.tier == Tier.FREE
        assert info.valid is False

    def test_valid_key_returns_pro(self) -> None:
        key = _make_valid_key()
        with patch("mcp_manager.licensing._find_license_key", return_value=key):
            info = get_license_info()
        assert info.tier == Tier.PRO
        assert info.valid is True
        assert info.license_key == key

    def test_invalid_format_returns_free(self) -> None:
        with patch("mcp_manager.licensing._find_license_key", return_value="bad-key"):
            info = get_license_info()
        assert info.tier == Tier.FREE
        assert info.valid is False

    def test_invalid_checksum_returns_free(self) -> None:
        with patch(
            "mcp_manager.licensing._find_license_key",
            return_value="MCPM-ABCD-EFGH-ZZZZ",
        ):
            info = get_license_info()
        assert info.tier == Tier.FREE
        assert info.valid is False

    def test_env_var_lookup(self, monkeypatch: object) -> None:
        import os

        key = _make_valid_key()
        with patch.dict(os.environ, {"MCP_MANAGER_LICENSE": key}):
            info = get_license_info()
        assert info.tier == Tier.PRO

    def test_file_lookup(self, tmp_path: Path) -> None:
        key = _make_valid_key()
        license_file = tmp_path / ".mcp-manager-license"
        license_file.write_text(key, encoding="utf-8")

        locations = [str(license_file)]
        with (
            patch.dict("os.environ", {}, clear=False),
            patch("mcp_manager.licensing._LICENSE_LOCATIONS", locations),
            patch("mcp_manager.licensing.os.environ.get", return_value=None),
        ):
            info = get_license_info()
        assert info.tier == Tier.PRO


class TestHasFeature:
    def test_free_has_list(self) -> None:
        with patch("mcp_manager.licensing._find_license_key", return_value=None):
            assert has_feature("list") is True

    def test_free_lacks_daemon(self) -> None:
        with patch("mcp_manager.licensing._find_license_key", return_value=None):
            assert has_feature("auto_health_daemon") is False

    def test_pro_has_daemon(self) -> None:
        key = _make_valid_key()
        with patch("mcp_manager.licensing._find_license_key", return_value=key):
            assert has_feature("auto_health_daemon") is True


class TestIsPro:
    def test_free(self) -> None:
        with patch("mcp_manager.licensing._find_license_key", return_value=None):
            assert is_pro() is False

    def test_pro(self) -> None:
        key = _make_valid_key()
        with patch("mcp_manager.licensing._find_license_key", return_value=key):
            assert is_pro() is True


class TestUpgradeMessage:
    def test_contains_feature_name(self) -> None:
        msg = get_upgrade_message("auto_health_daemon")
        assert "auto_health_daemon" in msg

    def test_contains_price(self) -> None:
        msg = get_upgrade_message("team_sync")
        assert "$5/mo" in msg

"""Tests for release automation: version guard, changelog extraction, build."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Import the script under test
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from extract_changelog import extract_version_section


class TestVersionGuard:
    """Unit tests for the version-guard logic used in release.yml."""

    def _guard(self, tag_version: str, code_version: str) -> int:
        """Simulate the shell version-guard logic in Python for testing."""
        if tag_version != code_version:
            return 1
        return 0

    def test_guard_match(self) -> None:
        assert self._guard("0.7.0", "0.7.0") == 0

    def test_guard_mismatch(self) -> None:
        assert self._guard("0.7.0", "0.6.0") == 1

    def test_guard_trailing_v_stripped(self) -> None:
        """In CI the 'v' prefix is already stripped; guard compares raw strings."""
        assert self._guard("0.7.0", "v0.7.0") == 1

    def test_current_version_matches_source(self) -> None:
        """Ensure __version__ in source matches pyproject.toml."""
        from mcp_manager import __version__

        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        text = pyproject.read_text()
        # Find version = "X.Y.Z"
        import re

        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        assert match is not None
        assert match.group(1) == __version__


class TestChangelogExtraction:
    """Tests for scripts/extract_changelog.py."""

    SAMPLE_CHANGELOG = """# Changelog

## [Unreleased]

## [0.7.0] — 2026-07-20

### Added

- Feature A
- Feature B

### Changed

- Thing C

## [0.6.0] — 2026-07-20

### Added

- Old feature
"""

    def test_extract_existing_version(self) -> None:
        body = extract_version_section(self.SAMPLE_CHANGELOG, "0.7.0")
        assert body is not None
        assert "Feature A" in body
        assert "Feature B" in body
        assert "Thing C" in body
        assert "Old feature" not in body

    def test_extract_missing_version(self) -> None:
        body = extract_version_section(self.SAMPLE_CHANGELOG, "0.99.0")
        assert body is None

    def test_extract_last_version(self) -> None:
        body = extract_version_section(self.SAMPLE_CHANGELOG, "0.6.0")
        assert body is not None
        assert "Old feature" in body
        assert "Feature A" not in body

    def test_cli_success(self) -> None:
        from extract_changelog import main

        result = main(["--version", "0.7.0"])
        assert result == 0

    def test_cli_failure(self) -> None:
        from extract_changelog import main

        result = main(["--version", "0.99.0"])
        assert result == 1

    def test_real_changelog(self) -> None:
        changelog = Path(__file__).parent.parent / "CHANGELOG.md"
        text = changelog.read_text()
        body = extract_version_section(text, "0.7.0")
        assert body is not None
        assert "Persistent registry authentication" in body


class TestBuild:
    """Ensure the package builds cleanly."""

    @pytest.mark.slow
    def test_build_succeeds(self) -> None:
        repo = Path(__file__).parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "build"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_build_requires_build(self) -> None:
        """Lightweight sanity check: build module is importable."""
        import build

        assert hasattr(build, "__version__")


class TestWorkflowYaml:
    """Validate release workflow file syntax."""

    def test_release_yml_valid(self) -> None:
        workflow = Path(__file__).parent.parent / ".github" / "workflows" / "release.yml"
        data = yaml.safe_load(workflow.read_text())
        assert data["name"] == "Release"
        assert "release" in data["jobs"]
        steps = data["jobs"]["release"]["steps"]
        names = [s.get("name") for s in steps]
        assert "Version guard" in names
        assert "Extract CHANGELOG section" in names
        assert "Create GitHub Release" in names
        assert "Publish to PyPI" in names

    def test_validate_action_provisions_pinned_uv(self) -> None:
        action = (
            Path(__file__).parent.parent
            / ".github"
            / "actions"
            / "mcp-manager-validate"
            / "action.yml"
        )
        data = yaml.safe_load(action.read_text())
        assert data["inputs"]["uv-version"]["default"] == "0.11.7"
        steps = data["runs"]["steps"]
        install_uv = next(step for step in steps if step.get("name") == "Install uv runtime")
        assert "uv==${{ inputs.uv-version }}" in install_uv["run"]

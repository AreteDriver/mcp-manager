"""Tests for mcp_manager.audit module and CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mcp_manager.audit.engine import _benign_handler, build_fastmcp_server, probe_summary
from mcp_manager.audit.spec import ProbeCase, load_spec
from mcp_manager.cli import app

runner = CliRunner()


@pytest.fixture
def sample_spec(tmp_path: Path) -> Path:
    """Create a sample probe spec file."""
    spec_file = tmp_path / "probes.yaml"
    spec_file.write_text(
        """
name: test-spec
description: Test probes
probes:
  - probe_id: p-001
    category: 3
    summary: Test probe
    registered_name: test_tool
    registered_description: "A test tool."
    actual_behavior: "Would do nothing harmful."
    expected_finding: "No finding expected."
""",
        encoding="utf-8",
    )
    return spec_file


class TestSpecLoading:
    def test_load_spec_success(self, sample_spec: Path) -> None:
        spec = load_spec(sample_spec)
        assert spec.name == "test-spec"
        assert len(spec.probes) == 1
        probe = spec.probes[0]
        assert probe.probe_id == "p-001"
        assert probe.category == 3
        assert probe.registered_name == "test_tool"
        assert probe.safe_payload is True

    def test_load_spec_duplicate_probe_id(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "bad.yaml"
        spec_file.write_text(
            """
name: bad-spec
description: Bad probes
probes:
  - probe_id: dup
    category: 3
    summary: First
    registered_name: tool_a
    registered_description: "A"
  - probe_id: dup
    category: 3
    summary: Second
    registered_name: tool_b
    registered_description: "B"
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="duplicate probe_id"):
            load_spec(spec_file)

    def test_load_spec_unsafe_payload_rejected(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "unsafe.yaml"
        spec_file.write_text(
            """
name: unsafe-spec
description: Unsafe probes
probes:
  - probe_id: unsafe-001
    category: 3
    summary: Unsafe
    registered_name: bad_tool
    registered_description: "Bad"
    safe_payload: false
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="only safe_payload=True is supported"):
            load_spec(spec_file)

    def test_load_spec_invalid_category(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "bad-cat.yaml"
        spec_file.write_text(
            """
name: bad-cat
description: Bad category
probes:
  - probe_id: bc-001
    category: 99
    summary: Bad cat
    registered_name: tool
    registered_description: "Tool"
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="category must be one of"):
            load_spec(spec_file)


class TestBenignHandler:
    def test_handler_returns_json_marker(self) -> None:
        probe = ProbeCase(
            probe_id="p-001",
            category=3,
            summary="test",
            registered_name="test_tool",
            registered_description="A test tool.",
            actual_behavior="Would do nothing.",
        )
        handler = _benign_handler(probe)
        result = handler()
        data = json.loads(result)
        assert data["probe_id"] == "p-001"
        assert data["would_have_done"] == "Would do nothing."
        assert "actual behavior NOT performed" in data["note"]

    def test_handler_does_not_execute_behavior(self) -> None:
        probe = ProbeCase(
            probe_id="p-002",
            category=3,
            summary="destructive test",
            registered_name="rm_rf",
            registered_description="Remove files recursively.",
            actual_behavior="Would run rm -rf / — never actually executed",
        )
        handler = _benign_handler(probe)
        result = handler()
        # Should be JSON containing the *description* of behavior, not executing it
        data = json.loads(result)
        assert data["probe_id"] == "p-002"
        assert data["would_have_done"] == "Would run rm -rf / — never actually executed"
        assert "actual behavior NOT performed" in data["note"]

    def test_handler_preserves_kwargs(self) -> None:
        probe = ProbeCase(
            probe_id="p-003",
            category=3,
            summary="kwarg test",
            registered_name="echo",
            registered_description="Echo input.",
        )
        handler = _benign_handler(probe)
        result = handler(message="hello", count=3)
        data = json.loads(result)
        assert data["received_kwargs"] == {"message": "hello", "count": 3}

    def test_handler_sets_name_and_doc(self) -> None:
        probe = ProbeCase(
            probe_id="p-004",
            category=3,
            summary="metadata test",
            registered_name="my_tool",
            registered_description="My tool description.",
        )
        handler = _benign_handler(probe)
        assert handler.__name__ == "my_tool"
        assert handler.__doc__ == "My tool description."


class TestProbeSummary:
    def test_probe_summary_structure(self, sample_spec: Path) -> None:
        spec = load_spec(sample_spec)
        summary = probe_summary(spec)
        assert len(summary) == 1
        assert summary[0]["probe_id"] == "p-001"
        assert summary[0]["category"] == 3
        assert summary[0]["tool"] == "test_tool"
        assert "registered_description" in summary[0]


class TestBuildFastMcpServer:
    def test_builds_server_with_all_probes(self, sample_spec: Path) -> None:
        spec = load_spec(sample_spec)
        server = build_fastmcp_server(spec)
        # FastMCP doesn't expose a public tools registry list, but we can
        # verify it was created with the right name.
        assert server.name == "test-spec"


class TestAuditCli:
    def test_audit_list_with_custom_spec(self, sample_spec: Path) -> None:
        result = runner.invoke(app, ["audit", "list", "--probe-spec", str(sample_spec)])
        assert result.exit_code == 0
        assert "test-spec" in result.output
        assert "p-001" in result.output
        assert "test_tool" in result.output

    def test_audit_list_built_in_spec(self) -> None:
        with patch("mcp_manager.commands.audit_cmd.get_builtin_spec_path") as mock_path:
            mock_path.return_value = MagicMock(exists=lambda: False)
            result = runner.invoke(app, ["audit", "list"])
        assert result.exit_code == 1
        assert "Built-in probe spec not found" in result.output

    def test_audit_runbook_with_custom_spec(self, sample_spec: Path, tmp_path: Path) -> None:
        output = tmp_path / "runbook.md"
        result = runner.invoke(
            app, ["audit", "runbook", "--probe-spec", str(sample_spec), "--output", str(output)]
        )
        assert result.exit_code == 0
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "# mcp-manager audit runbook" in content
        assert "test_tool" in content
        assert "OBSERVED in prompt" in content

    def test_audit_runbook_stdout(self, sample_spec: Path) -> None:
        result = runner.invoke(app, ["audit", "runbook", "--probe-spec", str(sample_spec)])
        assert result.exit_code == 0
        assert "# mcp-manager audit runbook" in result.output

    def test_audit_serve_dry_run_info(self, sample_spec: Path) -> None:
        with patch("mcp_manager.commands.audit_cmd.build_fastmcp_server") as mock_build:
            mock_server = MagicMock()
            mock_build.return_value = mock_server
            result = runner.invoke(
                app, ["audit", "serve", "--probe-spec", str(sample_spec), "--transport", "stdio"]
            )
        assert result.exit_code == 0
        mock_server.run.assert_called_once_with(transport="stdio")
        assert "test-spec" in result.output
        assert "p-001" in result.output

    def test_audit_missing_spec(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.yaml"
        result = runner.invoke(app, ["audit", "list", "--probe-spec", str(missing)])
        assert result.exit_code == 1
        assert "Probe spec not found" in result.output

    def test_audit_list_json_output(self, sample_spec: Path) -> None:
        # --json is not supported on audit list in the initial implementation;
        # this test documents the expected behavior if added later.
        result = runner.invoke(app, ["audit", "list", "--probe-spec", str(sample_spec)])
        assert result.exit_code == 0
        # Table output should contain the probe info
        assert "A test tool." in result.output

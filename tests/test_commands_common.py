"""Tests for commands/common.py shared helpers."""

from __future__ import annotations

from mcp_manager.commands.common import _filter_by_tags
from mcp_manager.models import McpServer, StdioConfig, TransportType


def _server(name: str, tags: list[str]) -> McpServer:
    """Build a minimal server for tag filter tests."""
    return McpServer(
        name=name,
        transport=TransportType.STDIO,
        stdio_config=StdioConfig(command="echo"),
        tags=tags,
    )


class TestFilterByTags:
    """Tests for _filter_by_tags."""

    def test_no_filters_returns_all(self) -> None:
        servers = [_server("a", ["x"]), _server("b", ["y"])]
        assert _filter_by_tags(servers) == servers

    def test_include_single_tag(self) -> None:
        servers = [_server("a", ["backend"]), _server("b", ["frontend"]), _server("c", [])]
        result = _filter_by_tags(servers, include=["backend"])
        assert [s.name for s in result] == ["a"]

    def test_include_multiple_tags_or_logic(self) -> None:
        servers = [
            _server("a", ["backend"]),
            _server("b", ["frontend"]),
            _server("c", ["backend", "frontend"]),
        ]
        result = _filter_by_tags(servers, include=["backend", "frontend"])
        assert {s.name for s in result} == {"a", "b", "c"}

    def test_exclude_single_tag(self) -> None:
        servers = [_server("a", ["experimental"]), _server("b", ["stable"])]
        result = _filter_by_tags(servers, exclude=["experimental"])
        assert [s.name for s in result] == ["b"]

    def test_exclude_removes_any_match(self) -> None:
        servers = [
            _server("a", ["backend", "experimental"]),
            _server("b", ["backend"]),
        ]
        result = _filter_by_tags(servers, exclude=["experimental"])
        assert [s.name for s in result] == ["b"]

    def test_include_and_exclude_combined(self) -> None:
        servers = [
            _server("a", ["backend", "experimental"]),
            _server("b", ["backend", "stable"]),
            _server("c", ["frontend"]),
        ]
        result = _filter_by_tags(servers, include=["backend"], exclude=["experimental"])
        assert [s.name for s in result] == ["b"]

    def test_empty_include_returns_none(self) -> None:
        servers = [_server("a", ["x"])]
        result = _filter_by_tags(servers, include=[])
        assert result == []

    def test_empty_exclude_returns_all(self) -> None:
        servers = [_server("a", ["x"])]
        result = _filter_by_tags(servers, exclude=[])
        assert [s.name for s in result] == ["a"]

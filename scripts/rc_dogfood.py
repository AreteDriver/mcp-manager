#!/usr/bin/env python3
"""Run destructive-path release-candidate checks in an isolated workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from unittest.mock import patch

from mcp_manager import __version__
from mcp_manager.adapters import build_target_adapters
from mcp_manager.atomic import atomic_write_text
from mcp_manager.models import McpServer, NetworkConfig, StdioConfig, TransportType
from mcp_manager.writeback import ConfigWriteback

TARGETS = (
    ("claude-code", "claude-code.json", "mcpServers"),
    ("claude-desktop", "claude-desktop.json", "mcpServers"),
    ("cursor", "cursor.json", "mcpServers"),
    ("windsurf", "windsurf.json", "mcpServers"),
    ("codex", "codex.toml", "mcp_servers"),
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_target(path: Path, target: str) -> None:
    if target == "codex":
        path.write_text(
            '# release-candidate-preserved-comment\nmodel = "preserved-model"\n',
            encoding="utf-8",
        )
        return
    path.write_text(
        json.dumps(
            {"unrelated": {"preserved": True}, "mcpServers": {}},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _dogfood_servers() -> list[McpServer]:
    return [
        McpServer(
            name="rc-stdio",
            transport=TransportType.STDIO,
            stdio_config=StdioConfig(command=sys.executable, args=["-c", "pass"]),
        ),
        McpServer(
            name="rc-http",
            transport=TransportType.HTTP,
            network_config=NetworkConfig(type="http", url="https://example.invalid/mcp"),
        ),
    ]


def check_config_round_trips(root: Path) -> dict[str, str]:
    """Exercise preview, repeat writes, backups, and removal for every target."""
    configs = [(name, root / filename, wrapper) for name, filename, wrapper in TARGETS]
    writeback = ConfigWriteback()
    writeback._ide_configs = {name: (str(path), wrapper) for name, path, wrapper in configs}
    writeback._target_adapters = build_target_adapters(configs)
    servers = _dogfood_servers()
    results: dict[str, str] = {}

    for target, path, _wrapper in configs:
        _seed_target(path, target)
        seed_digest = _digest(path)
        writeback.preview(target, servers)
        writeback.write_servers(target, servers)
        backup = path.with_suffix(path.suffix + ".mcp-manager-backup")
        if not backup.is_file():
            raise RuntimeError(f"{target}: backup was not created")
        shutil.copyfile(backup, path)
        if _digest(path) != seed_digest:
            raise RuntimeError(f"{target}: backup did not restore the original config")

        writeback.write_servers(target, servers)
        first_digest = _digest(path)
        writeback.write_servers(target, servers)
        if _digest(path) != first_digest:
            raise RuntimeError(f"{target}: repeated write was not idempotent")

        parsed_names = {
            server.name
            for server in writeback._adapter_for(target).parse(
                path.read_text(encoding="utf-8"),
                source_path=path,
            )
        }
        if parsed_names != {"rc-http", "rc-stdio"}:
            raise RuntimeError(f"{target}: round-trip changed server definitions")

        _path, removed = writeback.remove_servers(target, parsed_names)
        if set(removed) != parsed_names:
            raise RuntimeError(f"{target}: remove did not report every dogfood server")
        final_text = path.read_text(encoding="utf-8")
        if target == "codex":
            if "release-candidate-preserved-comment" not in final_text:
                raise RuntimeError("codex: unrelated comment was not preserved")
        else:
            final_data = json.loads(final_text)
            if final_data.get("unrelated") != {"preserved": True}:
                raise RuntimeError(f"{target}: unrelated JSON keys were not preserved")
        results[target] = "passed"

    return results


def _venv_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _child_environment() -> dict[str, str]:
    """Preserve a relocatable uv Python's library path in child venvs."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    if sys.platform == "darwin":
        library_dir = Path(sys.base_prefix) / "lib"
        if (
            library_dir / f"libpython{sys.version_info.major}.{sys.version_info.minor}.dylib"
        ).is_file():
            existing = environment.get("DYLD_LIBRARY_PATH")
            environment["DYLD_LIBRARY_PATH"] = (
                f"{library_dir}{os.pathsep}{existing}" if existing else str(library_dir)
            )
    return environment


def check_failed_write_cleanup(root: Path) -> str:
    """Verify a failed replacement retains content and removes its temp file."""
    target = root / "failed-write.json"
    target.write_text('{"preserved": true}\n', encoding="utf-8")
    before = _digest(target)
    try:
        with patch("mcp_manager.atomic.os.replace", side_effect=OSError("dogfood failure")):
            atomic_write_text(target, '{"preserved": false}\n')
    except OSError as exc:
        if str(exc) != "dogfood failure":
            raise
    else:
        raise RuntimeError("failed-write simulation unexpectedly succeeded")
    if _digest(target) != before:
        raise RuntimeError("failed write changed the target file")
    if list(root.glob(".failed-write.json-tmp-*")):
        raise RuntimeError("failed write left a temporary file behind")
    return "passed"


def check_wheel_install(wheel: Path, root: Path) -> str:
    """Install the candidate wheel into a fresh venv and invoke its CLI."""
    environment = root / "wheel-smoke"
    venv.EnvBuilder(with_pip=False, clear=True).create(environment)
    python = _venv_python(environment)
    child_environment = _child_environment()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "--python",
            str(python),
            "install",
            "--ignore-installed",
            "--quiet",
            str(wheel),
        ],
        check=True,
        env=child_environment,
    )
    module_location = subprocess.run(
        [str(python), "-c", "import mcp_manager; print(mcp_manager.__file__)"],
        check=True,
        capture_output=True,
        text=True,
        env=child_environment,
    ).stdout.strip()
    if environment.resolve() not in Path(module_location).resolve().parents:
        raise RuntimeError(f"wheel imported outside the isolated environment: {module_location}")
    result = subprocess.run(
        [str(python), "-m", "mcp_manager", "--version"],
        check=True,
        capture_output=True,
        text=True,
        env=child_environment,
    )
    expected = f"mcp-manager {__version__}"
    if result.stdout.strip() != expected:
        raise RuntimeError(f"wheel reported {result.stdout.strip()!r}, expected {expected!r}")
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, help="Candidate wheel to install and smoke-test")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="mcp-manager-rc-") as tmp:
        root = Path(tmp)
        evidence: dict[str, object] = {
            "version": __version__,
            "platform": sys.platform,
            "config_round_trips": check_config_round_trips(root),
            "failed_write_cleanup": check_failed_write_cleanup(root),
        }
        if args.wheel:
            evidence["wheel_install"] = check_wheel_install(args.wheel.resolve(), root)
        print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

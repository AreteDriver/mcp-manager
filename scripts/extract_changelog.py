#!/usr/bin/env python3
"""Extract a version section from CHANGELOG.md for release notes."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def extract_version_section(changelog_text: str, version: str) -> str | None:
    """Extract the markdown body for a specific version heading.

    Args:
        changelog_text: Full contents of CHANGELOG.md.
        version: Version string without leading 'v' (e.g. "0.7.0").

    Returns:
        The markdown body between the requested heading and the next
        ## [X.Y.Z] or ## [Unreleased] heading, or None if not found.
    """
    # Match headings like ## [0.7.0] — 2026-07-20
    pattern = re.compile(
        rf"^##\s+\[{re.escape(version)}\].*$",
        re.MULTILINE,
    )
    match = pattern.search(changelog_text)
    if not match:
        return None

    start = match.end()
    # Find next ## heading
    next_heading = re.search(r"^##\s+\[", changelog_text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(changelog_text)

    body = changelog_text[start:end].strip()
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract a version section from CHANGELOG.md")
    parser.add_argument("--file", type=Path, default=Path("CHANGELOG.md"), help="Changelog path")
    parser.add_argument("--version", required=True, help="Version to extract (e.g. 0.7.0)")
    parser.add_argument("--fallback", default="", help="Text to print if section not found")
    args = parser.parse_args(argv)

    text = args.file.read_text(encoding="utf-8")
    section = extract_version_section(text, args.version)
    if section is None:
        print(args.fallback, end="")
        return 1
    print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main())

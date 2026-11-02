"""Fail the build when any recorded version drifts from version.json.

The version string used to live in six scripts, the batch file, two TEXTS
entries and four documents.  A single missed edit only surfaced at step 15
(or worse, shipped as an EXE whose PE version disagreed with its filename),
so this check runs right after the base copy and reports every offender at
once.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
import struct
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"\d+\.\d+\.\d+\.\d+")

# Files that must agree with version.json verbatim.
SOURCES = (
    "一键构建.bat",
    "README.md",
    "CHANGELOG.md",
    "项目说明.md",
    "交接文件.md",
)
PATH_SCRIPTS = (
    "scripts/patch_version_info.py",
    "scripts/package_release.py",
    "scripts/finalize_release.py",
    "scripts/repack_pyz.py",
    "scripts/strip_embedded_assets.py",
    "scripts/validate_final.py",
)

# Documents legitimately mention older releases, so they are scanned for the
# *newest* version only: the top CHANGELOG section, the README banner and the
# archive index must all name the version under construction.
ARCHIVE_INDEX = "项目文件历史版本/归档索引.md"


def read_version() -> str:
    data = json.loads((BASE / "version.json").read_text(encoding="utf-8"))
    version = data.get("version", "")
    if not SEMVER.fullmatch(version):
        raise SystemExit(f"version.json holds an invalid version: {version!r}")
    return version


def check_scripts(version: str) -> list[str]:
    problems = []
    for rel in PATH_SCRIPTS:
        path = BASE / rel
        text = path.read_text(encoding="utf-8")
        if 'version.json' not in text:
            problems.append(f"{rel}: does not read version.json")
        for line_no, line in enumerate(text.splitlines(), 1):
            code = line.split("#", 1)[0]
            for found in SEMVER.findall(code):
                if found != version:
                    problems.append(f"{rel}:{line_no}: hard-coded version {found}")
    return problems


def check_batch(version: str) -> list[str]:
    path = BASE / "一键构建.bat"
    raw = path.read_bytes()
    if raw.count(b"\n") != raw.count(b"\r\n"):
        return ["一键构建.bat: mixed line endings (cmd.exe truncates on LF)"]
    text = raw.decode("utf-8")
    if "version.json" not in text:
        return ["一键构建.bat: does not read version.json"]
    return [
        f"一键构建.bat: hard-coded version {found}"
        for found in SEMVER.findall(text)
        if found != version
    ]


def check_ui_texts(version: str) -> list[str]:
    """about_version holds a display prefix such as " · V1.4.1.0"."""
    path = BASE / "ui_compact.py"
    text = path.read_text(encoding="utf-8")
    entries = re.findall(r'"about_version"\s*:\s*"([^"]*)"', text)
    if len(entries) != 2:
        return [f"ui_compact.py: expected 2 about_version entries, found {len(entries)}"]
    problems = []
    for label, value in zip(("zh", "en"), entries):
        found = SEMVER.search(value)
        if not found:
            problems.append(f"ui_compact.py: {label}.about_version has no version")
        elif found.group(0) != version:
            problems.append(
                f"ui_compact.py: {label}.about_version is {found.group(0)}"
            )
    return problems


def check_docs(version: str) -> list[str]:
    problems = []

    readme = (BASE / "README.md").read_text(encoding="utf-8")
    banner = re.search(r"badge/version-([\d.]+)-", readme)
    if not banner:
        problems.append("README.md: version badge not found")
    elif banner.group(1) != version:
        problems.append(f"README.md: version badge is {banner.group(1)}")
    if f"V{version}" not in readme:
        problems.append(f"README.md: never mentions V{version}")

    changelog = (BASE / "CHANGELOG.md").read_text(encoding="utf-8")
    first = re.search(r"^## V([\d.]+)", changelog, re.MULTILINE)
    if not first:
        problems.append("CHANGELOG.md: no version section")
    elif first.group(1) != version:
        problems.append(f"CHANGELOG.md: newest section is V{first.group(1)}")

    notes = BASE / "docs" / f"release-notes-v{version}.md"
    if not notes.is_file():
        problems.append(f"docs/release-notes-v{version}.md: missing")

    index = BASE / ARCHIVE_INDEX
    if index.is_file():
        if version not in index.read_text(encoding="utf-8"):
            problems.append(f"{ARCHIVE_INDEX}: does not list {version}")
    else:
        problems.append(f"{ARCHIVE_INDEX}: missing")
    return problems


def check_pe(path: Path, version: str) -> list[str]:
    """Read FileVersion straight out of the UTF-16 StringFileInfo block.

    The master EXE ships an older version (1.3.2.2); after step 3 rewrites
    the resource this must equal version.json.
    """
    if not path.is_file():
        return [f"{path.name}: missing"]
    data = path.read_bytes()
    key = "FileVersion".encode("utf-16le")
    at = data.find(key)
    if at < 0:
        return [f"{path.name}: no FileVersion resource"]
    # key, NUL pad, then the value string, all UTF-16LE.
    tail = data[at + len(key):at + len(key) + 96]
    found = SEMVER.search(tail.decode("utf-16le", "ignore"))
    if not found:
        return [f"{path.name}: FileVersion value not readable"]
    if found.group(0) != version:
        return [f"{path.name}: PE FileVersion is {found.group(0)}"]
    return []


def main() -> int:
    version = read_version()
    problems: list[str] = []
    problems += check_scripts(version)
    problems += check_batch(version)
    problems += check_ui_texts(version)
    problems += check_docs(version)

    # --exe runs as the post-write check; the plain build step runs before
    # the version resource is patched, so the master's old number is expected.
    if "--exe" in sys.argv:
        problems += check_pe(BASE / "build" / "base_v1100.exe", version)

    if problems:
        print(f"version sync FAILED for {version} ({len(problems)} problems)")
        for item in problems:
            print("  -", item)
        return 1
    print(f"version sync OK {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

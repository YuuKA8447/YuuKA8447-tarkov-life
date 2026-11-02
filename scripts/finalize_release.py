"""Rename the stripped build to the Chinese release filename.

The batch file keeps every command-line path ASCII so cmd.exe cannot
misparse the multibyte release name; this final step performs the rename
inside Python, which handles Unicode paths reliably.
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
VERSION = json.loads((BASE / "version.json").read_text(encoding="utf-8"))["version"]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "build" / f"_V{VERSION}_stripped.exe"
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "build" / f"从零开始的塔科夫生活_V{VERSION}.exe"

if not SRC.is_file():
    raise SystemExit(f"missing stripped build: {SRC}")
SRC.replace(DST)
print(DST)

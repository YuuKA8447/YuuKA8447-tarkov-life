"""Rename the stripped build to the Chinese release filename.

The batch file keeps every command-line path ASCII so cmd.exe cannot
misparse the multibyte release name; this final step performs the rename
inside Python, which handles Unicode paths reliably.
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "build" / "_V1.4.1.0_stripped.exe"
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "build" / "从零开始的塔科夫生活_V1.4.1.0.exe"

if not SRC.is_file():
    raise SystemExit(f"missing stripped build: {SRC}")
SRC.replace(DST)
print(DST)

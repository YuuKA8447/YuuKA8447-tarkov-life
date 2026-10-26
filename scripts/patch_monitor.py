"""Patch monitor.marshal so the default hotkey is F1 instead of F10.

The monitor module is shipped as marshal bytecode without source, so the
default (0, 121) constant inside App.__init__ is rewritten to (0, 112).
The rewrite is recursive because the constant lives in a nested code object.
"""
from __future__ import annotations

import marshal
import shutil
import types
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TARGET = BASE / "monitor.marshal"
BACKUP = BASE / "build" / "_backup_20261025" / "monitor.marshal"
OLD = (0, 121)  # F10
NEW = (0, 112)  # F1


def rewrite(code):
    changed = 0
    consts = []
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            value, hits = rewrite(value)
            changed += hits
        elif value == OLD:
            value = NEW
            changed += 1
        consts.append(value)
    if changed:
        code = code.replace(co_consts=tuple(consts))
    return code, changed


def count_constant(code, target):
    total = 0
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            total += count_constant(value, target)
        elif value == target:
            total += 1
    return total


def main():
    original = TARGET.read_bytes()
    code = marshal.loads(original)
    patched, changed = rewrite(code)
    if changed == 0:
        if count_constant(code, NEW):
            print("already patched: default hotkey is F1 (0, 112)")
            return 0
        raise SystemExit("default hotkey constant (0, 121) not found")

    if BACKUP.is_file() and count_constant(
        marshal.loads(BACKUP.read_bytes()), OLD
    ):
        print("backup present", BACKUP)
    else:
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_bytes(original)
        print("backup written", BACKUP)

    TARGET.write_bytes(marshal.dumps(patched))
    verify = marshal.loads(TARGET.read_bytes())
    if count_constant(verify, OLD) or count_constant(verify, NEW) != changed:
        raise SystemExit("monitor hotkey patch did not round-trip")
    print(f"patched {changed} constant(s): (0, 121) -> (0, 112) = F1")
    print("written", TARGET, TARGET.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

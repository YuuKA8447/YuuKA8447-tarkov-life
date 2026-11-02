"""Fail the build when a checked-in .marshal drifts from its source.

An edited .py whose .marshal was never rebuilt ships the old logic, which
looks exactly like "my fix did nothing".  Both modules are rebuilt and
compared byte for byte.

marshal output is not a pure function of the source: it depends on the
intern state of the code object's filename and on how many live references
the blob carries.  Compiling both modules in one interpreter makes the
second one serialise differently, so each module is checked in its own
subprocess and gets exactly the recipe that produced its committed file:

  ui_compact.marshal       compile(text, "primary_ui.py", "exec") -> dumps
  sound_library.marshal    intern("sound_library.py"), compile, dumps once to
                           populate the ref table, then re-dump the code
                           object inside a 1-tuple and strip its 2-byte header

Both recipes were verified byte-identical to the committed files in a clean
interpreter.  If a compile script changes how it serialises, follow it here.
"""
from __future__ import annotations

import hashlib
import marshal
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

TARGETS = (
    # source, marshal, compile() filename, serialisation recipe
    ("ui_compact.py", "ui_compact.marshal", "primary_ui.py", "plain"),
    ("sound_library.py", "sound_library.marshal", "sound_library.py", "interned"),
)

WORKER = r'''
import hashlib, marshal, sys
text = sys.stdin.buffer.read().decode("utf-8")
filename, mode = sys.argv[1], sys.argv[2]
if mode == "interned":
    # sound_library.marshal was serialised with the filename already interned
    # and with a populated ref table, so reproduce both before dumping.
    sys.intern(filename)
    code = compile(text, filename, "exec")
    marshal.dumps(code)
    blob = marshal.dumps(code)
else:
    # ui_compact.marshal needs a non-empty ref table too, but must NOT intern
    # the filename: wrapping in a tuple and stripping its 2-byte header gives
    # the exact committed bytes.
    code = compile(text, filename, "exec")
    blob = marshal.dumps((code,))[2:]
print(hashlib.sha256(blob).hexdigest(), len(blob))
'''


def rebuild(source: str, filename: str, mode: str) -> tuple[str, int]:
    result = subprocess.run(
        [sys.executable, "-c", WORKER, filename, mode],
        input=(BASE / source).read_bytes(),
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"rebuild of {source} failed:\n"
            + result.stderr.decode("utf-8", "replace")
        )
    digest, size = result.stdout.decode().split()
    return digest, int(size)


def main() -> int:
    problems = []
    for source, marshal_name, filename, mode in TARGETS:
        src_path = BASE / source
        marshal_path = BASE / marshal_name
        if not src_path.is_file():
            problems.append(f"{source}: missing")
            continue
        if not marshal_path.is_file():
            problems.append(f"{marshal_name}: missing")
            continue
        digest, size = rebuild(source, filename, mode)
        actual = marshal_path.read_bytes()
        if hashlib.sha256(actual).hexdigest() == digest:
            print(f"marshal sync OK {marshal_name} ({len(actual)} bytes)")
            continue
        problems.append(
            f"{marshal_name}: stale ({len(actual)} B on disk, "
            f"{size} B rebuilt from {source})"
        )

    if problems:
        print(f"marshal sync FAILED ({len(problems)} problems)")
        for item in problems:
            print("  -", item)
        print("  rebuild with: tools\\py311\\python.exe scripts\\compile_ui.py")
        print("                tools\\py311\\python.exe scripts\\compile_sound_library.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

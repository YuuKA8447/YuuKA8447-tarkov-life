"""Dump monitor.marshal as a readable, annotated reference implementation.

The monitor module ships as marshal bytecode with no source in the repo, so
changing a default or tracing a code path meant reading a byte-offset patch.
This script walks the code objects and emits structured disassembly that a
human can follow, plus a summary of the module's shape.

It is a *reading aid*, not a build input: nothing here is compiled back.
Regenerate with:

    tools\\py311\\python.exe scripts\\dump_monitor_reference.py

Output: scripts\\reference\\monitor_reference.txt
"""
from __future__ import annotations

import dis
import marshal
import types
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SOURCE = BASE / "monitor.marshal"
OUT = BASE / "scripts" / "reference" / "monitor_reference.txt"

# Sections the module is documented in.  Leaf names are matched so nested
# helpers (App.worker.collect, App.record_key.<genexpr>) fall under the same
# heading as their owner.
SECTIONS = (
    ("A. 配置与热键", {
        "__init__", "build_ui", "fit_window", "write_preferences",
        "save_ui_theme", "apply_runtime_settings", "persist_session",
        "save_preparation", "save_advanced", "edit_delay", "edit_hz",
        "open_sound_settings", "play_sound", "select_sound",
        "open_shortcuts", "begin_record", "record_key", "record_combo",
        "check_shortcuts", "refresh_shortcuts", "apply_shortcut",
        "pick_sound", "drop_sound", "import_sound", "convert",
        "save_settings", "load_settings", "_load_settings", "_save_settings",
        "event", "cancel", "toggle", "close", "check_language",
        "set_language", "load_language", "shortcut_label", "combo_label",
        "apply_delay",
    }),
    ("B. 采集 worker 与定时", {
        "worker", "collect", "tick", "performance", "percentile",
        "observe_exit", "grab", "capture", "normalize", "send_alt_f4",
        "packet", "target",
    }),
    ("C. 撤离状态机", {
        "ExtractionGuard", "_extraction_step", "gate", "transition",
        "observe", "reset", "update", "hold", "release", "step",
    }),
    ("D. 窗口控件与提示", {
        "WindowsNotice", "show", "SquareToggle", "redraw",
        "MOUSEINPUT", "KEYBDINPUT", "HARDWAREINPUT", "INPUTUNION",
        "INPUT", "NOTIFYICONDATA", "open_log",
    }),
    ("E. 类容器与模块主体", {
        "App", "module", "<module>",
    }),
)


def flatten(root: types.CodeType):
    """Depth-first list of (path, code) pairs, stable order."""
    out = []

    def walk(code: types.CodeType, path: str):
        here = f"{path}.{code.co_name}" if path else code.co_name
        out.append((here, code))
        for value in code.co_consts:
            if isinstance(value, types.CodeType):
                walk(value, here)

    walk(root, "")
    return out


def classify(path: str) -> str:
    """Walk up the dotted path so lambdas/genexprs follow their owner."""
    parts = path.split(".")
    while parts:
        leaf = parts[-1]
        for label, names in SECTIONS:
            if leaf in names:
                return label
        parts.pop()
    return "unclassified"


def describe(code: types.CodeType, path: str) -> list[str]:
    lines = [
        f"### {path}",
        f"    flags={code.co_flags} args={code.co_argcount} "
        f"kwonly={code.co_kwonlyargcount} stack={code.co_stacksize} "
        f"bytecode={len(code.co_code)} bytes lines={code.co_firstlineno}",
    ]
    if code.co_varnames:
        lines.append(f"    varnames={code.co_varnames}")
    if code.co_freevars:
        lines.append(f"    freevars={code.co_freevars}")
    if code.co_names:
        lines.append(f"    names={code.co_names}")
    consts = [c for c in code.co_consts if not isinstance(c, types.CodeType)]
    if consts:
        lines.append(f"    consts={[repr(c) for c in consts]}")
    lines.append("")
    for item in dis.get_instructions(code):
        arg = "" if item.argval is None else f" {item.argval!r}"
        lines.append(f"    {item.offset:>6}  {item.opname}{arg}")
    lines.append("")
    return lines


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f"missing {SOURCE}")
    module = marshal.loads(SOURCE.read_bytes())
    units = flatten(module)

    buckets: dict[str, list[tuple[str, types.CodeType]]] = {}
    for path, code in units:
        buckets.setdefault(classify(path), []).append((path, code))

    lines = [
        "# monitor.marshal 参考实现（自动生成，勿手改）",
        "",
        f"源文件: {SOURCE.name}  {SOURCE.stat().st_size} 字节",
        f"代码对象: {len(units)} 个",
        "",
        "本文件由 scripts/dump_monitor_reference.py 从 marshal 字节码生成，",
        "用途是让人能读懂 monitor 的逻辑结构，不参与构建、不参与校验。",
        "修改 monitor 行为仍然走 scripts/patch_monitor*.py 的补丁链。",
        "",
        "## 目录",
        "",
    ]
    for label, _ in SECTIONS:
        items = buckets.get(label, [])
        lines.append(f"- {label}: {len(items)} 个代码对象")
    lines.append(f"- unclassified: {len(buckets.get('unclassified', []))} 个代码对象")
    lines.append("")

    for label, _ in SECTIONS:
        lines.append(f"\n{'=' * 70}\n== {label}\n{'=' * 70}\n")
        for path, code in buckets.get(label, []):
            lines.extend(describe(code, path))

    rest = buckets.get("unclassified", [])
    if rest:
        lines.append(f"\n{'=' * 70}\n== unclassified\n{'=' * 70}\n")
        for path, code in rest:
            lines.append(
                f"### {path}\n"
                f"    flags={code.co_flags} bytecode={len(code.co_code)} bytes"
            )
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(units)} code objects)")
    for label, _ in SECTIONS:
        print(f"  {label}: {len(buckets.get(label, []))}")
    print(f"  unclassified: {len(rest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

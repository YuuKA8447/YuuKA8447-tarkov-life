"""Install the extraction hold/end state into monitor.marshal.

The monitor script is shipped as marshal bytecode without source.  This patch:

1. Replaces the worker branch that cancelled monitoring as soon as
   ExtractionGuard returned True with a call to App._extraction_step.
2. Appends that helper to the App class body.

The worker branch keeps its original length: the new call sequence is 44 bytes
and the remaining 152 bytes become NOPs, so every existing jump/exception
offset stays valid.
"""
from __future__ import annotations

import dis
import marshal
import sys
import types
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TARGET = BASE / "monitor.marshal"
BACKUP = BASE / "build" / "_backup_20261025" / "monitor_before_extraction.marshal"

BRANCH_START = 6374
BRANCH_END = 6570
CALL_SITE = 6374

NOTICE_SHOW_SOURCE = '''
def show(self, text):
    enabled = text.startswith('监控中')
    actual_exit = '已发送一次 Alt+F4' in text
    silent = (
        text.startswith('撤离点已识别')
        or text.startswith('已回到战斗 HUD')
        or text.startswith('撤离结束')
        or '识别到撤离结束' in text
    )
    if actual_exit and self.return_sound_enabled:
        filename = 'return_by_death.wav'
    elif enabled:
        filename = 'enabled.wav'
    else:
        filename = 'disabled.wav'
    library = getattr(self, 'sound_library', None)
    if library:
        if actual_exit and self.return_sound_enabled:
            sound = library.resolve('exit')
        elif enabled:
            sound = library.resolve('enabled')
        else:
            sound = library.resolve('disabled')
    else:
        sound = Path(__file__).parent / 'assets' / filename
    audio_ok = False
    audio_allowed = not library or (
        not library.muted
        and library.enabled['exit' if actual_exit else ('enabled' if enabled else 'disabled')]
    )
    if library and actual_exit:
        sound = library.resolve('exit')
    if '--smoke-test' not in sys.argv and audio_allowed and sound is not None and not silent:
        try:
            winsound.PlaySound(
                str(sound),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
            audio_ok = True
        except RuntimeError:
            pass
    return dict(
        enabled=enabled,
        audio_requested=audio_ok,
        popup_accepted=False,
        windows_notifications_enabled=False,
    )
'''

HELPER_SOURCE = '''
def _extraction_step(self, guard, now):
    event = getattr(guard, 'event', None)
    if not event:
        return
    guard.event = None
    if event == 'b_hold':
        self.gate.active = False
        self.gate.missing = 0
        self.gate.missing_since = None
        try:
            if getattr(self.sounds, 'enabled', {}).get('disabled', True):
                self.play_sound('disabled')
        except Exception:
            pass
        self.event('extraction_hold', reason=guard.reason, source='B')
        self.ui.put(('status', '撤离点已识别 · 暂停 Alt+F4，继续检测'))
    elif event == 'm_end':
        self.gate.active = False
        self.gate.missing = 0
        self.gate.missing_since = None
        self.event('extraction_end', reason=guard.reason)
        self.ui.put(('status', '撤离结束 · 3 秒后停止监控'))
    elif event == 'resume':
        self.gate.active = True
        self.gate.missing = 0
        self.gate.missing_since = None
        self.gate.last_observation = None
        try:
            if getattr(self.sounds, 'enabled', {}).get('enabled', True):
                self.play_sound('enabled')
        except Exception:
            pass
        self.event('extraction_resume', reason=guard.reason)
        self.ui.put(('status', '已回到战斗 HUD · 恢复 Alt+F4'))
    elif event == 'finished':
        self.gate.active = False
        self.cancel('识别到撤离结束，停止监控（未发送 Alt+F4）')
        try:
            if getattr(self.sounds, 'enabled', {}).get('disabled', True):
                self.play_sound('disabled')
        except Exception:
            pass
'''

CACHES = {
    "LOAD_FAST": 0,
    "LOAD_DEREF": 0,
    "LOAD_CONST": 0,
    "LOAD_METHOD": 10,
    "MAKE_FUNCTION": 0,
    "PRECALL": 1,
    "CALL": 4,
    "POP_TOP": 0,
    "STORE_NAME": 0,
    "NOP": 0,
}


def find_code(code, name):
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            if value.co_name == name:
                return value
            found = find_code(value, name)
            if found is not None:
                return found
    return None


def encode(opname, arg=0):
    opcode = dis.opmap[opname]
    return bytes((opcode, arg)) + b"\x00\x00" * CACHES[opname]


def build_call(worker):
    names = list(worker.co_names)
    if "_extraction_step" not in names:
        names.append("_extraction_step")
    name_index = names.index("_extraction_step")
    guard_index = worker.co_varnames.index("extraction_guard")
    now_index = worker.co_varnames.index("now")
    if name_index > 255 or guard_index > 255 or now_index > 255:
        raise SystemExit("worker argument index exceeds one-byte encoding")
    call = b"".join((
        encode("LOAD_DEREF", 0),
        encode("LOAD_METHOD", name_index),
        encode("LOAD_FAST", guard_index),
        encode("LOAD_FAST", now_index),
        encode("PRECALL", 2),
        encode("CALL", 2),
        encode("POP_TOP"),
    ))
    if len(call) != 44:
        raise SystemExit(f"call sequence is {len(call)} bytes, expected 44")
    return call, tuple(names)


def patch_worker(worker):
    code = worker.co_code
    if len(code) <= BRANCH_END:
        raise SystemExit("worker code is shorter than the expected branch")
    if BRANCH_END - BRANCH_START != 196:
        raise SystemExit("branch size changed")

    instructions = {item.offset: item for item in dis.get_instructions(worker)}
    checks = {
        6370: ("LOAD_FAST", "extracted"),
        6372: ("POP_JUMP_FORWARD_IF_FALSE", 6570),
        6374: ("LOAD_DEREF", "self"),
        6398: ("LOAD_CONST", "extraction_transition"),
        6502: ("LOAD_METHOD", "cancel"),
    }
    for offset, (opname, argval) in checks.items():
        item = instructions.get(offset)
        if item is None or item.opname != opname:
            raise SystemExit(f"worker anchor {offset} is {item!r}, expected {opname}")
        if argval is not None and item.argval != argval:
            raise SystemExit(
                f"worker anchor {offset} arg is {item.argval!r}, expected {argval!r}"
            )
    for item in instructions.values():
        if (item.opname.startswith(("JUMP", "POP_JUMP", "FOR_ITER"))
                and isinstance(item.argval, int)
                and BRANCH_START <= item.argval < BRANCH_END):
            raise SystemExit(
                f"jump at {item.offset} enters replaced branch at {item.argval}"
            )

    call, names = build_call(worker)
    replacement = call + encode("NOP") * ((BRANCH_END - BRANCH_START - len(call)) // 2)
    if len(replacement) != BRANCH_END - BRANCH_START:
        raise SystemExit("replacement branch length mismatch")
    new_code = code[:BRANCH_START] + replacement + code[BRANCH_END:]
    if len(new_code) != len(code):
        raise SystemExit("worker code length changed")
    return worker.replace(co_code=new_code, co_names=names)


def inject_helper(app):
    names = list(app.co_names)
    if "_extraction_step" in names:
        raise SystemExit("App._extraction_step is already present")
    names.append("_extraction_step")
    name_index = len(names) - 1

    helper = find_code(
        compile(HELPER_SOURCE, "monitor.py", "exec"), "_extraction_step"
    )
    if helper is None:
        raise SystemExit("helper compile failed")
    consts = list(app.co_consts)
    consts.append(helper)
    helper_index = len(consts) - 1
    if helper_index > 255 or name_index > 255:
        raise SystemExit("App constant/name index exceeds one-byte encoding")

    tail = app.co_code[-4:]
    expected = bytes((dis.opmap["LOAD_CONST"], len(app.co_consts) - 1,
                      dis.opmap["RETURN_VALUE"], 0))
    if tail != expected:
        raise SystemExit(f"unexpected App class tail {tail.hex()} != {expected.hex()}")
    injection = b"".join((
        encode("LOAD_CONST", helper_index),
        encode("MAKE_FUNCTION", 0),
        encode("STORE_NAME", name_index),
    ))
    new_code = app.co_code[:-4] + injection + tail
    return app.replace(
        co_code=new_code,
        co_consts=tuple(consts),
        co_names=tuple(names),
        co_stacksize=max(app.co_stacksize, 1),
    )


def replace_app(module, new_app):
    consts = []
    hit = False
    for value in module.co_consts:
        if isinstance(value, types.CodeType) and value.co_name == "App":
            consts.append(new_app)
            hit = True
        else:
            consts.append(value)
    if not hit:
        raise SystemExit("App class not found")
    return module.replace(co_consts=tuple(consts))


def patch_notice(module):
    notice = find_code(module, "WindowsNotice")
    if notice is None:
        raise SystemExit("WindowsNotice class not found")
    show = find_code(notice, "show")
    if show is None:
        raise SystemExit("WindowsNotice.show not found")
    if "撤离点已识别" in show.co_consts:
        return module, False

    new_show = find_code(
        compile(NOTICE_SHOW_SOURCE, "monitor.py", "exec"), "show"
    )
    if new_show is None:
        raise SystemExit("notice show compile failed")
    new_show = new_show.replace(
        co_qualname="WindowsNotice.show",
        co_filename=show.co_filename,
        co_firstlineno=show.co_firstlineno,
    )

    consts = list(notice.co_consts)
    for index, value in enumerate(consts):
        if isinstance(value, types.CodeType) and value.co_name == "show":
            consts[index] = new_show
            break
    else:
        raise SystemExit("WindowsNotice.show constant not found")
    new_notice = notice.replace(co_consts=tuple(consts))

    consts = list(module.co_consts)
    for index, value in enumerate(consts):
        if isinstance(value, types.CodeType) and value.co_name == "WindowsNotice":
            consts[index] = new_notice
            break
    else:
        raise SystemExit("WindowsNotice class constant not found")
    return module.replace(co_consts=tuple(consts)), True


def verify_notice(module):
    notice = find_code(module, "WindowsNotice")
    show = find_code(notice, "show") if notice is not None else None
    if show is None:
        raise SystemExit("WindowsNotice.show missing after patch")
    strings = {value for value in show.co_consts if isinstance(value, str)}
    required = {
        "撤离点已识别", "已回到战斗 HUD", "撤离结束", "识别到撤离结束"
    }
    missing = required - strings
    if missing:
        raise SystemExit(f"notice silence markers missing: {sorted(missing)}")
    return show


def verify(module):
    app = find_code(module, "App")
    worker = find_code(module, "worker")
    if app is None or worker is None:
        raise SystemExit("App or worker missing after patch")
    if find_code(app, "_extraction_step") is None:
        raise SystemExit("App._extraction_step missing after patch")
    if len(worker.co_code) != 8854:
        raise SystemExit(f"worker code size changed to {len(worker.co_code)}")
    items = {item.offset: item for item in dis.get_instructions(worker)}
    expected = [
        (CALL_SITE, "LOAD_DEREF", "self"),
        (6376, "LOAD_METHOD", "_extraction_step"),
        (6398, "LOAD_FAST", "extraction_guard"),
        (6400, "LOAD_FAST", "now"),
        (6402, "PRECALL", 2),
        (6406, "CALL", 2),
        (6416, "POP_TOP", None),
    ]
    for offset, opname, argval in expected:
        item = items.get(offset)
        if item is None or item.opname != opname:
            raise SystemExit(f"call site {offset} is {item!r}, expected {opname}")
        if argval is not None and item.argval != argval:
            raise SystemExit(
                f"call site {offset} arg is {item.argval!r}, expected {argval!r}"
            )
    for offset in range(CALL_SITE + 44, BRANCH_END, 2):
        item = items.get(offset)
        if item is None or item.opname != "NOP":
            raise SystemExit(f"padding at {offset} is {item!r}, expected NOP")
    if items[BRANCH_END].opname != "LOAD_DEREF":
        raise SystemExit("gate update entry is not LOAD_DEREF after padding")
    if items[BRANCH_END].argval != "self":
        raise SystemExit("gate update entry changed after patch")
    return app, worker


def main() -> int:
    original = TARGET.read_bytes()
    module = marshal.loads(original)
    worker = find_code(module, "worker")
    app = find_code(module, "App")
    if worker is None or app is None:
        raise SystemExit("worker or App not found")

    module, notice_changed = patch_notice(module)
    if notice_changed:
        print("notice sound filter installed")

    if "_extraction_step" in app.co_names:
        verify(module)
        verify_notice(module)
        if notice_changed:
            payload = marshal.dumps(module)
            TARGET.write_bytes(payload)
            print("monitor.marshal", len(original), "->", len(payload), "bytes")
            print("written", TARGET, TARGET.stat().st_size, "bytes")
        else:
            print("already patched: App._extraction_step present")
        return 0

    if BACKUP.is_file():
        print("backup present", BACKUP)
    else:
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        BACKUP.write_bytes(original)
        print("backup written", BACKUP)

    new_worker = patch_worker(worker)
    new_app = inject_helper(app)
    inner = []
    hit = False
    for value in new_app.co_consts:
        if isinstance(value, types.CodeType) and value.co_name == "worker":
            inner.append(new_worker)
            hit = True
        else:
            inner.append(value)
    if not hit:
        raise SystemExit("worker replacement did not hit App class body")
    new_app = new_app.replace(co_consts=tuple(inner))
    patched = replace_app(module, new_app)
    verify(patched)
    verify_notice(patched)

    payload = marshal.dumps(patched)
    TARGET.write_bytes(payload)
    print("monitor.marshal", len(original), "->", len(payload), "bytes")
    try:
        from zopfli.zlib import compress
        print("zopfli", len(compress(payload)))
    except ImportError:
        pass
    print("written", TARGET, TARGET.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

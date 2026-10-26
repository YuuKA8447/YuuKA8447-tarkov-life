"""Exercise the extraction hold/end state machine and the monitor helper."""
from __future__ import annotations

import marshal
import sys
import types
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DETECTOR = BASE / "detector.marshal"
MONITOR = BASE / "monitor.marshal"
UI = BASE / "ui_compact.marshal"
SOUND = BASE / "sound_library.marshal"


def load_detector():
    if "timer_digits" not in sys.modules:
        stub = types.ModuleType("timer_digits")

        class TimerDigits:
            def __init__(self, *args, **kwargs):
                self.templates = []

        stub.TimerDigits = TimerDigits
        sys.modules["timer_digits"] = stub
    code = marshal.loads(DETECTOR.read_bytes())
    namespace = {"__name__": "detector", "__file__": str(BASE / "detector.py")}
    exec(code, namespace)
    return namespace


def find_code(code, name):
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            if value.co_name == name:
                return value
            found = find_code(value, name)
            if found is not None:
                return found
    return None


def cue(banner=False, blackout=False, end=False, bar=1.0, body=1.0):
    return {
        "banner": banner,
        "blackout": blackout,
        "end": end,
        "bar_frames": bar,
        "body_shape": body,
        "scene_luma": 0 if blackout else 50,
    }


def feed(guard, now, combat=0.8, menu=False, **kwargs):
    guard.event = None
    returned = guard.update(now, combat, menu, cue(**kwargs))
    event = guard.event
    guard.event = None
    return returned, event


def run_guard_scenarios(guard_class):
    failures = []

    def expect(case, actual, wanted):
        if actual != wanted:
            failures.append(f"{case}: {actual!r} != {wanted!r}")

    guard = guard_class()
    events = []
    for args, kwargs in (
        ((0.0,), {"banner": True}),
        ((0.2,), {"banner": True}),
        ((0.5,), {}),
        ((0.9,), {"bar": 0.15, "body": 0.30}),
        ((1.1,), {"blackout": True, "bar": 0.0, "body": 0.0}),
        ((1.4,), {"end": True, "bar": 0.0, "body": 0.0}),
        ((4.2,), {"end": True, "bar": 0.0, "body": 0.0}),
        ((4.6,), {"bar": 0.0, "body": 0.0}),
    ):
        _, event = feed(guard, *args, combat=0.8 if args[0] < 1 else 0.05,
                        **kwargs)
        if event:
            events.append(event)
    expect("success-event-sequence", events, ["b_hold", "m_end", "finished"])
    expect("success-mode", guard.mode, "done")
    expect("success-hold", guard.hold, False)

    guard = guard_class()
    events = []
    for now, combat, kwargs in (
        (0.0, 0.8, {"banner": True}),
        (0.5, 0.8, {}),
        (5.4, 0.8, {}),
        (5.6, 0.8, {}),
    ):
        _, event = feed(guard, now, combat=combat, **kwargs)
        if event:
            events.append(event)
    expect("passby-event-sequence", events, ["b_hold", "resume"])
    expect("passby-hold", guard.hold, False)

    guard = guard_class()
    events = []
    for now, combat, menu, kwargs in (
        (0.0, 0.8, False, {"banner": True}),
        (0.5, 0.1, True, {}),
        (1.5, 0.8, False, {}),
        (5.4, 0.8, False, {}),
        (5.6, 0.8, False, {}),
    ):
        _, event = feed(guard, now, combat=combat, menu=menu, **kwargs)
        if event:
            events.append(event)
    expect("menu-event-sequence", events, ["b_hold", "resume"])

    guard = guard_class()
    events = []
    for now, combat, kwargs in (
        (0.0, 0.8, {"banner": True}),
        (0.5, 0.8, {}),
        (1.5, 0.8, {}),
        (2.4, 0.8, {}),
        (2.6, 0.05, {"blackout": True, "bar": 0.0, "body": 0.0}),
        (5.0, 0.05, {"end": True, "bar": 0.0, "body": 0.0}),
        (8.2, 0.05, {"end": True, "bar": 0.0, "body": 0.0}),
    ):
        _, event = feed(guard, now, combat=combat, **kwargs)
        if event:
            events.append(event)
    expect("2s-a-then-black-event-sequence", events,
           ["b_hold", "m_end", "finished"])
    expect("2s-a-then-black-no-resume", "resume" in events, False)

    guard = guard_class()
    events = []
    for now in (10.0, 12.9, 13.1):
        _, event = feed(guard, now, combat=0.05,
                        end=now < 13.0, bar=0.0, body=0.0)
        if event:
            events.append(event)
    expect("direct-m-event-sequence", events, ["m_end", "finished"])

    return failures


def run_helper_tests():
    module = marshal.loads(MONITOR.read_bytes())
    app = find_code(module, "App")
    helper = find_code(app, "_extraction_step") if app else None
    if helper is None:
        return ["monitor helper missing"]
    function = types.FunctionType(helper, {"__name__": "monitor"})

    class Gate:
        active = True
        missing = 4
        missing_since = 123.0
        last_observation = 99.0

    class Sounds:
        enabled = {"enabled": True, "disabled": True}
        muted = False

    class Guard:
        def __init__(self, event):
            self.event = event
            self.reason = "test_reason"

    class Host:
        def __init__(self):
            self.gate = Gate()
            self.sounds = Sounds()
            self.events = []
            self.statuses = []
            self.played = []
            self.cancel_reason = None

        def play_sound(self, name):
            self.played.append(name)

        def event(self, kind, **details):
            self.events.append((kind, details))

        def cancel(self, reason):
            self.cancel_reason = reason
            self.gate.active = False

        class UI:
            def __init__(self, outer):
                self.outer = outer

            def put(self, value):
                self.outer.statuses.append(value)

        @property
        def ui(self):
            return Host.UI(self)

    failures = []

    def expect(case, actual, wanted):
        if actual != wanted:
            failures.append(f"{case}: {actual!r} != {wanted!r}")

    host = Host()
    guard = Guard("b_hold")
    function(host, guard, 1.0)
    expect("b-hold-gate", host.gate.active, False)
    expect("b-hold-sound", host.played, ["disabled"])
    expect("b-hold-event", [item[0] for item in host.events],
           ["extraction_hold"])
    expect("b-hold-status", "撤离点已识别" in host.statuses[0][1], True)
    expect("b-hold-consumed", guard.event, None)

    host = Host()
    function(host, Guard("m_end"), 2.0)
    expect("m-end-gate", host.gate.active, False)
    expect("m-end-sound", host.played, [])
    expect("m-end-event", [item[0] for item in host.events],
           ["extraction_end"])
    expect("m-end-status", "3 秒" in host.statuses[0][1], True)

    host = Host()
    host.gate.active = False
    function(host, Guard("resume"), 3.0)
    expect("resume-gate", host.gate.active, True)
    expect("resume-observation", host.gate.last_observation, None)
    expect("resume-sound", host.played, ["enabled"])
    expect("resume-event", [item[0] for item in host.events],
           ["extraction_resume"])

    host = Host()
    function(host, Guard("finished"), 4.0)
    expect("finished-gate", host.gate.active, False)
    expect("finished-cancel", "撤离结束" in (host.cancel_reason or ""), True)
    expect("finished-sound", host.played, ["disabled"])

    host = Host()
    function(host, Guard(None), 5.0)
    expect("no-event", (host.played, host.events, host.statuses), ([], [], []))

    return failures


def run_sound_checks():
    """Default enabled/disabled cues must point at different, correct files."""
    namespace = {"__name__": "sound_library"}
    exec(marshal.loads(SOUND.read_bytes()), namespace)
    presets = namespace["PRESETS"]
    defaults = namespace["DEFAULTS"]
    failures = []
    if presets.get(defaults.get("enabled")) != "enabled.wav":
        failures.append("default enabled cue is not enabled.wav")
    if presets.get(defaults.get("disabled")) != "disabled.wav":
        failures.append("default disabled cue is not disabled.wav")
    if defaults.get("enabled") == defaults.get("disabled"):
        failures.append("enabled and disabled share the same default cue")
    return failures


def run_notice_sound_checks():
    """Extraction statuses must not get an extra status-bar sound."""
    failures = []
    module = marshal.loads(MONITOR.read_bytes())
    notice = find_code(module, "WindowsNotice")
    show = find_code(notice, "show") if notice is not None else None
    if show is None:
        return ["WindowsNotice.show missing"]

    class FakeLibrary:
        def __init__(self):
            self.muted = False
            self.enabled = {"enabled": True, "disabled": True, "exit": True}
            self.resolved = []

        def resolve(self, key):
            self.resolved.append(key)
            return Path("fake.wav")

    class FakeWinsound:
        SND_FILENAME = 1
        SND_ASYNC = 2
        SND_NODEFAULT = 4
        calls = []

        @classmethod
        def PlaySound(cls, path, flags):
            cls.calls.append((path, flags))

    class FakeSelf:
        return_sound_enabled = True

        def __init__(self):
            self.sound_library = FakeLibrary()

    class FakeSys:
        argv = []

    function = types.FunctionType(
        show,
        {
            "Path": Path,
            "sys": FakeSys,
            "winsound": FakeWinsound,
            "getattr": getattr,
        },
    )

    cases = (
        ("监控中 · F1 可停止", 1, "enabled"),
        ("已关闭 · F1 关闭", 1, "disabled"),
        ("撤离点已识别 · 暂停 Alt+F4，继续检测", 0, None),
        ("已回到战斗 HUD · 恢复 Alt+F4", 0, None),
        ("撤离结束 · 3 秒后停止监控", 0, None),
        ("已关闭 · 识别到撤离结束，停止监控（未发送 Alt+F4）", 0, None),
        ("已发送一次 Alt+F4", 1, "exit"),
    )
    for text, wanted, wanted_key in cases:
        FakeWinsound.calls.clear()
        fake = FakeSelf()
        result = function(fake, text)
        got = len(FakeWinsound.calls)
        if got != wanted:
            failures.append(f"notice {text!r}: {got} calls != {wanted}")
        if wanted == 0 and result.get("audio_requested") is not False:
            failures.append(f"notice {text!r}: audio_requested is not false")
        if wanted and (not fake.sound_library.resolved
                       or fake.sound_library.resolved[-1] != wanted_key):
            failures.append(
                f"notice {text!r}: cue {fake.sound_library.resolved!r} != {wanted_key!r}"
            )
    return failures


def run_ui_checks():
    """The UI layer must not stop monitoring on its own when B appears."""
    failures = []
    root = marshal.loads(UI.read_bytes())
    legacy_text = "识别到撤离点绿色横幅"

    def walk(scope):
        for value in scope.co_consts:
            if isinstance(value, types.CodeType):
                if value.co_name == "_extraction_standby":
                    failures.append("ui still defines _extraction_standby")
                walk(value)
            elif isinstance(value, str) and legacy_text in value:
                failures.append("ui still contains the legacy B cancel text")

    walk(root)
    return failures


def main() -> int:
    try:
        import cv2  # noqa: F401
    except ImportError:
        candidates = []
        temp_site = Path.home() / "AppData" / "Local" / "Temp"
        candidates.append(temp_site / "tarkov_v129_cv2" / "site")
        candidates.append(BASE / "build" / "_offline_deps")
        for candidate in candidates:
            if candidate.is_dir():
                sys.path.insert(0, str(candidate))
                break
    namespace = load_detector()
    failures = []
    failures.extend(run_guard_scenarios(namespace["ExtractionGuard"]))
    failures.extend(run_helper_tests())
    failures.extend(run_ui_checks())
    failures.extend(run_notice_sound_checks())
    failures.extend(run_sound_checks())
    if failures:
        print("FAILURES")
        for item in failures:
            print(" -", item)
        return 1
    print("OK success B -> Z -> M -> 3s -> finished")
    print("OK pass-by B -> 5s stable A -> resume")
    print("OK menu bypass B -> 5s stable A -> resume")
    print("OK B -> 2s A -> Z -> M without a false resume")
    print("OK direct M -> 3s -> finished")
    print("OK monitor helper gate/sound/cancel")
    print("OK extraction statuses add no status-bar sound")
    print("OK default enabled/disabled cues are distinct")
    print("ALL EXTRACTION FLOW CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

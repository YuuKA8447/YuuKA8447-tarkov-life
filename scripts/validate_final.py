"""Verify the rebuilt EXE against the project modules and embedded assets."""
import hashlib
import marshal
import os
import struct
import sys
import types
import zlib
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
EXE = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "build" / "从零开始的塔科夫生活_V1.4.1.0.exe"
COOKIE = b"MEI\x0c\x0b\x0a\x0b\x0e"

REQUIRED_ASSETS = {
    "assets\\subaru_clean.ico",
    "assets\\enabled.wav",
    "assets\\disabled.wav",
    "assets\\return_by_death.wav",
    "assets\\return_by_death.mp3",
    "assets\\killer_queen.wav",
    "assets\\duckov_extract.wav",
}

REMOVED_ASSETS = {
    "assets\\bin.png",
    "assets\\emilia.ico",
    "assets\\emilia.png",
    "assets\\emilia_head.png",
    "assets\\mascot.png",
    "assets\\mascot_ui.png",
    "assets\\return_by_death.ico",
    "assets\\subaru_clean.png",
    "assets\\rewind.wav",
    "assets\\quest_completed.wav",
    "assets\\ui_v2\\manifest.json",
    "assets\\fonts\\Arvo-Bold.ttf",
    "assets\\fonts\\Arvo-Italic-4.ttf",
    "assets\\fonts\\Plix-Medium.otf",
    "assets\\fonts\\Plix-Regular.otf",
    "assets\\fonts\\Plix-SemiBold.otf",
    "assets\\bar.png",
    "assets\\bar_horizontal.png",
    "assets\\bar_vertical.png",
    "assets\\body_shape.npz",
    "assets\\confirm_subtitle.png",
    "assets\\confirm_title.png",
    "assets\\extract_title.png",
    "assets\\extract_zero.png",
    "assets\\health.png",
    "assets\\label_shape.png",
    "assets\\menu_return.png",
    "assets\\menu_tabs.png",
    "assets\\pause_logo_left.png",
    "assets\\pause_logo_right.png",
    "assets\\settings_return.png",
    "assets\\settings_title.png",
    "assets\\timer_digits.npz",
}

EMBEDDED_TEMPLATES = {
    "hud_hotbar", "hud_body", "hud_body_169", "extract_B", "extract_found",
    "end_M", "console_K", "pause_C", "pause_C_lab", "pause_C_factory",
    "pause_C_nameless", "pause_C_forest", "menu_return", "settings_L",
    "tabs_D", "tabs_E", "tabs_F", "tabs_G", "tabs_H", "tabs_I", "tabs_J",
}

REMOVED_PACKAGES = {
    "cv2\\opencv_videoio_ffmpeg500_64.dll",
    "libscipy_openblas64_-63c857e738469261263c764a36be9436.dll",
}

buf = EXE.read_bytes()
cp = buf.rfind(COOKIE)
magic, pkg_len, toc_off, toc_len, pyver, pylib = struct.unpack("!8sIIii64s", buf[cp:cp + 88])
tail = len(buf) - cp - 88
overlay = len(buf) - (pkg_len + tail)
toc = buf[overlay + toc_off:overlay + toc_off + toc_len]

entries = {}
pos = 0
while pos < len(toc):
    es, = struct.unpack("!i", toc[pos:pos + 4])
    epos, cmprsd, uncmprsd, flag, typ, name = struct.unpack(
        "!IIIBc" + str(es - 18) + "s", toc[pos + 4:pos + es]
    )
    entries[name.decode("utf-8", "replace").rstrip("\0")] = {
        "pos": epos, "cmprsd": cmprsd, "uncmprsd": uncmprsd,
        "flag": flag, "type": typ,
    }
    pos += es


def asset(name):
    e = entries[name]
    raw = buf[overlay + e["pos"]:overlay + e["pos"] + e["cmprsd"]]
    return zlib.decompress(raw) if e["flag"] == 1 else raw


missing_required = sorted(REQUIRED_ASSETS - set(entries))
if missing_required:
    raise RuntimeError(f"missing required assets: {missing_required}")
still_removed = sorted(REMOVED_ASSETS & set(entries))
if still_removed:
    raise RuntimeError(f"unused assets still embedded: {still_removed}")
ui_v2 = sorted(name for name in entries if name.startswith("assets\\ui_v2\\"))
fonts = sorted(name for name in entries if name.startswith("assets\\fonts\\"))
if ui_v2 or fonts:
    raise RuntimeError(f"legacy ui_v2/fonts remain: {ui_v2 + fonts}")
trimmed = sorted(REMOVED_PACKAGES & set(entries))
trimmed += sorted(name for name in entries if name.startswith("PIL\\"))
if trimmed:
    raise RuntimeError(f"trimmed packages still embedded: {trimmed}")
if len(entries) != 1193:
    raise RuntimeError(f"unexpected archive entry count: {len(entries)}")
print("asset cleanup", len(REQUIRED_ASSETS), "required present;",
      len(REMOVED_ASSETS), "legacy absent;",
      len(REMOVED_PACKAGES) + 1, "package groups absent; entries", len(entries))

ico = (BASE / "build" / "icons" / "first_icon.ico").read_bytes()
wav = (BASE / "assets" / "audio" / "itachi_exit_v2_35.wav").read_bytes()
print("icon asset match", asset("assets\\subaru_clean.ico") == ico,
      len(asset("assets\\subaru_clean.ico")))
print("sound asset match", asset("assets\\duckov_extract.wav") == wav,
      len(asset("assets\\duckov_extract.wav")))

pyz_e = entries["PYZ.pyz"]
pyz_off = overlay + pyz_e["pos"]
pyz = buf[pyz_off:pyz_off + pyz_e["cmprsd"]]
pyz_toc_pos = struct.unpack(">i", pyz[8:12])[0]
pyz_toc = dict(marshal.loads(pyz[pyz_toc_pos:]))
for name, file in (("primary_ui", "ui_compact.marshal"),
                   ("sound_library", "sound_library.marshal"),
                   ("detector", "detector.marshal")):
    is_pkg, mpos, mlen = pyz_toc[name]
    blob = zlib.decompress(pyz[mpos:mpos + mlen])
    want = (BASE / file).read_bytes()
    if blob != want:
        raise RuntimeError(f"{name} does not match {file}")
    print(name, "match True", "slot", mlen, "unc", len(blob))
    print(name, "sha", hashlib.sha256(blob).hexdigest()[:16])

# The monitor main script is a CArchive script entry, not a PYZ module.
monitor_blob = asset("monitor")
monitor_want = (BASE / "monitor.marshal").read_bytes()
if monitor_blob != monitor_want:
    raise RuntimeError("monitor does not match monitor.marshal")
print("monitor match True", "unc", len(monitor_blob))
print("monitor sha", hashlib.sha256(monitor_blob).hexdigest()[:16])

# The detector must carry every ui识别 template inside its code constants; if
# one is missing the EXE would start but silently fall back to "0" forever.
_, _, detector_len = pyz_toc["detector"]
detector_blob = zlib.decompress(pyz[pyz_toc["detector"][1]:
                                   pyz_toc["detector"][1] + detector_len])
try:
    import cv2  # noqa: F401
except ImportError:
    candidates = []
    env_site = os.environ.get("TARKOV_CV2_SITE")
    if env_site:
        candidates.append(Path(env_site))
    temp_site = os.environ.get("TEMP")
    if temp_site:
        candidates.append(Path(temp_site) / "tarkov_v129_cv2" / "site")
    candidates.append(BASE / "build" / "_offline_deps")
    for candidate in candidates:
        if candidate.is_dir():
            sys.path.insert(0, str(candidate))
            break
    import cv2  # noqa: F401
namespace = {"__name__": "detector", "__file__": str(BASE / "detector.py")}
timer_stub = types.ModuleType("timer_digits")
timer_stub.TimerDigits = type(
    "TimerDigits", (),
    {"__init__": lambda self, *a, **k: setattr(self, "templates", [])},
)
sys.modules.setdefault("timer_digits", timer_stub)
exec(marshal.loads(detector_blob), namespace)
detector = namespace["Detector"]()
loaded = set(detector.iface_templates)
if loaded != EMBEDDED_TEMPLATES:
    raise RuntimeError(
        f"detector template set mismatch: missing={sorted(EMBEDDED_TEMPLATES - loaded)} "
        f"extra={sorted(loaded - EMBEDDED_TEMPLATES)}"
    )
print("detector templates decoded", len(loaded))

print("size", len(buf), "sha256", hashlib.sha256(buf).hexdigest().upper())

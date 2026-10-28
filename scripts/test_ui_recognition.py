"""Run the patched detector against every screenshot in ui识别.

This is a real regression: it executes detector.marshal (the same blob that is
packed into the EXE), feeds each screenshot through Detector.analyze, and
checks the interface code.  It also runs the cropped-top-strip path used by the
live monitor so a full-screen-only test cannot hide a normalize bug.
"""
from __future__ import annotations

import marshal
import os
import sys
import time
import types
from pathlib import Path

try:
    import cv2
except ImportError:
    candidates = []
    env_site = os.environ.get("TARKOV_CV2_SITE")
    if env_site:
        candidates.append(Path(env_site))
    temp_site = os.environ.get("TEMP")
    if temp_site:
        candidates.append(Path(temp_site) / "tarkov_v129_cv2" / "site")
    candidates.append(Path(__file__).resolve().parent.parent / "build" / "_offline_deps")
    for candidate in candidates:
        if candidate.is_dir():
            sys.path.insert(0, str(candidate))
            break
    import cv2
import numpy as np

BASE = Path(__file__).resolve().parent.parent
UI_ROOT = BASE / "ui识别"
MARSHAL = BASE / "detector.marshal"
FOUND_BANNER = (
    UI_ROOT / "画面识别 B 撤离点,战斗HUD" / "找到撤离点_黑名单(不参与识别).png"
)

IMAGES = {
    "A1": "画面识别 A 入场界面,战斗HUD/测试图2560 1600 16：10/A39_0.887.png",
    "A2": "画面识别 A 入场界面,战斗HUD/测试图2560 1600 16：10/A40_0.929.png",
    "A3": "画面识别 A 入场界面,战斗HUD/测试图2560 1600 16：10/A41_0.869.png",
    "A4": "画面识别 A 入场界面,战斗HUD/测试图2560 1600 16：10/A42_0.875.png",
    "N1": "画面识别 B 撤离点,战斗HUD/测试图/B1_1.000.png",
    "N2": "画面识别 B 撤离点,战斗HUD/测试图/B2_1.000.png",
    "N3": "画面识别 B 撤离点,战斗HUD/测试图/B3_1.000.png",
    "N4": "画面识别 B 撤离点,战斗HUD/测试图/B4_1.000.png",
    "Q": "画面识别 C 二级菜单,游戏主页面/测试图/C4_1.000.png",
    "Q2": "画面识别 C 二级菜单,游戏主页面/测试图/C1_0.993.png",
    "Q3": "画面识别 C 二级菜单,游戏主页面/测试图/C2_1.000.png",
    "Q4": "画面识别 C 二级菜单,游戏主页面/测试图/C3_0.985.png",
    "Q5": "画面识别 C 二级菜单,游戏主页面/测试图/C5_0.989.png",
    "B1": "画面识别 D 二级菜单,背包界面/测试图/D3_1.000.png",
    "B2": "画面识别 D 二级菜单,背包界面/测试图/D4_1.000.png",
    "B3": "画面识别 D 二级菜单,背包界面/测试图/D1_0.755.png",
    "B4": "画面识别 D 二级菜单,背包界面/测试图/D2_0.714.png",
    "C": "画面识别 E 二级菜单,总览/测试图/E1_1.000.png",
    "D": "画面识别 F 二级菜单,健康/测试图/F1_1.000.png",
    "E": "画面识别 G 二级菜单,成就/测试图/G1_1.000.png",
    "H": "测试画面 H 二级菜单,地图/测试图/H1_1.000.png",
    "G": "画面识别 I 二级菜单,任务/测试图/I1_1.000.png",
    "O": "画面识别 J 二级菜单,成就/测试图/J1_1.000.png",
    "P": "画面识别 K 二级菜单,控制台/测试图/K1_1.000.png",
    "L1": "画面识别 L 三级菜单,设置/测试图/L1_1.000.png",
    "L2": "画面识别 L 三级菜单,设置/测试图/L2_0.995.png",
    "L3": "画面识别 L 三级菜单,设置/测试图/L3_0.996.png",
    "L4": "画面识别 L 三级菜单,设置/测试图/L4_0.995.png",
    "L5": "画面识别 L 三级菜单,设置/测试图/L5_0.995.png",
    "M1": "画面识别 M 撤离结束/测试图/M1_1.000.png",
    "M2": "画面识别 M 撤离结束/测试图/M2_0.970.png",
    "M3": "画面识别 M 撤离结束/测试图/M3_0.970.png",
    "M4": "画面识别 M 撤离结束/测试图/M4_0.945.png",
    "M5": "画面识别 M 撤离结束/测试图/M5_0.941.png",
}

# Detection codes follow the ui识别 folder letters exactly.  A folder letter
# is used verbatim as the interface code; U is the unknown-menu fallback.
EXPECTED = {
    "A1": "A", "A2": "A", "A3": "A", "A4": "A",
    "N1": "B", "N2": "B", "N3": "B", "N4": "B",
    "Q": "C", "Q2": "C", "Q3": "C", "Q4": "C", "Q5": "C",
    "B1": "D", "B2": "D", "B3": "D", "B4": "D",
    "C": "E", "D": "F", "E": "G", "H": "H", "G": "I", "O": "J", "P": "K",
    "L1": "L", "L2": "L", "L3": "L", "L4": "L", "L5": "L",
    "M1": "M", "M2": "M", "M3": "M", "M4": "M", "M5": "M",
}


def discover_169():
    """Collect the real 2560x1440 samples added under every category."""
    cases = {}
    for folder in sorted(UI_ROOT.iterdir()):
        if not folder.is_dir():
            continue
        code = None
        parts = folder.name.split()
        for index, part in enumerate(parts[:-1]):
            if part in ("画面识别", "测试画面") and len(parts[index + 1]) == 1:
                code = parts[index + 1]
        if code is None:
            continue
        sub = folder / "测试图2560 1440 16：9"
        if not sub.is_dir():
            continue
        for number, path in enumerate(sorted(sub.glob("*.png")), 1):
            key = f"{code}169-{number}"
            cases[key] = (str(path.relative_to(UI_ROOT)), code)
    return cases


CASES = {key: (path, EXPECTED[key]) for key, path in IMAGES.items()}
CASES.update(discover_169())

# Overexposed / semi-transparent tab-bar crops.  They are pasted onto a blank
# 2560x1600 frame so the normal normalize_top + analyze path is exercised.
OVER_SLICES = {
    "overD": ("画面识别 D 二级菜单,背包界面/识别画面G.png", "D"),
    "overE": ("画面识别 E 二级菜单,总览/识别画面E.png", "E"),
    "overF": ("画面识别 F 二级菜单,健康/画面识别D.png", "F"),
    "overG": ("画面识别 G 二级菜单,成就/识别画面C.png", "G"),
    "overH": ("测试画面 H 二级菜单,地图/识别画面B.png", "H"),
    "overI": ("画面识别 I 二级菜单,任务/识别画面B.png", "I"),
    "overJ": ("画面识别 J 二级菜单,成就/识别画面C.png", "J"),
}


def load_detector_module():
    if "timer_digits" not in sys.modules:
        stub = types.ModuleType("timer_digits")

        class TimerDigits:
            def __init__(self, *args, **kwargs):
                self.templates = []

        stub.TimerDigits = TimerDigits
        sys.modules["timer_digits"] = stub
    code = marshal.loads(MARSHAL.read_bytes())
    namespace = {"__name__": "detector", "__file__": str(BASE / "detector.py")}
    exec(code, namespace)
    return namespace


def read_image(relative: str):
    path = UI_ROOT / relative
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def run_case(detector, image):
    return detector.analyze(image)


def main() -> int:
    namespace = load_detector_module()
    Detector = namespace["Detector"]
    detector = Detector()

    failures = []
    timings = []
    print("full-frame path")
    for key, (relative, expected) in CASES.items():
        image = read_image(relative)
        began = time.perf_counter()
        scores, menu = run_case(detector, image)
        elapsed = (time.perf_counter() - began) * 1000
        timings.append(elapsed)
        actual = detector.last_interface
        status = "OK" if actual == expected else "FAIL"
        if actual != expected:
            failures.append((key, expected, actual))
        combat = detector.last_features.get("combat_score", 0)
        banner = (detector.last_extraction or {}).get("banner")
        extraction = detector.last_extraction or {}
        if expected != "M" and extraction.get("end_score", 0) >= .78:
            failures.append((key + "-end-false-positive", 0,
                             extraction.get("end_score")))
        print(f"{status:4s} {key:7s} expect={expected:1s} got={actual:1s} "
              f"combat={combat:.3f} menu={menu:.2f} "
              f"banner={banner} end={extraction.get('end_score', 0):.3f} "
              f"{elapsed:.1f}ms")

    print("\ncropped-strip path (full_size supplied)")
    for key, (relative, expected) in CASES.items():
        image = read_image(relative)
        full_h, full_w = image.shape[:2]
        strip_h = round(full_h * 240 / 1080)
        strip = image[:strip_h]
        detector.analyze(strip, (full_w, full_h))
        actual = detector.last_interface
        status = "OK" if actual == expected else "FAIL"
        if actual != expected:
            failures.append((key + "-strip", expected, actual))
        print(f"{status:4s} {key:7s} expect={expected:1s} got={actual:1s}")

    print("\noverexposed tab-strip synthetic path")
    for key, (relative, expected) in OVER_SLICES.items():
        image = read_image(relative)
        height, width = image.shape[:2]
        scaled = cv2.resize(
            image, (2560, round(height * 2560 / width)),
            interpolation=cv2.INTER_AREA,
        )
        frame = np.zeros((1600, 2560, 3), dtype=np.uint8)
        end_y = min(frame.shape[0], 7 + scaled.shape[0])
        frame[7:end_y] = scaled[:end_y - 7]
        detector.analyze(frame)
        actual = detector.last_interface
        status = "OK" if actual == expected else "FAIL"
        if actual != expected:
            failures.append((key, expected, actual))
        print(f"{status:4s} {key:7s} expect={expected:1s} got={actual:1s}")

    print("\nM page simulated 2560x1440 path")
    m_image = read_image(IMAGES["M1"])[:1440]
    detector.analyze(m_image)
    m_score = (detector.last_extraction or {}).get("end_score", 0)
    status = "OK" if detector.last_interface == "M" else "FAIL"
    if detector.last_interface != "M":
        failures.append(("M1-169", "M", detector.last_interface))
    print(f"{status:4s} M1-169 expect=M got={detector.last_interface} "
          f"end={m_score:.3f}")

    print("\nblackout synthetic path")
    black = np.zeros((1600, 2560, 3), dtype=np.uint8)
    detector.analyze(black)
    status = "OK" if detector.last_interface == "Z" else "FAIL"
    if detector.last_interface != "Z":
        failures.append(("blackout-synthetic", "Z", detector.last_interface))
    print(f"{status:4s} blackout expect=Z got={detector.last_interface}")

    print("\nfound-banner blacklist path")
    positive_top = detector.normalize_top(read_image(IMAGES["N1"]))
    positive = detector.extraction_features(positive_top)
    print(f"positive banner={positive.get('banner')} "
          f"title={positive.get('title_score', 0):.3f} "
          f"found={positive.get('found_score', 0):.3f}")
    if not positive.get("banner"):
        failures.append(("stay-banner", True, False))
    found_image = cv2.imdecode(
        np.fromfile(str(FOUND_BANNER), dtype=np.uint8), cv2.IMREAD_COLOR
    )
    found_h, found_w = found_image.shape[:2]
    for target in (380, 430, 500):
        synthetic = positive_top.copy()
        scaled = cv2.resize(
            found_image,
            (target, round(found_h * target / found_w)),
            interpolation=cv2.INTER_AREA,
        )
        sh, sw = scaled.shape[:2]
        synthetic[10:10 + sh, 1250:1250 + sw] = scaled
        details = detector.extraction_features(synthetic)
        rejected = not details.get("banner") and details.get("found_score", 0) >= .75
        status = "OK" if rejected else "FAIL"
        if not rejected:
            failures.append((f"found-{target}", False, True))
        print(f"{status:4s} found width={target} banner={details.get('banner')} "
              f"title={details.get('title_score', 0):.3f} "
              f"found={details.get('found_score', 0):.3f}")

    print(f"\nframes={len(timings)} average={sum(timings)/len(timings):.1f}ms "
          f"max={max(timings):.1f}ms")
    if failures:
        print("FAILURES", failures)
        return 1
    print(f"ALL {len(CASES)} SCREENSHOTS + {len(OVER_SLICES)} OVEREXPOSED "
          f"STRIPS RECOGNIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

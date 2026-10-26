"""Build detector templates from the source UI screenshots only.

All crops are taken from ``ui识别`` after applying the same 1920x240 top-strip
normalization the detector uses at runtime.  No legacy detector image is read.
"""
from __future__ import annotations

import json
import os
import sys
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
SRC = BASE / "ui识别"
OUT = BASE / "assets" / "interface"

# Source screenshots.  Folder letters follow the user's UI-identification set;
# the detector keys follow the application's established interface codes.
SOURCES = {
    "hud_1": SRC / "画面识别 A 入场界面,战斗HUD/测试图2560 1600 16：10/战斗HUD画面1.png",
    "hud_2": SRC / "画面识别 A 入场界面,战斗HUD/测试图2560 1600 16：10/战斗HUD画面2.png",
    "hud_169": SRC / "画面识别 A 入场界面,战斗HUD/测试图2560 1440 16：9"
               / "2026-10-25[15-04]_69.02, 2.00, -68.86_0.04727, 0.04666, "
                 "-0.00221, 0.99779_15.47 (0).png",
    "extract": SRC / "画面识别 B 撤离点,战斗HUD/测试图/撤离点测试图.png",
    "end_m": SRC / "画面识别 M 撤离结束/测试图/测试图1.png",
    "pause": SRC / "画面识别 C 二级菜单,游戏主页面/测试图/测试画面.png",
    "inventory": SRC / "画面识别 D 二级菜单,背包界面/测试图/测试画面1.png",
    "overview": SRC / "画面识别 E 二级菜单,总览/测试图/测试图1.png",
    "health": SRC / "画面识别 F 二级菜单,健康/测试图/测试图.png",
    "skills": SRC / "画面识别 G 二级菜单,成就/测试图/测试图.png",
    "map": SRC / "测试画面 H 二级菜单,地图/测试图/测试图.png",
    "quests": SRC / "画面识别 I 二级菜单,任务/测试图/测试图.png",
    "achievements": SRC / "画面识别 J 二级菜单,成就/测试图/联想截图_20261022143802.png",
    "console": SRC / "画面识别 K 二级菜单,控制台/测试图/测试图.png",
    "settings": SRC / "画面识别 L 三级菜单,设置/测试图/测试图1.png",
}

# (template name, source key, crop box, match box, margin, kind)
# Crop box is the exact template area in the normalized 1920x240 strip.
# Match box is the expected location used by the detector's local search.
# Template suffixes follow the ui识别 folder letters exactly.
TEMPLATES = [
    ("hud_hotbar", "hud_2", (565, 0, 1490, 32), (565, 0, 1490, 32), 8, "gray"),
    ("hud_body", "hud_1", (0, 0, 115, 240), (0, 0, 120, 240), 0, "edges"),
    # 16:9 renders the health silhouette smaller and further left than the
    # 16:10 source, so both aspect ratios need their own edge template.
    ("hud_body_169", "hud_169", (0, 0, 120, 240), (0, 0, 120, 240), 0, "edges"),
    ("extract_B", "extract", (1345, 3, 1700, 38), (1340, 0, 1705, 43), 6, "gray"),
    # "战局结束 / 提前撤离" title on the post-raid summary page.  The page is
    # otherwise black, so end_M must be matched before the blackout fallback.
    ("end_M", "end_m", (865, 0, 1061, 84), (820, 0, 1110, 120), 12, "gray"),
    ("console_K", "console", (0, 0, 270, 32), (0, 0, 275, 36), 5, "gray"),
    ("pause_C", "pause", (450, 90, 1430, 240), (0, 0, 1920, 240), 0, "gray"),
    ("menu_return", "health", (1755, 0, 1840, 45), (1750, 0, 1845, 50), 6, "gray"),
    ("settings_L", "settings", (720, 8, 1010, 58), (710, 0, 1020, 68), 10, "gray"),
    ("tabs_D", "inventory", (128, 5, 253, 45), (128, 5, 253, 45), 6, "gray"),
    ("tabs_E", "overview", (0, 5, 120, 45), (0, 5, 120, 45), 6, "gray"),
    ("tabs_F", "health", (250, 5, 375, 45), (250, 5, 375, 45), 6, "gray"),
    ("tabs_G", "skills", (372, 5, 497, 45), (372, 5, 497, 45), 6, "gray"),
    ("tabs_H", "map", (494, 5, 619, 45), (494, 5, 619, 45), 6, "gray"),
    ("tabs_I", "quests", (616, 5, 741, 45), (616, 5, 741, 45), 6, "gray"),
    ("tabs_J", "achievements", (738, 5, 863, 45), (738, 5, 863, 45), 6, "gray"),
]

# Templates supplied as an already-cropped banner instead of a full screenshot.
# The user's "找到撤离点" sample is a 572x72 banner crop, so it must not run
# through normalize().  The detector matches it at several widths because the
# source capture scale is unknown.
DIRECT_TEMPLATES = [
    (
        "extract_found",
        SRC / "画面识别 B 撤离点,战斗HUD/找到撤离点_黑名单(不参与识别).png",
        (1200, 0, 1820, 110),
        0,
        "gray",
    ),
]

# A 16:9 / 16:10 game area is normalized by the detector before matching.
TOP_SIZE = (1920, 240)


def normalize(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"cannot read {path}")
    height, width = image.shape[:2]
    strip_h = round(height * 240 / 1080)
    return cv2.resize(image[:strip_h], TOP_SIZE)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cache = {}
    metadata = {"version": 1, "top_size": list(TOP_SIZE), "templates": {}}
    for name, source_key, crop_box, match_box, margin, kind in TEMPLATES:
        if source_key not in cache:
            cache[source_key] = normalize(SOURCES[source_key])
        top = cache[source_key]
        x1, y1, x2, y2 = crop_box
        crop = top[y1:y2, x1:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        if kind == "edges":
            # Isolate the bright HUD silhouette from the dark source background,
            # then keep its outline.  Matching at runtime uses distance support,
            # so extra scene edges do not hurt.
            mask = (gray > 65).astype(np.uint8) * 255
            template = cv2.Canny(mask, 50, 150)
        else:
            template = gray
        path = OUT / f"{name}.png"
        ok, encoded = cv2.imencode(".png", template)
        if not ok:
            raise RuntimeError(f"cannot encode {name}")
        path.write_bytes(encoded.tobytes())
        metadata["templates"][name] = {
            "file": path.name,
            "source": str(SOURCES[source_key].relative_to(BASE)),
            "crop": list(crop_box),
            "box": list(match_box),
            "margin": margin,
            "kind": kind,
            "width": int(template.shape[1]),
            "height": int(template.shape[0]),
            "bytes": path.stat().st_size,
        }
        print(f"{name:14s} {template.shape[1]:4d}x{template.shape[0]:<3d} "
              f"{path.stat().st_size:6d} B  {SOURCES[source_key].name}")
    for name, source, match_box, margin, kind in DIRECT_TEMPLATES:
        image = cv2.imdecode(
            np.fromfile(str(source), dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if image is None:
            raise RuntimeError(f"cannot read {source}")
        template = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        path = OUT / f"{name}.png"
        ok, encoded = cv2.imencode(".png", template)
        if not ok:
            raise RuntimeError(f"cannot encode {name}")
        path.write_bytes(encoded.tobytes())
        metadata["templates"][name] = {
            "file": path.name,
            "source": str(source.relative_to(BASE)),
            "crop": [0, 0, int(template.shape[1]), int(template.shape[0])],
            "box": list(match_box),
            "margin": margin,
            "kind": kind,
            "width": int(template.shape[1]),
            "height": int(template.shape[0]),
            "bytes": path.stat().st_size,
        }
        print(f"{name:14s} {template.shape[1]:4d}x{template.shape[0]:<3d} "
              f"{path.stat().st_size:6d} B  {source.name}")
    (OUT / "templates.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    total = sum(item["bytes"] for item in metadata["templates"].values())
    print(f"templates={len(metadata['templates'])} total_bytes={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

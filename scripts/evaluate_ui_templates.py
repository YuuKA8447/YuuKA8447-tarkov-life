"""Score every generated template against every source UI screenshot."""
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
UI_ROOT = BASE / "ui识别"
ASSETS = BASE / "assets" / "interface"

IMAGES = {
    "A1": "画面识别 A 入场界面,战斗HUD/测试图2560 1600 16：10/战斗HUD画面1.png",
    "A2": "画面识别 A 入场界面,战斗HUD/测试图2560 1600 16：10/战斗HUD画面2.png",
    "A3": "画面识别 A 入场界面,战斗HUD/测试图2560 1600 16：10/战斗HUD画面3.png",
    "A4": "画面识别 A 入场界面,战斗HUD/测试图2560 1600 16：10/战斗HUD画面4.png",
    "N1": "画面识别 B 撤离点,战斗HUD/测试图/撤离点测试图.png",
    "N2": "画面识别 B 撤离点,战斗HUD/测试图/撤离点测试图2.png",
    "N3": "画面识别 B 撤离点,战斗HUD/测试图/测试图3.png",
    "N4": "画面识别 B 撤离点,战斗HUD/测试图/测试图4.png",
    "Q": "画面识别 C 二级菜单,游戏主页面/测试图/测试画面.png",
    "B1": "画面识别 D 二级菜单,背包界面/测试图/测试画面1.png",
    "B2": "画面识别 D 二级菜单,背包界面/测试图/测试画面2.png",
    "C": "画面识别 E 二级菜单,总览/测试图/测试图1.png",
    "D": "画面识别 F 二级菜单,健康/测试图/测试图.png",
    "E": "画面识别 G 二级菜单,成就/测试图/测试图.png",
    "H": "测试画面 H 二级菜单,地图/测试图/测试图.png",
    "G": "画面识别 I 二级菜单,任务/测试图/测试图.png",
    "O": "画面识别 J 二级菜单,成就/测试图/联想截图_20261022143802.png",
    "P": "画面识别 K 二级菜单,控制台/测试图/测试图.png",
    "L1": "画面识别 L 三级菜单,设置/测试图/测试图1.png",
    "L2": "画面识别 L 三级菜单,设置/测试图/测试图2.png",
    "L3": "画面识别 L 三级菜单,设置/测试图/测试图3.png",
    "L4": "画面识别 L 三级菜单,设置/测试图/测试图4.png",
    "L5": "画面识别 L 三级菜单,设置/测试图/测试图5.png",
    "M1": "画面识别 M 撤离结束/测试图/测试图1.png",
    "Z1": "画面识别 M 撤离结束/测试图/测试图2.png",
}

EXPECTED = {
    "A1": "A", "A2": "A", "A3": "A", "A4": "A",
    "N1": "B", "N2": "B", "N3": "B", "N4": "B",
    "Q": "C",
    "B1": "D", "B2": "D",
    "C": "E", "D": "F", "E": "G", "H": "H", "G": "I", "O": "J", "P": "K",
    "L1": "L", "L2": "L", "L3": "L", "L4": "L", "L5": "L",
    "M1": "M", "Z1": "Z",
}

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
        IMAGES[key] = str(path.relative_to(UI_ROOT))
        EXPECTED[key] = code

TOP = (1920, 240)


def normalize(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    height = image.shape[0]
    strip_h = round(height * 240 / 1080)
    return cv2.resize(image[:strip_h], TOP)


def local_score(gray: np.ndarray, template: np.ndarray, box, margin: int) -> float:
    x1, y1, x2, y2 = box
    region = gray[max(0, y1 - margin):min(gray.shape[0], y2 + margin),
                  max(0, x1 - margin):x2 + margin]
    if region.shape[0] < template.shape[0] or region.shape[1] < template.shape[1]:
        return 0.0
    return max(0.0, float(cv2.minMaxLoc(
        cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED))[1]))


def edge_score(gray: np.ndarray, reference: np.ndarray, box, margin: int) -> float:
    x1, y1, x2, y2 = box
    region = gray[max(0, y1 - margin):min(gray.shape[0], y2 + margin),
                  max(0, x1 - margin):x2 + margin]
    if region.shape[0] < reference.shape[0] or region.shape[1] < reference.shape[1]:
        return 0.0
    edges = cv2.Canny(region, 35, 90)
    if not np.any(edges):
        return 0.0
    distance = cv2.distanceTransform(255 - edges, cv2.DIST_L2, 3)
    distance = distance[:reference.shape[0], :reference.shape[1]]
    values = distance[reference > 0]
    return float(np.mean(np.maximum(0, 1 - values / 2.2))) if len(values) else 0.0


def found_score(gray: np.ndarray, template: np.ndarray, box) -> float:
    x1, y1, x2, y2 = box
    region = gray[y1:y2, x1:x2]
    height, width = template.shape[:2]
    best = 0.0
    for target in range(240, 561, 20):
        scaled_h = max(8, round(height * target / width))
        if region.shape[0] < scaled_h or region.shape[1] < target:
            continue
        scaled = cv2.resize(template, (target, scaled_h),
                            interpolation=cv2.INTER_AREA)
        best = max(best, float(cv2.minMaxLoc(
            cv2.matchTemplate(region, scaled, cv2.TM_CCOEFF_NORMED))[1]))
    return best


def home_score(gray: np.ndarray, template: np.ndarray) -> float:
    base = cv2.resize(template, (max(1, template.shape[1] // 2),
                                 max(1, template.shape[0] // 2)),
                      interpolation=cv2.INTER_AREA)
    variants = [cv2.resize(base, (max(1, int(base.shape[1] * scale)),
                                   max(1, int(base.shape[0] * scale * aspect))),
                           interpolation=cv2.INTER_AREA)
                for aspect in (1.0, 1.2)
                for scale in (0.8, 0.9, 1.0, 1.1, 1.2)]
    small = cv2.resize(gray, (960, 120), interpolation=cv2.INTER_AREA)
    best = 0.0
    for variant in variants:
        if variant.shape[0] > small.shape[0] or variant.shape[1] > small.shape[1]:
            continue
        best = max(best, float(cv2.minMaxLoc(
            cv2.matchTemplate(small, variant, cv2.TM_CCOEFF_NORMED))[1]))
    return best


def main() -> int:
    metadata = json.loads((ASSETS / "templates.json").read_text(encoding="utf-8"))
    templates = {}
    for name, item in metadata["templates"].items():
        templates[name] = cv2.imdecode(
            np.fromfile(str(ASSETS / item["file"]), dtype=np.uint8),
            cv2.IMREAD_GRAYSCALE,
        )

    rows = {}
    for key, relative in IMAGES.items():
        top = normalize(UI_ROOT / relative)
        gray = cv2.cvtColor(top, cv2.COLOR_BGR2GRAY)
        scores = {}
        for name, item in metadata["templates"].items():
            template = templates[name]
            if name == "pause_C":
                score = home_score(gray, template)
            elif name == "extract_found":
                score = found_score(gray, template, item["box"])
            elif item["kind"] == "edges":
                score = edge_score(gray, template, item["box"], item["margin"])
            else:
                score = local_score(gray, template, item["box"], item["margin"])
            scores[name] = score
        rows[key] = scores
        ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:4]
        print(f"{key:2s} expect={EXPECTED[key]:1s} " +
              " ".join(f"{name}={value:.3f}" for name, value in ranked))

    names = list(metadata["templates"])
    print("\nmatrix (rows=images, columns=templates)")
    print("     " + " ".join(f"{name[:9]:>9s}" for name in names))
    for key, scores in rows.items():
        print(f"{key:2s}   " + " ".join(f"{scores[name]:9.3f}" for name in names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

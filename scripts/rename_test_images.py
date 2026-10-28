"""Rename ui识别 test screenshots by current detector verdict + score.

Naming rule: {verdict_letter}{increment}_{score}.png
  - verdict_letter: Detector.analyze() result for the full frame
  - increment: 1-based, global per verdict letter across all 测试图* folders
  - score: the score that drove the verdict (3 decimals)

Modes:
  (default)      dry-run over every test image
  --apply        one-time normalizer: rename every test image, rewrite mapping
  --incremental  keep already-compliant names, rename only new files, append mapping
"""
from __future__ import annotations

import csv
import datetime
import marshal
import os
import re
import sys
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
NAME_RE = re.compile(r"^([A-Z0-9])(\d+)_([0-9]+\.[0-9]{3})\.png$")


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


def read_image(path: Path):
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


def score_basis(detector, verdict: str) -> tuple[float, str]:
    menu = detector.last_menu_features or {}
    extraction = detector.last_extraction or {}
    if verdict == "B":
        return float(extraction.get("title_score", 0)), "title_score"
    if verdict == "M":
        return float(extraction.get("end_score", 0)), "end_score"
    if verdict == "Z":
        return 1.0, "blackout_luma"
    if verdict in ("D", "E", "F", "G", "H", "I", "J"):
        if "tab_brightness" in menu:
            return float(menu.get("tab_brightness", 0)) / 255.0, "tab_brightness/255"
        return float(menu.get("interface_score", 0)), "tab_score"
    if verdict == "C":
        return float(menu.get("home_score", menu.get("interface_score", 0))), "home_score"
    if verdict == "K":
        return float(menu.get("console", menu.get("interface_score", 0))), "console_score"
    if verdict == "L":
        return float(menu.get("settings", menu.get("interface_score", 0))), "settings_score"
    if verdict == "U":
        return float(menu.get("menu_return", menu.get("interface_score", 0))), "menu_return"
    if verdict == "A":
        return float(menu.get("combat", menu.get("interface_score", 0))), "combat_score"
    return float(menu.get("interface_score", 0)), "interface_score"


def collect_test_images() -> list[Path]:
    images: list[Path] = []
    for directory in sorted(UI_ROOT.rglob("测试图*")):
        if not directory.is_dir():
            continue
        images.extend(
            path for path in sorted(directory.iterdir())
            if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg")
        )
    return images


def analyze_row(detector, path: Path) -> dict:
    image = read_image(path)
    if image is None:
        raise SystemExit(f"cannot read image: {path}")
    detector.analyze(image)
    verdict = detector.last_interface
    score, score_type = score_basis(detector, verdict)
    menu = detector.last_menu_features or {}
    extraction = detector.last_extraction or {}
    features = detector.last_features or {}
    return {
        "path": path,
        "folder": str(path.parent.relative_to(UI_ROOT)),
        "old_name": path.name,
        "verdict": verdict,
        "score": score,
        "score_type": score_type,
        "complement": {
            "combat_score": features.get("combat_score", 0),
            "body_shape": features.get("body_shape", 0),
            "hotbar": features.get("hotbar", 0),
            "title_score": extraction.get("title_score", 0),
            "end_score": extraction.get("end_score", 0),
            "tab_match": menu.get("tab_match", ""),
        },
    }


def main() -> int:
    apply = "--apply" in sys.argv
    incremental = "--incremental" in sys.argv
    namespace = load_detector_module()
    Detector = namespace["Detector"]
    detector = Detector()

    rows = []
    counters: dict[str, int] = {}
    for path in collect_test_images():
        match = NAME_RE.match(path.name) if incremental else None
        if match:
            verdict, number, score_text = match.groups()
            counters[verdict] = max(counters.get(verdict, 0), int(number))
            rows.append({
                "path": path,
                "folder": str(path.parent.relative_to(UI_ROOT)),
                "old_name": path.name,
                "verdict": verdict,
                "score": float(score_text),
                "score_type": "existing",
                "complement": {},
                "new_name": path.name,
                "target": path,
                "keep": True,
            })
            continue
        row = analyze_row(detector, path)
        row["keep"] = False
        rows.append(row)

    for row in sorted(rows, key=lambda r: (str(r["path"].parent), r["old_name"])):
        if row["keep"]:
            continue
        verdict = row["verdict"]
        counters[verdict] = counters.get(verdict, 0) + 1
        new_name = f"{verdict}{counters[verdict]}_{row['score']:.3f}.png"
        row["new_name"] = new_name
        row["target"] = row["path"].with_name(new_name)

    collisions = [
        row for row in rows
        if not row["keep"] and row["target"].exists() and row["target"] != row["path"]
    ]
    if collisions:
        for row in collisions:
            print(f"COLLISION {row['target']}")
        return 1

    new_rows = [row for row in rows if not row["keep"]]
    kept_rows = [row for row in rows if row["keep"]]
    print(f"images={len(rows)} keep={len(kept_rows)} rename={len(new_rows)}")
    for row in rows:
        if row["keep"]:
            continue
        print(
            f"{row['verdict']} {row['score']:.3f} {row['score_type']:18s} "
            f"{row['folder']}\\{row['old_name']}  ->  {row['new_name']}"
        )

    if not apply:
        print("dry-run only; pass --apply (full) or --incremental --apply (new files only)")
        return 0

    if incremental:
        mapping = UI_ROOT / f"测试图命名对照_{datetime.date.today():%Y%m%d}.csv"
        exists = mapping.exists()
    else:
        mapping = UI_ROOT / "测试图命名对照_20261028.csv"
        exists = False

    with mapping.open("a" if exists else "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        if not exists:
            writer.writerow([
                "序号", "判定字母", "得分", "得分依据", "原文件名", "新文件名",
                "所在目录", "combat_score", "body_shape", "hotbar",
                "title_score", "end_score", "tab_match",
            ])
        for index, row in enumerate(new_rows, 1):
            complement = row["complement"]
            writer.writerow([
                index, row["verdict"], f"{row['score']:.3f}", row["score_type"],
                row["old_name"], row["new_name"], row["folder"],
                f"{complement.get('combat_score', 0):.3f}",
                f"{complement.get('body_shape', 0):.3f}",
                f"{complement.get('hotbar', 0):.3f}",
                f"{complement.get('title_score', 0):.3f}",
                f"{complement.get('end_score', 0):.3f}",
                complement.get("tab_match", ""),
            ])

    for row in new_rows:
        row["path"].rename(row["target"])
    print(f"renamed {len(new_rows)} files; mapping -> {mapping}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

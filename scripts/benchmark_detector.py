"""Benchmark the compiled detector against the project screenshot set.

Usage:
    tools/py311/python.exe scripts/benchmark_detector.py \
        --module detector.marshal --images 项目测试图 \
        --rounds 3 --json build/bench_baseline.json

The module is loaded from marshal with a synthetic __file__ so its
`Path(__file__).parent / "assets"` lookup resolves to the project assets.
"""
from __future__ import annotations

import argparse
import json
import marshal
import os
import statistics
import struct
import sys
import tempfile
import time
import types
import zlib
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
COOKIE = b"MEI\x0c\x0b\x0a\x0b\x0e"
DEFAULT_EXE = BASE / "build" / "从零开始的塔科夫生活_V1.0.0.1.exe"
CV2_FALLBACKS = (
    Path.home() / "AppData" / "Local" / "Temp" / "tarkov_v129_cv2" / "site",
    BASE / "build" / "_offline_deps",
)


def parse_archive(exe_path: Path):
    buf = exe_path.read_bytes()
    cp = buf.rfind(COOKIE)
    if cp < 0:
        raise RuntimeError(f"PyInstaller cookie not found in {exe_path}")
    magic, pkg_len, toc_off, toc_len, pyver, pylib = struct.unpack(
        "!8sIIii64s", buf[cp:cp + 88]
    )
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
        nm = name.decode("utf-8", "replace").rstrip("\0")
        entries[nm] = {
            "pos": epos, "cmprsd": cmprsd, "flag": flag, "type": typ
        }
        pos += es
    return buf, overlay, entries


def extract_pyz_code(exe_path: Path, module_name: str):
    buf, overlay, entries = parse_archive(exe_path)
    e = entries["PYZ.pyz"]
    pyz = buf[overlay + e["pos"]:overlay + e["pos"] + e["cmprsd"]]
    pyz_toc_pos = struct.unpack(">i", pyz[8:12])[0]
    pyz_toc = dict(marshal.loads(pyz[pyz_toc_pos:]))
    is_pkg, mpos, mlen = pyz_toc[module_name]
    return marshal.loads(zlib.decompress(pyz[mpos:mpos + mlen]))


def ensure_timer_digits(exe_path: Path):
    if "timer_digits" in sys.modules:
        return
    cached = BASE / "build" / "_offline_deps" / "timer_digits.marshal"
    if cached.is_file():
        code = marshal.loads(cached.read_bytes())
    else:
        code = extract_pyz_code(exe_path, "timer_digits")
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(marshal.dumps(code))
    module = types.ModuleType("timer_digits")
    module.__file__ = str(cached)
    sys.modules["timer_digits"] = module
    exec(code, module.__dict__)


REQUIRED_ASSET_FILES = (
    "health.png", "bar.png", "bar_horizontal.png", "bar_vertical.png",
    "label_shape.png", "body_shape.npz", "timer_digits.npz",
    "extract_title.png", "extract_zero.png", "confirm_subtitle.png",
    "confirm_title.png", "menu_return.png", "menu_tabs.png",
    "pause_logo_left.png", "pause_logo_right.png",
    "settings_return.png", "settings_title.png",
)


def ensure_assets(exe_path: Path):
    # cv2.imread on Windows cannot read non-ASCII paths. The project path
    # contains Chinese characters, so the offline detector runs from an
    # ASCII temp directory instead.
    #
    # Detector builds since V1.3.2.x embed all 21 page templates, so the
    # EXE no longer carries assets/interface.  Return the project assets
    # directly when the archive has none; only older EXEs need extraction.
    out = Path(tempfile.gettempdir()) / "tarkov_bench_assets" / "assets"
    if all((out / name).is_file() for name in REQUIRED_ASSET_FILES):
        return out
    buf, overlay, entries = parse_archive(exe_path)
    embedded = [name for name in entries if name.startswith("assets\\")]
    if not any(name.endswith(name_.replace("/", "\\"))
               for name in embedded for name_ in REQUIRED_ASSET_FILES):
        return BASE / "assets"
    for name, e in entries.items():
        if not name.startswith("assets\\"):
            continue
        raw = buf[overlay + e["pos"]:overlay + e["pos"] + e["cmprsd"]]
        if e["flag"] == 1:
            raw = zlib.decompress(raw)
        rel = name.split("\\", 1)[1]
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    missing = [name for name in REQUIRED_ASSET_FILES if not (out / name).is_file()]
    if missing:
        raise RuntimeError(f"missing detector assets after extraction: {missing}")
    return out


def load_detector(module_path: Path, assets_root: Path):
    namespace = {
        "__file__": str(assets_root.parent / "detector.py"),
        "__name__": "detector",
    }
    code = marshal.loads(module_path.read_bytes())
    exec(code, namespace)
    return namespace


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", default="detector.marshal")
    parser.add_argument("--images", default="项目测试图")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--json", default="")
    parser.add_argument("--exe", default=str(DEFAULT_EXE))
    args = parser.parse_args()

    try:
        import cv2
        import numpy as np
    except ImportError:
        env_site = os.environ.get("TARKOV_CV2_SITE")
        candidates = ([Path(env_site)] if env_site else []) + list(CV2_FALLBACKS)
        for fallback in candidates:
            if fallback and fallback.is_dir():
                sys.path.insert(0, str(fallback))
                break
        import cv2
        import numpy as np
    ensure_timer_digits(Path(args.exe))
    assets_root = ensure_assets(Path(args.exe))

    module_path = (BASE / args.module).resolve()
    image_dir = (BASE / args.images).resolve()
    images = sorted(image_dir.glob("*.png"))
    if not images:
        raise SystemExit(f"no PNG images in {image_dir}")

    namespace = load_detector(module_path, assets_root)
    Detector = namespace["Detector"]
    detector = Detector()

    frames = []
    for path in images:
        data = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            raise SystemExit(f"cannot read {path}")
        frames.append((path.name, image))

    # Warm up caches and OpenCV code paths.
    for _, image in frames:
        h, w = image.shape[:2]
        detector.analyze(image, full_size=(w, h))

    per_image = {name: [] for name, _ in frames}
    results = {}
    for round_index in range(args.rounds):
        for name, image in frames:
            h, w = image.shape[:2]
            detector.last_extraction_seen = None
            start = time.perf_counter()
            detector.analyze(image, full_size=(w, h))
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            per_image[name].append(elapsed_ms)
            results[name] = {
                "interface": detector.last_interface,
                "menu": jsonable(detector.last_menu_features),
                "extraction": jsonable(detector.last_extraction),
            }

    rows = []
    total_median = 0.0
    for name, samples in per_image.items():
        median_ms = statistics.median(samples)
        total_median += median_ms
        rows.append(
            {
                "image": name,
                "median_ms": round(median_ms, 3),
                "min_ms": round(min(samples), 3),
                "max_ms": round(max(samples), 3),
                "interface": results[name]["interface"],
            }
        )

    rows.sort(key=lambda row: row["median_ms"], reverse=True)
    print(f"module={module_path.name} images={len(images)} rounds={args.rounds}")
    print(f"total_median_ms={total_median:.3f} avg_median_ms={total_median/len(rows):.3f}")
    for row in rows:
        print(
            f"{row['median_ms']:9.3f} ms  {row['interface']:>2s}  {row['image']}"
        )

    payload = {
        "module": str(module_path),
        "module_size": module_path.stat().st_size,
        "image_dir": str(image_dir),
        "rounds": args.rounds,
        "total_median_ms": round(total_median, 3),
        "average_median_ms": round(total_median / len(rows), 3),
        "rows": rows,
        "results": results,
    }
    if args.json:
        out = (BASE / args.json).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("written", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

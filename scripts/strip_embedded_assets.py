"""Remove unused fonts, legacy media, retired sounds and old UI templates.

The bootloader reads entries through the outer CArchive TOC, so deleting data
requires rebuilding the overlay and updating every entry offset. This script
keeps the original compressed bytes for all retained entries and writes a new
archive with no slot padding or dead files.
"""
from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "build" / "_V1.4.1.0_full.exe"
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "build" / "从零开始的塔科夫生活_V1.4.1.0.exe"
COOKIE = b"MEI\x0c\x0b\x0a\x0b\x0e"

UNUSED_ROOT_ASSETS = {
    "assets\\bin.png",
    "assets\\emilia.ico",
    "assets\\emilia.png",
    "assets\\emilia_head.png",
    "assets\\mascot.png",
    "assets\\mascot_ui.png",
    "assets\\return_by_death.ico",
    "assets\\subaru_clean.png",
}

DEPRECATED_AUDIO = {
    "assets\\rewind.wav",
    "assets\\quest_completed.wav",
}

# Runtime imports neither Pillow nor cv2 video I/O; numpy loads its own
# OpenBLAS from numpy.libs, so the duplicate copy at the archive root is dead.
DEPRECATED_PACKAGES = {
    "cv2\\opencv_videoio_ffmpeg500_64.dll",
    "libscipy_openblas64_-63c857e738469261263c764a36be9436.dll",
}

# The legacy detector read these files from assets/interface at runtime.  The
# new detector embeds the fourteen ui识别 templates in detector.marshal instead,
# so every one of these CArchive entries is now dead weight.
RETIRED_RECOGNITION_ASSETS = {
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

REQUIRED_ASSETS = {
    "assets\\subaru_clean.ico",
    "assets\\enabled.wav",
    "assets\\disabled.wav",
    "assets\\return_by_death.wav",
    "assets\\return_by_death.mp3",
    "assets\\killer_queen.wav",
    "assets\\duckov_extract.wav",
}


def parse_archive(buf: bytes):
    cp = buf.rfind(COOKIE)
    if cp < 0:
        raise RuntimeError("找不到 CArchive cookie")
    magic, pkg_len, toc_off, toc_len, pyver, pylib = struct.unpack(
        "!8sIIii64s", buf[cp:cp + 88]
    )
    tail = len(buf) - cp - 88
    overlay = len(buf) - (pkg_len + tail)
    toc = bytes(buf[overlay + toc_off:overlay + toc_off + toc_len])
    entries = []
    order = []
    pos = 0
    while pos < len(toc):
        es, = struct.unpack("!i", toc[pos:pos + 4])
        epos, cmprsd, uncmprsd, flag, typ, name = struct.unpack(
            "!IIIBc" + str(es - 18) + "s", toc[pos + 4:pos + es]
        )
        nm = name.decode("utf-8", "replace").rstrip("\0")
        record = bytes(toc[pos:pos + es])
        entries.append(
            {
                "name": nm,
                "pos": epos,
                "cmprsd": cmprsd,
                "uncmprsd": uncmprsd,
                "flag": flag,
                "type": typ,
                "record": record,
                "es": es,
            }
        )
        order.append(nm)
        pos += es
    if pos != toc_len:
        raise RuntimeError("CArchive TOC 长度不一致")
    header = (magic, pkg_len, toc_off, toc_len, pyver, pylib)
    return overlay, entries, order, header, tail


def main() -> int:
    if not SRC.is_file():
        raise RuntimeError(f"缺少源 EXE: {SRC}")
    if DST == SRC:
        raise RuntimeError("输出不能与源 EXE 相同")
    buf = SRC.read_bytes()
    overlay, entries, order, header, tail = parse_archive(buf)
    by_name = {entry["name"]: entry for entry in entries}
    if len(by_name) != len(entries):
        raise RuntimeError("CArchive 存在重名条目")
    if order[-1] != "PYZ.pyz":
        raise RuntimeError("PYZ.pyz 不是最后一个数据条目")

    remove = (set(UNUSED_ROOT_ASSETS) | set(DEPRECATED_AUDIO)
              | set(DEPRECATED_PACKAGES)
              | set(RETIRED_RECOGNITION_ASSETS))
    remove |= {
        name for name in order
        if name.startswith("assets\\fonts\\")
    }
    remove |= {
        name for name in order
        if name.startswith("assets\\ui_v2\\")
    }
    remove |= {
        name for name in order
        if name.startswith("PIL\\")
    }
    # The original PyInstaller base ships all 78 retired entries; the V1.3.2.2
    # rebuilt base has already dropped them, so a match count of 0 is the
    # steady state. Only a half-trimmed base is a real mismatch.
    present = remove & set(by_name)
    missing = sorted(remove - set(by_name))
    if missing and present:
        raise RuntimeError(f"待删除条目部分缺失（基底不一致）: {missing}")
    if present and len(present) != 78:
        raise RuntimeError(f"待删除条目数量异常: {len(present)}，预期 78")
    if set(REQUIRED_ASSETS) - set(by_name):
        raise RuntimeError(
            f"源 EXE 缺少必需资源: {sorted(set(REQUIRED_ASSETS) - set(by_name))}"
        )
    if set(REQUIRED_ASSETS) & remove:
        raise RuntimeError("必需资源被列入删除列表")

    kept = [entry for entry in entries if entry["name"] not in remove]
    new_data = bytearray()
    new_toc = bytearray()
    new_pos = 0
    for entry in kept:
        old_start = overlay + entry["pos"]
        raw = buf[old_start:old_start + entry["cmprsd"]]
        if len(raw) != entry["cmprsd"]:
            raise RuntimeError(f"源数据被截断: {entry['name']}")
        start = len(new_data)
        new_data += raw
        if start != new_pos:
            raise RuntimeError("新数据区位置计算错误")
        new_pos += len(raw)
        record = bytearray(entry["record"])
        struct.pack_into("!I", record, 4, start)
        new_toc += record

    new_toc_off = len(new_data)
    new_toc_len = len(new_toc)
    new_pkg_len = new_toc_off + new_toc_len + 88
    magic, _, _, _, pyver, pylib = header
    cookie = struct.pack(
        "!8sIIii64s", magic, new_pkg_len, new_toc_off, new_toc_len, pyver, pylib
    )
    out = bytes(buf[:overlay]) + bytes(new_data) + bytes(new_toc) + cookie + bytes(buf[-tail:] if tail else b"")
    if len(out) != overlay + new_pkg_len:
        raise RuntimeError("输出文件长度与 CArchive 头不一致")
    DST.write_bytes(out)

    # Reopen the result and compare every retained raw slot with the source.
    out_buf = DST.read_bytes()
    out_overlay, out_entries, out_order, out_header, out_tail = parse_archive(out_buf)
    if out_overlay != overlay or out_tail != tail:
        raise RuntimeError("新 CArchive overlay/tail 变化")
    if len(out_entries) != len(kept):
        raise RuntimeError("新 CArchive 条目数量异常")
    if [entry["name"] for entry in out_entries] != [entry["name"] for entry in kept]:
        raise RuntimeError("新 CArchive 条目顺序异常")
    if set(remove) & set(out_order):
        raise RuntimeError("删除条目仍存在于输出")
    for old_entry, new_entry in zip(kept, out_entries):
        old_raw = buf[overlay + old_entry["pos"]:
                      overlay + old_entry["pos"] + old_entry["cmprsd"]]
        new_raw = out_buf[out_overlay + new_entry["pos"]:
                          out_overlay + new_entry["pos"] + new_entry["cmprsd"]]
        if old_raw != new_raw:
            raise RuntimeError(f"保留条目数据变化: {old_entry['name']}")
    pyz = next(entry for entry in out_entries if entry["name"] == "PYZ.pyz")
    pyz_raw = out_buf[out_overlay + pyz["pos"]:out_overlay + pyz["pos"] + pyz["cmprsd"]]
    if pyz_raw[:4] != b"PYZ\0":
        raise RuntimeError("输出 PYZ 文件头异常")
    if set(REQUIRED_ASSETS) - set(out_order):
        raise RuntimeError("输出缺少必需资源")

    removed_bytes = sum(by_name[name]["cmprsd"] for name in present)
    print(f"source={SRC}")
    print(f"output={DST}")
    print(f"entries {len(entries)} -> {len(out_entries)} (removed {len(present)})")
    print(f"removed_compressed_bytes={removed_bytes}")
    print(f"size {len(buf)} -> {len(out)} (saved {len(buf) - len(out)})")
    print(f"sha256={hashlib.sha256(out).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

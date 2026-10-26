"""Replace the CArchive `monitor` script entry with monitor.marshal.

The main monitor module is stored as a marshalled script entry in the outer
CArchive, not in PYZ.pyz.  The replacement is smaller than the original
compressed slot, so it is written in place and zero-padded; the TOC keeps the
same entry offsets and only its compressed/uncompressed sizes change.
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "build" / "base_v1100.exe"
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else SRC
PAYLOAD = Path(sys.argv[3]) if len(sys.argv) > 3 else BASE / "monitor.marshal"
COOKIE = b"MEI\x0c\x0b\x0a\x0b\x0e"
ENTRY = "monitor"

try:
    from zopfli.zlib import compress as deflate
except ImportError:
    deflate = lambda data: zlib.compress(data, 9)


def main() -> int:
    buf = bytearray(SRC.read_bytes())
    cp = buf.rfind(COOKIE)
    if cp < 0:
        raise SystemExit("CArchive cookie not found")
    magic, pkg_len, toc_off, toc_len, pyver, pylib = struct.unpack(
        "!8sIIii64s", buf[cp:cp + 88]
    )
    tail = len(buf) - cp - 88
    overlay = len(buf) - (pkg_len + tail)
    toc_start = overlay + toc_off
    toc = bytes(buf[toc_start:toc_start + toc_len])

    record_pos = None
    entry = None
    pos = 0
    while pos < len(toc):
        es, = struct.unpack("!i", toc[pos:pos + 4])
        epos, cmprsd, uncmprsd, flag, typ, name = struct.unpack(
            "!IIIBc" + str(es - 18) + "s", toc[pos + 4:pos + es]
        )
        nm = name.decode("utf-8", "replace").rstrip("\0")
        if nm == ENTRY:
            record_pos = pos
            entry = (epos, cmprsd, uncmprsd, flag, typ)
        pos += es
    if pos != toc_len or entry is None or record_pos is None:
        raise SystemExit(f"{ENTRY} script entry not found")

    epos, old_cmprsd, old_uncmprsd, flag, typ = entry
    if typ != b"s" or flag != 1:
        raise SystemExit(f"unexpected {ENTRY} entry: type={typ!r} flag={flag}")
    raw = bytes(buf[overlay + epos:overlay + epos + old_cmprsd])
    current = zlib.decompress(raw)
    payload = PAYLOAD.read_bytes()

    if current == payload:
        print(f"{ENTRY} entry already up to date ({len(payload)} bytes)")
        return 0

    compressed = deflate(payload)
    if len(compressed) > old_cmprsd:
        raise SystemExit(
            f"replacement does not fit: {len(compressed)} > {old_cmprsd} bytes"
        )
    slot = compressed + b"\0" * (old_cmprsd - len(compressed))
    start = overlay + epos
    buf[start:start + old_cmprsd] = slot
    struct.pack_into("!II", buf, toc_start + record_pos + 8,
                     len(compressed), len(payload))

    out = bytes(buf)
    check_cp = out.rfind(COOKIE)
    cmagic, cpkg, ctoc_off, ctoc_len, cpyver, cpylib = struct.unpack(
        "!8sIIii64s", out[check_cp:check_cp + 88]
    )
    ctail = len(out) - check_cp - 88
    coverlay = len(out) - (cpkg + ctail)
    check = zlib.decompress(
        out[coverlay + epos:coverlay + epos + len(compressed)]
    )
    if check != payload:
        raise SystemExit("monitor entry round-trip failed")

    DST.write_bytes(out)
    print(f"{ENTRY} entry patched: {old_cmprsd} -> {len(compressed)} bytes "
          f"compressed, {len(payload)} uncompressed, slot {old_cmprsd}")
    print("written", DST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Draw assets/icon.png (512x512, transparent): two flashcards on a teal tile. Pure Python, no dependencies."""

import struct
import zlib
from pathlib import Path

N, SS = 512, 3  # size, supersampling per axis


def rrect(x, y, x0, y0, x1, y1, r):
    """Inside a rounded rectangle?"""
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r and x0 <= x <= x1 and y0 <= y <= y1


TILE = (15, 118, 110)      # teal
BACK = (153, 246, 228)     # light teal card
FRONT = (255, 255, 255)
BAR = (148, 163, 184)      # slate text bars
ACCENT = (245, 158, 11)    # amber dot (audio)


def color_at(x, y):
    c = None
    if rrect(x, y, 16, 16, 496, 496, 104):
        c = TILE
    if rrect(x, y, 150, 96, 430, 336, 30):
        c = BACK
    if rrect(x, y, 82, 176, 362, 416, 30):
        c = FRONT
        if rrect(x, y, 122, 226, 322, 254, 14) or rrect(x, y, 122, 282, 282, 304, 11) or rrect(x, y, 122, 330, 252, 352, 11):
            c = BAR
        if (x - 318) ** 2 + (y - 368) ** 2 <= 22 ** 2:
            c = ACCENT
    return c


rows = []
for py in range(N):
    row = bytearray([0])  # filter type 0
    for px in range(N):
        acc = [0, 0, 0, 0]
        for sy in range(SS):
            for sx in range(SS):
                c = color_at(px + (sx + 0.5) / SS, py + (sy + 0.5) / SS)
                if c:
                    acc[0] += c[0]; acc[1] += c[1]; acc[2] += c[2]; acc[3] += 1
        n = acc[3]
        row += bytes([acc[0] // n, acc[1] // n, acc[2] // n, 255 * n // (SS * SS)]) if n else b"\0\0\0\0"
    rows.append(bytes(row))


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0)) \
    + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")
out = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
out.write_bytes(png)
print(f"wrote {out} ({len(png)} bytes)")

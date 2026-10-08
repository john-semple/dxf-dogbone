"""Draw assets/dxf-dogbone.ico and .png. Stdlib only. Run once to regenerate."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

# Measured from the chosen mark, then symmetrized. Coordinates are in
# disc-radii, origin at the disc center, y down.
_ELBOW = (-0.47, -0.47)
_H_END = (0.47, -0.47)
_V_END = (-0.47, 0.47)
_HALF_STROKE = 0.113
_BLUE = (0.20, 0.20, 0.40)
_DISC_R = 0.46  # fraction of the icon side

_DISC = (0x17, 0x1A, 0x21, 255)
_WHITE = (0xF1, 0xF2, 0xF6, 255)
_BLUE_RGBA = (0x35, 0x7E, 0xFE, 255)

_ROOT = Path(__file__).resolve().parents[1]
_SIZES = (16, 24, 32, 48, 64, 256)


def _seg_dist(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx, aby = bx - ax, by - ay
    t = ((px - ax) * abx + (py - ay) * aby) / (abx * abx + aby * aby)
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    dx, dy = ax + t * abx - px, ay + t * aby - py
    return dx * dx + dy * dy


def render(size: int, ss: int = 4) -> bytes:
    """RGBA, top-down, straight alpha."""
    n = size * ss
    inv = 1.0 / n
    half = _HALF_STROKE * _HALF_STROKE
    bx, by, br = _BLUE
    br2 = br * br
    out = bytearray(size * size * 4)
    samples = ss * ss
    for y in range(size):
        for x in range(size):
            r = g = b = a = 0
            for sy in range(ss):
                for sx in range(ss):
                    # Pixel center of this subsample, in disc-radii.
                    lx = ((x * ss + sx) + 0.5) * inv
                    ly = ((y * ss + sy) + 0.5) * inv
                    dx = (lx - 0.5) / _DISC_R
                    dy = (ly - 0.5) / _DISC_R
                    if dx * dx + dy * dy > 1.0:
                        continue
                    px, py = dx, dy
                    ddx, ddy = px - bx, py - by
                    if ddx * ddx + ddy * ddy <= br2:
                        cr, cg, cb, ca = _BLUE_RGBA
                    elif (
                        _seg_dist(px, py, *_ELBOW, *_H_END) <= half
                        or _seg_dist(px, py, *_ELBOW, *_V_END) <= half
                    ):
                        cr, cg, cb, ca = _WHITE
                    else:
                        cr, cg, cb, ca = _DISC
                    r += cr
                    g += cg
                    b += cb
                    a += ca
            i = (y * size + x) * 4
            out[i] = r // samples
            out[i + 1] = g // samples
            out[i + 2] = b // samples
            out[i + 3] = a // samples
    return bytes(out)


def _png(rgba: bytes, size: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = bytearray()
    stride = size * 4
    for y in range(size):
        raw.append(0)
        raw.extend(rgba[y * stride : (y + 1) * stride])
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)),
            chunk(b"IEND", b""),
        )
    )


def _bmp(rgba: bytes, size: int) -> bytes:
    """ICO-embedded 32-bit DIB: bottom-up BGRA plus a 1-bit AND mask."""
    xor_rows = bytearray()
    for y in range(size - 1, -1, -1):
        row = y * size * 4
        for x in range(size):
            i = row + x * 4
            r, g, b, a = rgba[i : i + 4]
            xor_rows.extend((b, g, r, a))
    mask_stride = ((size + 31) // 32) * 4
    mask = bytearray()
    for y in range(size - 1, -1, -1):
        row = y * size * 4
        bits = 0
        written = 0
        line = bytearray()
        for x in range(size):
            bits = (bits << 1) | (0 if rgba[row + x * 4 + 3] else 1)
            written += 1
            if written == 32:
                line.extend(struct.pack(">I", bits))
                bits = 0
                written = 0
        if written:
            bits <<= 32 - written
            line.extend(struct.pack(">I", bits))
        if len(line) < mask_stride:
            line.extend(b"\x00" * (mask_stride - len(line)))
        mask.extend(line)
    header = struct.pack(
        "<IiiHHIIiiII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        len(xor_rows) + len(mask),
        0,
        0,
        0,
        0,
    )
    return header + bytes(xor_rows) + bytes(mask)


def _ico(images: list[tuple[int, bytes]]) -> bytes:
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries = bytearray()
    blobs = bytearray()
    for size, rgba in images:
        dib = _bmp(rgba, size)
        entries.extend(
            struct.pack(
                "<BBBBHHII",
                size if size < 256 else 0,
                size if size < 256 else 0,
                0,
                0,
                1,
                32,
                len(dib),
                offset,
            )
        )
        blobs.extend(dib)
        offset += len(dib)
    return header + bytes(entries) + bytes(blobs)


def main() -> None:
    rendered = [(size, render(size, ss=8 if size <= 48 else 4)) for size in _SIZES]
    out = _ROOT / "assets"
    out.mkdir(exist_ok=True)
    (out / "dxf-dogbone.ico").write_bytes(_ico(rendered))
    (out / "dxf-dogbone.png").write_bytes(_png(rendered[-1][1], rendered[-1][0]))
    print(f"wrote {out / 'dxf-dogbone.ico'}")


if __name__ == "__main__":
    main()

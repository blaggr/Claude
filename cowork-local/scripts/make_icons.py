#!/usr/bin/env python3
"""Generate placeholder PNG app icons without external dependencies.

Produces the icon sizes referenced by tauri.conf.json. For a production build
that bundles macOS/.icns and Windows/.ico icons, replace these by running:
    npm run tauri icon path/to/logo.png
"""
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(__file__), "..", "src-tauri", "icons")

# Anthropic-ish warm palette: clay accent on a dark ground.
BG = (26, 23, 20, 255)
ACCENT = (217, 119, 87, 255)


def rounded_rect_mask(x, y, w, h, size, radius):
    """Return True if pixel (x,y) is inside a rounded rectangle."""
    if x < size * 0.18 or x >= size * 0.82 or y < size * 0.18 or y >= size * 0.82:
        return False
    # corners
    inner_l, inner_r = size * 0.18 + radius, size * 0.82 - radius
    inner_t, inner_b = size * 0.18 + radius, size * 0.82 - radius
    cx = min(max(x, inner_l), inner_r)
    cy = min(max(y, inner_t), inner_b)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def make_png(size):
    radius = size * 0.12
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0 (none)
        for x in range(size):
            if rounded_rect_mask(x, y, size, size, size, radius):
                raw.extend(ACCENT)
            else:
                raw.extend(BG)
    return _png_bytes(size, size, bytes(raw))


def _png_bytes(width, height, raw):
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(raw, 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def main():
    os.makedirs(OUT, exist_ok=True)
    targets = {
        "32x32.png": 32,
        "128x128.png": 128,
        "128x128@2x.png": 256,
        "icon.png": 512,
        "Square150x150Logo.png": 150,
    }
    for name, size in targets.items():
        with open(os.path.join(OUT, name), "wb") as f:
            f.write(make_png(size))
        print("wrote", name, size)
    # Also drop a copy the web frontend can use as a favicon.
    pub = os.path.join(os.path.dirname(__file__), "..", "public")
    os.makedirs(pub, exist_ok=True)
    with open(os.path.join(pub, "icon.png"), "wb") as f:
        f.write(make_png(64))
    print("wrote public/icon.png")


if __name__ == "__main__":
    main()

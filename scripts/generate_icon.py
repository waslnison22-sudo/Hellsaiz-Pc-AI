from __future__ import annotations

import argparse
import struct
from pathlib import Path


def _pixel(x: int, y: int, size: int) -> tuple[int, int, int, int]:
    """Return a crisp monochrome H mark on a graphite circular field."""
    cx = cy = (size - 1) / 2
    radius = size * 0.46
    if (x - cx) ** 2 + (y - cy) ** 2 > radius**2:
        return 0, 0, 0, 0

    inset = max(1, round(size * 0.25))
    stroke = max(1, round(size * 0.12))
    left, right = inset, size - inset - stroke
    top, bottom = inset, size - inset - stroke
    mid = size // 2 - stroke // 2
    if (left <= x < left + stroke or right <= x < right + stroke) and top <= y < bottom + stroke:
        return 245, 246, 248, 255
    if left <= x < right + stroke and mid <= y < mid + stroke:
        return 245, 246, 248, 255
    return 32, 36, 43, 255


def make_ico(path: Path) -> None:
    """Write a Windows ICO containing 16, 32, 48, 64, 128 and 256px images."""
    sizes = (16, 32, 48, 64, 128, 256)
    images: list[tuple[int, bytes]] = []
    for size in sizes:
        pixels = bytearray()
        for y in range(size - 1, -1, -1):
            for x in range(size):
                red, green, blue, alpha = _pixel(x, y, size)
                pixels.extend((blue, green, red, alpha))
        mask_stride = ((size + 31) // 32) * 4
        mask = bytes(mask_stride * size)
        header = struct.pack("<IIIHHIIIIII", 40, size, size * 2, 1, 32, 0,
                             len(pixels) + len(mask), 0, 0, 0, 0)
        images.append((size, header + pixels + mask))

    directory = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, data in images:
        directory.extend(struct.pack("<BBBBHHII", size if size < 256 else 0,
                                     size if size < 256 else 0, 0, 0, 1, 32,
                                     len(data), offset))
        offset += len(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(directory + b"".join(data for _, data in images))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", type=Path, default=Path("assets/hellsaiz.ico"))
    args = parser.parse_args()
    make_ico(args.output)
    print(f"Created {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

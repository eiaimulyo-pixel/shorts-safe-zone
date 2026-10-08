"""UI zones and box geometry.

A zone is a rectangle (x0, y0, x1, y1) in pixels, defined on a reference frame
(1080x1920 by default) and scaled per axis to the size of the video under test.
A text box is (x, y, w, h). A box "hits" a zone when the two rectangles overlap
by at least one pixel (touching edges do not count).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

BASE_SIZE = (1080, 1920)


@dataclass(frozen=True)
class Zone:
    name: str
    x0: int
    y0: int
    x1: int
    y1: int

    def as_list(self) -> list[int]:
        return [self.x0, self.y0, self.x1, self.y1]


# Default zones on a 1080x1920 frame, where the YouTube Shorts player draws its UI:
#   top    - search / menu icons
#   bottom - channel name, title, music ticker (bottom ~23% of the frame)
#   right  - like / comment / share / remix button column
DEFAULT_ZONES = (
    Zone("top", 0, 0, 1080, 150),
    Zone("bottom", 0, 1480, 1080, 1920),
    Zone("right", 930, 1000, 1080, 1480),
)


class ZonesError(ValueError):
    """The zones file is missing, unreadable or malformed."""


def _parse_rect(raw, where: str) -> tuple[int, int, int, int]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raise ZonesError(f"{where}: rect must be [x0, y0, x1, y1]")
    try:
        x0, y0, x1, y1 = (int(v) for v in raw)
    except (TypeError, ValueError) as exc:
        raise ZonesError(f"{where}: rect values must be numbers") from exc
    if x1 <= x0 or y1 <= y0:
        raise ZonesError(f"{where}: rect needs x1 > x0 and y1 > y0")
    return x0, y0, x1, y1


def load_zones(path: str | Path) -> tuple[tuple[int, int], tuple[Zone, ...]]:
    """Read a zones file.

    Accepted shapes:
      {"base_size": [1080, 1920], "zones": [{"name": "bottom", "rect": [0, 1480, 1080, 1920]}, ...]}
      {"zones": [[0, 0, 1080, 150], ...]}          (base_size defaults to 1080x1920)
      [[0, 0, 1080, 150], ...]
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ZonesError(f"cannot read zones file: {exc}") from exc
    except ValueError as exc:
        raise ZonesError(f"zones file is not valid JSON: {exc}") from exc
    base = BASE_SIZE
    raw_zones = data
    if isinstance(data, dict):
        if "base_size" in data:
            bs = data["base_size"]
            if not isinstance(bs, (list, tuple)) or len(bs) != 2 or int(bs[0]) <= 0 or int(bs[1]) <= 0:
                raise ZonesError("base_size must be [width, height] with positive values")
            base = (int(bs[0]), int(bs[1]))
        raw_zones = data.get("zones")
    if not isinstance(raw_zones, list) or not raw_zones:
        raise ZonesError("zones file must contain a non-empty list of zones")
    zones = []
    for i, z in enumerate(raw_zones):
        if isinstance(z, dict):
            name = str(z.get("name") or f"zone{i + 1}")
            rect = _parse_rect(z.get("rect"), f"zone {i + 1}")
        else:
            name = f"zone{i + 1}"
            rect = _parse_rect(z, f"zone {i + 1}")
        zones.append(Zone(name, *rect))
    return base, tuple(zones)


def scale_zones(zones, width: int, height: int, base_size=BASE_SIZE) -> tuple[Zone, ...]:
    """Scale zones from base_size to (width, height), each axis by its own ratio."""
    sx = width / base_size[0]
    sy = height / base_size[1]
    return tuple(
        Zone(z.name, round(z.x0 * sx), round(z.y0 * sy), round(z.x1 * sx), round(z.y1 * sy)) for z in zones
    )


def hits(box, zones) -> list[Zone]:
    """Zones that the box (x, y, w, h) overlaps."""
    x, y, w, h = box
    return [z for z in zones if x < z.x1 and x + w > z.x0 and y < z.y1 and y + h > z.y0]


def parse_box(text: str) -> tuple[int, int, int, int]:
    """'x,y,w,h' -> (x, y, w, h)."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        raise ValueError(f"box must be x,y,w,h: {text!r}")
    x, y, w, h = (int(round(float(p))) for p in parts)
    if w <= 0 or h <= 0:
        raise ValueError(f"box width and height must be positive: {text!r}")
    return x, y, w, h

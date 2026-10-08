"""Command line: shorts-safe-zone check <video> | shorts-safe-zone box x,y,w,h ..."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .check import (
    DEFAULT_FPS,
    DEFAULT_LANG_PASSES,
    DEFAULT_MAX_SECONDS,
    DEFAULT_MIN_CHARS,
    DEFAULT_MIN_CONFIDENCE,
    EXIT_CODES,
    check,
)
from .zones import BASE_SIZE, DEFAULT_ZONES, ZonesError, hits, load_zones, parse_box, scale_zones


def _zones(path):
    if path:
        return load_zones(path)
    return BASE_SIZE, DEFAULT_ZONES


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="shorts-safe-zone",
        description="Check that on-screen text in a vertical short-form video stays out of platform UI zones.",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="OCR a video and report text inside UI zones (exit 0 pass, 1 fail, 2 unmeasured)")
    c.add_argument("video")
    c.add_argument("--zones", help="JSON file with custom zones (see README)")
    c.add_argument("--fps", type=float, default=DEFAULT_FPS, help=f"frames sampled per second (default {DEFAULT_FPS:g})")
    c.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS,
                   help=f"longer videos are not shorts (default {DEFAULT_MAX_SECONDS:g})")
    c.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE,
                   help=f"ignore OCR results below this confidence (default {DEFAULT_MIN_CONFIDENCE:g})")
    c.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CHARS,
                   help=f"ignore text with fewer letters/digits (default {DEFAULT_MIN_CHARS})")
    c.add_argument("--langs", default=";".join(DEFAULT_LANG_PASSES),
                   help="OCR passes separated by ';', languages in a pass by ',' "
                        f"(default \"{';'.join(DEFAULT_LANG_PASSES)}\")")
    c.add_argument("--output", "-o", help="also write the JSON report to this file")

    b = sub.add_parser("box", help="check planned text boxes x,y,w,h before rendering (exit 0 pass, 1 fail)")
    b.add_argument("boxes", nargs="+", metavar="x,y,w,h")
    b.add_argument("--size", default=f"{BASE_SIZE[0]}x{BASE_SIZE[1]}", help="frame size WxH (default 1080x1920)")
    b.add_argument("--zones", help="JSON file with custom zones")

    x = ap.parse_args(argv)
    try:
        base, zones = _zones(x.zones)
    except ZonesError as exc:
        print(json.dumps({"verdict": "UNMEASURED", "reason": f"zones: {exc}"}))
        return 2

    if x.command == "box":
        try:
            fw, fh = (int(v) for v in x.size.lower().split("x"))
            boxes = [parse_box(s) for s in x.boxes]
        except ValueError as exc:
            print(json.dumps({"verdict": "UNMEASURED", "reason": str(exc)}))
            return 2
        scaled = scale_zones(zones, fw, fh, base)
        rows = []
        for bx in boxes:
            hit = hits(bx, scaled)
            rows.append({"box": dict(zip("xywh", bx)), "verdict": "FAIL" if hit else "PASS",
                         "zones": [z.name for z in hit]})
        bad = any(r["verdict"] == "FAIL" for r in rows)
        print(json.dumps({"verdict": "FAIL" if bad else "PASS", "size": [fw, fh],
                          "zones": [{"name": z.name, "rect": z.as_list()} for z in scaled], "boxes": rows}, indent=2))
        return 1 if bad else 0

    passes = [p.strip() for p in x.langs.split(";") if p.strip()]
    report = check(x.video, zones=zones, base_size=base, fps=x.fps, max_seconds=x.max_seconds,
                   min_confidence=x.min_confidence, min_chars=x.min_chars, lang_passes=passes)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if x.output:
        with open(x.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return EXIT_CODES[report["verdict"]]


if __name__ == "__main__":
    sys.exit(main())

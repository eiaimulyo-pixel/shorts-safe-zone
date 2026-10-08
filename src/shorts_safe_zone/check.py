"""Check a video: sample frames, OCR them, report text that overlaps UI zones."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import __version__
from .ocr import OCRError, run_ocr
from .zones import BASE_SIZE, DEFAULT_ZONES, hits, scale_zones

PASS = "PASS"
FAIL = "FAIL"
UNMEASURED = "UNMEASURED"
NOT_APPLICABLE = "NOT_APPLICABLE"

EXIT_CODES = {PASS: 0, NOT_APPLICABLE: 0, FAIL: 1, UNMEASURED: 2}

DEFAULT_FPS = 2.0
DEFAULT_MAX_SECONDS = 180.0
DEFAULT_MIN_CONFIDENCE = 0.5
DEFAULT_MIN_CHARS = 2
DEFAULT_LANG_PASSES = ("ja-JP,en-US", "ko-KR,en-US")


def char_count(text: str) -> int:
    """Letters and digits only (spaces, punctuation and underscores do not count)."""
    return len(re.sub(r"[\s\W_]", "", str(text or "")))


def probe(video: str) -> tuple[int, int, float]:
    """(width, height, duration seconds) of the first video stream; zeros if unreadable."""
    if not shutil.which("ffprobe"):
        raise FileNotFoundError("ffprobe not found; install ffmpeg")
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", video],
        capture_output=True, text=True,
    )
    try:
        d = json.loads(r.stdout or "{}")
    except ValueError:
        d = {}
    s = (d.get("streams") or [{}])[0]
    return int(s.get("width") or 0), int(s.get("height") or 0), float((d.get("format") or {}).get("duration") or 0)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check(
    video: str,
    zones=DEFAULT_ZONES,
    base_size=BASE_SIZE,
    fps: float = DEFAULT_FPS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    min_chars: int = DEFAULT_MIN_CHARS,
    lang_passes=DEFAULT_LANG_PASSES,
) -> dict:
    """Return a JSON-ready report. report["verdict"] is PASS, FAIL, UNMEASURED or NOT_APPLICABLE."""
    report: dict = {
        "tool": "shorts-safe-zone",
        "version": __version__,
        "video": os.path.basename(video),
        "verdict": None,
        "reason": "",
        "settings": {
            "fps": fps,
            "max_seconds": max_seconds,
            "min_confidence": min_confidence,
            "min_chars": min_chars,
            "ocr_language_passes": list(lang_passes),
            "zones_base_size": list(base_size),
        },
        "frames": 0,
        "text_read": 0,
        "hits": [],
    }

    def done(verdict: str, reason: str) -> dict:
        report["verdict"] = verdict
        report["reason"] = reason
        return report

    if not os.path.isfile(video):
        return done(UNMEASURED, "file not found")
    report["sha256"] = _sha256(video)
    try:
        w, h, dur = probe(video)
    except FileNotFoundError as exc:
        return done(UNMEASURED, str(exc))
    report.update(width=w, height=h, duration=round(dur, 2))
    if not w or not h or not dur:
        return done(UNMEASURED, "ffprobe could not read width, height or duration")
    if h <= w:
        return done(NOT_APPLICABLE, "not a vertical video; no short-form UI overlay")
    if dur > max_seconds:
        return done(NOT_APPLICABLE, f"{dur:.0f}s is longer than {max_seconds:.0f}s; not a short")

    scaled = scale_zones(zones, w, h, base_size)
    report["zones"] = [{"name": z.name, "rect": z.as_list()} for z in scaled]

    with tempfile.TemporaryDirectory(prefix="shorts-safe-zone-") as td:
        r = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", video, "-vf", f"fps={fps}",
             os.path.join(td, "f%05d.png")],
            capture_output=True, text=True,
        )
        frames = sorted(Path(td).glob("f*.png"))
        report["frames"] = len(frames)
        if r.returncode or not frames:
            return done(UNMEASURED, "frame extraction failed: " + (r.stderr or "no frames")[-200:].strip())
        try:
            ocr = run_ocr([str(p) for p in frames], list(lang_passes))
        except OCRError as exc:
            return done(UNMEASURED, f"OCR failed: {exc}"[:300])

        read = 0
        for k, p in enumerate(frames):
            t = round((k + 0.5) / fps, 2)   # the k-th frame of the fps filter sits at about (k + 0.5) / fps seconds
            for item in ocr.get(str(p), []):
                text = str(item.get("text", ""))
                if float(item.get("conf", 0)) < min_confidence or char_count(text) < min_chars:
                    continue
                read += 1
                x, y, bw, bh = (int(round(v)) for v in item["box"])
                hit = hits((x, y, bw, bh), scaled)
                if hit:
                    report["hits"].append({
                        "time": t,
                        "text": text,
                        "confidence": round(float(item.get("conf", 0)), 3),
                        "box": {"x": x, "y": y, "w": bw, "h": bh},
                        "zones": [z.name for z in hit],
                    })
    report["text_read"] = read
    if report["hits"]:
        n = len({hh["text"] for hh in report["hits"]})
        return done(FAIL, f"{n} distinct text(s) overlap UI zones in {len(report['hits'])} detection(s)")
    return done(PASS, f"{len(frames)} frames, {read} text box(es) read, none in UI zones")

"""macOS Vision OCR through a small Swift helper.

The helper source ships with the package. It is compiled with `swiftc` on first
use and cached under ~/.cache/shorts-safe-zone (or $SHORTS_SAFE_ZONE_CACHE).
Every failure raises OCRError: a frame that could not be read is never treated
as a frame without text.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
from importlib import resources
from pathlib import Path

BATCH = 40


class OCRError(RuntimeError):
    """OCR could not run or returned something unusable."""


def _cache_dir() -> Path:
    env = os.environ.get("SHORTS_SAFE_ZONE_CACHE")
    if env:
        return Path(env)
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "shorts-safe-zone"


def helper_path() -> str:
    """Build (if needed) and return the path of the OCR helper binary."""
    if platform.system() != "Darwin":
        raise OCRError("OCR needs macOS (Vision framework); this system is " + platform.system())
    src = resources.files("shorts_safe_zone").joinpath("ocr_vision.swift").read_bytes()
    digest = hashlib.sha256(src).hexdigest()[:12]
    out = _cache_dir() / f"ocr_vision-{digest}"
    if out.is_file() and os.access(out, os.X_OK):
        return str(out)
    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise OCRError("swiftc not found; install Xcode Command Line Tools (xcode-select --install)")
    out.parent.mkdir(parents=True, exist_ok=True)
    src_file = out.parent / f"ocr_vision-{digest}.swift"
    src_file.write_bytes(src)
    tmp = out.with_suffix(".tmp")
    r = subprocess.run([swiftc, "-O", str(src_file), "-o", str(tmp)], capture_output=True, text=True)
    if r.returncode or not tmp.is_file():
        raise OCRError("building the OCR helper failed: " + (r.stderr or r.stdout)[-400:])
    os.replace(tmp, out)
    return str(out)


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _dedupe(items: list[dict], same_box_iou: float = 0.8) -> list[dict]:
    """Merge detections of the same text line from different language passes.

    Boxes that overlap with IoU >= same_box_iou count as one line; the most
    confident reading is kept.
    """
    out: list[dict] = []
    for it in sorted(items, key=lambda d: -float(d.get("conf", 0))):
        box = it.get("box") or [0, 0, 0, 0]
        if any(_iou(box, kept.get("box") or [0, 0, 0, 0]) >= same_box_iou for kept in out):
            continue
        out.append(it)
    return out


def run_ocr(paths: list[str], lang_passes: list[str]) -> dict[str, list[dict]]:
    """{image path: [{"text", "conf", "box": [x, y, w, h]}]}.

    Each entry of lang_passes is one recognition pass (comma separated language
    codes); results of all passes are merged and exact duplicates removed.
    """
    if not paths:
        raise OCRError("no frames to read")
    if not lang_passes:
        raise OCRError("no OCR language pass given")
    binary = helper_path()
    out: dict[str, list[dict]] = {p: [] for p in paths}
    for langs in lang_passes:
        for i in range(0, len(paths), BATCH):
            chunk = paths[i:i + BATCH]
            try:
                r = subprocess.run([binary, *chunk], capture_output=True, text=True,
                                   env=dict(os.environ, OCR_VISION_LANGS=langs), timeout=600)
            except subprocess.TimeoutExpired as exc:
                raise OCRError(f"OCR helper timed out ({langs})") from exc
            if r.returncode:
                raise OCRError(f"OCR helper exited {r.returncode} ({langs}): {r.stderr[-300:]}")
            try:
                data = json.loads(r.stdout)
            except ValueError as exc:
                raise OCRError(f"OCR helper returned invalid JSON ({langs})") from exc
            files = data.get("files") or []
            got = {f.get("file") for f in files}
            missing = [p for p in chunk if p not in got]
            if missing:
                raise OCRError(f"OCR helper skipped {len(missing)} frame(s) ({langs})")
            for f in files:
                if f.get("error"):
                    raise OCRError(f"OCR failed on {os.path.basename(f['file'])} ({langs}): {f['error']}")
                out[f["file"]].extend(f.get("items") or [])
    return {p: _dedupe(v) for p, v in out.items()}

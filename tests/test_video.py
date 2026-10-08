"""End-to-end tests on synthetic videos made with ffmpeg drawtext. Needs macOS + ffmpeg."""
import contextlib
import io
import os
import platform
import shutil
import subprocess
import tempfile
import unittest

from shorts_safe_zone.check import FAIL, NOT_APPLICABLE, PASS, UNMEASURED, check
from shorts_safe_zone.cli import main


def run_cli(args):
    with contextlib.redirect_stdout(io.StringIO()):
        return main(args)

FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
)

HAVE_TOOLS = platform.system() == "Darwin" and shutil.which("ffmpeg") and shutil.which("ffprobe")


def make_video(path, size, text=None, x=None, y=None, fontsize=72, seconds=2):
    w, h = size
    vf = "format=yuv420p"
    if text:
        font = next((f for f in FONT_CANDIDATES if os.path.isfile(f)), None)
        font_opt = f"fontfile='{font}':" if font else ""
        vf = (f"drawtext={font_opt}text='{text}':fontcolor=white:fontsize={fontsize}:"
              f"box=1:boxcolor=black@0.6:boxborderw=12:x={x}:y={y},{vf}")
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x3060a0:s={w}x{h}:d={seconds}:r=30",
         "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
        check=True, capture_output=True,
    )
    return path


@unittest.skipUnless(HAVE_TOOLS, "needs macOS, ffmpeg and ffprobe")
class SyntheticVideos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="ssz-test-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def p(self, name):
        return os.path.join(self.tmp, name)

    def test_text_in_bottom_zone_fails(self):
        v = make_video(self.p("bottom.mp4"), (1080, 1920), "SUBSCRIBE NOW", "(w-text_w)/2", 1650)
        r = check(v)
        self.assertEqual(r["verdict"], FAIL, r)
        self.assertGreater(r["frames"], 0)
        hit = r["hits"][0]
        self.assertIn("bottom", hit["zones"])
        self.assertIn("SUBSCRIBE", hit["text"].upper())
        self.assertGreaterEqual(hit["box"]["y"] + hit["box"]["h"], 1480)
        self.assertGreaterEqual(hit["time"], 0)
        self.assertEqual(run_cli(["check", v]), 1)

    def test_text_in_center_passes(self):
        v = make_video(self.p("center.mp4"), (1080, 1920), "HELLO WORLD", "(w-text_w)/2", "(h-text_h)/2")
        r = check(v)
        self.assertEqual(r["verdict"], PASS, r)
        self.assertGreater(r["text_read"], 0, "OCR should have read the centered text")
        self.assertEqual(r["hits"], [])
        self.assertEqual(run_cli(["check", v]), 0)

    def test_scaled_zones_on_small_frame(self):
        # 540x960: bottom zone starts at y=740; text at y=800 must fail
        v = make_video(self.p("small.mp4"), (540, 960), "LINK IN BIO", "(w-text_w)/2", 800, fontsize=40)
        r = check(v)
        self.assertEqual(r["verdict"], FAIL, r)
        self.assertEqual(r["zones"][1]["rect"], [0, 740, 540, 960])

    def test_landscape_is_not_applicable(self):
        v = make_video(self.p("wide.mp4"), (1280, 720), "WIDE", 100, 600)
        self.assertEqual(check(v)["verdict"], NOT_APPLICABLE)

    def test_long_video_is_not_applicable(self):
        v = make_video(self.p("long.mp4"), (1080, 1920), "LONG", 100, 1600)
        self.assertEqual(check(v, max_seconds=1)["verdict"], NOT_APPLICABLE)

    def test_broken_file_is_unmeasured(self):
        bad = self.p("broken.mp4")
        with open(bad, "wb") as f:
            f.write(b"not a video")
        self.assertEqual(check(bad)["verdict"], UNMEASURED)
        self.assertEqual(run_cli(["check", bad]), 2)
        self.assertEqual(check(self.p("missing.mp4"))["verdict"], UNMEASURED)

    def test_ocr_failure_is_unmeasured(self):
        v = make_video(self.p("nolang.mp4"), (1080, 1920), "TEXT", 100, 900)
        self.assertEqual(check(v, lang_passes=[])["verdict"], UNMEASURED)


if __name__ == "__main__":
    unittest.main()

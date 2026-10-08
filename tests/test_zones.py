import contextlib
import io
import json
import os
import tempfile
import unittest

from shorts_safe_zone.check import char_count
from shorts_safe_zone.cli import main


def run_cli(args):
    with contextlib.redirect_stdout(io.StringIO()):
        return main(args)
from shorts_safe_zone.zones import DEFAULT_ZONES, Zone, ZonesError, hits, load_zones, parse_box, scale_zones


class ZoneMath(unittest.TestCase):
    def test_default_zones(self):
        self.assertEqual(
            [z.as_list() for z in DEFAULT_ZONES],
            [[0, 0, 1080, 150], [0, 1480, 1080, 1920], [930, 1000, 1080, 1480]],
        )

    def test_scale_half(self):
        z = scale_zones(DEFAULT_ZONES, 540, 960)
        self.assertEqual([q.as_list() for q in z], [[0, 0, 540, 75], [0, 740, 540, 960], [465, 500, 540, 740]])

    def test_scale_per_axis(self):
        # 720x1280 is the same aspect ratio; 1080x2340 is taller, only y stretches
        self.assertEqual(scale_zones(DEFAULT_ZONES, 720, 1280)[1].as_list(), [0, 987, 720, 1280])
        self.assertEqual(scale_zones(DEFAULT_ZONES, 1080, 2340)[0].as_list(), [0, 0, 1080, 183])

    def test_center_box_passes(self):
        self.assertEqual(hits((200, 900, 600, 100), DEFAULT_ZONES), [])

    def test_bottom_box_fails(self):
        self.assertEqual([z.name for z in hits((100, 1500, 400, 80), DEFAULT_ZONES)], ["bottom"])

    def test_right_column(self):
        self.assertEqual([z.name for z in hits((900, 1200, 100, 50), DEFAULT_ZONES)], ["right"])
        self.assertEqual(hits((800, 1200, 129, 50), DEFAULT_ZONES), [])   # ends at x=929

    def test_touching_edge_is_not_a_hit(self):
        self.assertEqual(hits((0, 150, 100, 50), DEFAULT_ZONES), [])      # starts on the top zone's edge
        self.assertEqual(hits((0, 1430, 100, 50), DEFAULT_ZONES), [])     # ends on the bottom zone's edge
        self.assertEqual([z.name for z in hits((0, 1431, 100, 50), DEFAULT_ZONES)], ["bottom"])

    def test_box_in_two_zones(self):
        names = sorted(z.name for z in hits((950, 1400, 100, 200), DEFAULT_ZONES))
        self.assertEqual(names, ["bottom", "right"])

    def test_parse_box(self):
        self.assertEqual(parse_box("10, 20, 30.4, 40.6"), (10, 20, 30, 41))
        with self.assertRaises(ValueError):
            parse_box("1,2,3")
        with self.assertRaises(ValueError):
            parse_box("1,2,0,5")

    def test_char_count(self):
        self.assertEqual(char_count("a b-c_!"), 3)
        self.assertEqual(char_count("I"), 1)
        self.assertEqual(char_count(""), 0)


class Dedupe(unittest.TestCase):
    def test_same_line_from_two_passes_kept_once(self):
        from shorts_safe_zone.ocr import _dedupe
        items = [
            {"text": "Follow for part2", "conf": 0.5, "box": [312, 1592, 464, 72]},
            {"text": "Follow for part 2", "conf": 1.0, "box": [312, 1592, 466, 72]},
            {"text": "Main caption", "conf": 1.0, "box": [300, 900, 480, 90]},
        ]
        out = _dedupe(items)
        self.assertEqual(sorted(i["text"] for i in out), ["Follow for part 2", "Main caption"])


class ZonesFile(unittest.TestCase):
    def _write(self, data):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        self.addCleanup(os.remove, path)
        return path

    def test_named_zones_with_base(self):
        base, zones = load_zones(self._write({"base_size": [720, 1280], "zones": [{"name": "caption", "rect": [0, 1000, 720, 1280]}]}))
        self.assertEqual(base, (720, 1280))
        self.assertEqual(zones, (Zone("caption", 0, 1000, 720, 1280),))

    def test_plain_list(self):
        base, zones = load_zones(self._write([[0, 0, 1080, 200]]))
        self.assertEqual(base, (1080, 1920))
        self.assertEqual(zones[0].as_list(), [0, 0, 1080, 200])

    def test_bad_files(self):
        for bad in ["not json", [], {"zones": [[0, 0, 10]]}, {"zones": [[10, 0, 5, 5]]}, {"base_size": [0, 1], "zones": [[0, 0, 1, 1]]}]:
            with self.assertRaises(ZonesError, msg=repr(bad)):
                load_zones(self._write(bad))
        with self.assertRaises(ZonesError):
            load_zones("/nonexistent/zones.json")


class BoxCommand(unittest.TestCase):
    def test_exit_codes(self):
        self.assertEqual(run_cli(["box", "200,900,600,100"]), 0)
        self.assertEqual(run_cli(["box", "200,900,600,100", "100,1500,400,80"]), 1)
        self.assertEqual(run_cli(["box", "100,750,200,50", "--size", "540x960"]), 1)
        self.assertEqual(run_cli(["box", "1,2,3"]), 2)


if __name__ == "__main__":
    unittest.main()

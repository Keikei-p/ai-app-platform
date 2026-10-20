import re
import unittest

from src.ui.window_geometry import fit_geometry


class WindowGeometryTests(unittest.TestCase):
    def test_client_and_decorations_fit_short_and_scaled_desktops(self):
        for area in ((0, 0, 1280, 720), (0, 0, 853, 480), (0, 40, 1024, 728)):
            with self.subTest(area=area):
                w, h, x, y = map(int, re.findall(r"\d+", fit_geometry(area)))
                left, top, width, height = area
                self.assertGreaterEqual(x, left)
                self.assertGreaterEqual(y, top)
                self.assertLessEqual(x + w + 16, left + width)
                self.assertLessEqual(y + h + 60, top + height)

    def test_large_desktop_keeps_readable_initial_size(self):
        self.assertTrue(fit_geometry((0, 0, 3840, 2100)).startswith("1140x760"))

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from usage_layout import side_geometry
except ImportError:
    side_geometry = None


class SideMenuTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(side_geometry, "Side menus not implemented yet")

    def test_opens_right_on_left_monitor(self):
        x, y, w, h = side_geometry((-1061, 1221, 382, 374), [(-1080, -377, 0, 1485)], 300, 430)
        self.assertEqual(x, -671)
        self.assertLessEqual(y + h, 1477)
        self.assertEqual(w, 300)

    def test_opens_left_if_right_edge_is_near(self):
        x, y, w, h = side_geometry((-390, 100, 382, 374), [(-1080, -377, 0, 1485)], 300, 430)
        self.assertEqual(x + w, -398)

    def test_narrow_space_shrinks_panel_but_never_overlaps_widget(self):
        x, y, w, h = side_geometry((349, 600, 382, 374), [(0, 0, 1080, 1000)], 500, 480)
        self.assertTrue(x >= 739 or x + w <= 341)
        self.assertGreater(w, 300)
        self.assertGreaterEqual(x, 8)
        self.assertLessEqual(x + w, 1072)


if __name__ == "__main__":
    unittest.main()

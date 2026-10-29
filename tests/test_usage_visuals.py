import unittest
from usage_visuals import hit_target, render_bar, profile_from_config, PROFILES


class VisualTests(unittest.TestCase):
    def test_profile_migration_and_mini_width(self):
        self.assertEqual(profile_from_config({"compact": True}), "horizontal")
        self.assertEqual(profile_from_config({"compact": False}), "detailed")
        self.assertEqual(profile_from_config({"profile": "square"}), "square")
        self.assertEqual(PROFILES["mini"][:2], (60, 180))

    def test_icon_centres_and_clickable_padding_match_each_profile(self):
        for name, (width, height, _) in PROFILES.items():
            if name == "mini":
                self.assertEqual(hit_target(name, width, 30, 90), "menu")
            else:
                self.assertEqual(hit_target(name, width, width - 28, 26), "menu")
                self.assertEqual(hit_target(name, width, width - 64, 26), "refresh")
                self.assertEqual(hit_target(name, width, width - 77, 35), "refresh")

    def test_bar_has_square_edges_and_zero_is_empty(self):
        image = render_bar(100, "#71ddb6", "still", 0, 100)
        self.assertEqual(image.size, (100, 48))
        self.assertGreater(image.getpixel((0, 13))[3], 240)
        self.assertGreater(image.getpixel((99, 34))[3], 240)
        empty = render_bar(0, "#71ddb6", "still", 0, 100)
        self.assertNotEqual(image.getpixel((50, 24)), empty.getpixel((50, 24)))
        self.assertEqual(render_bar(50, "#71ddb6", "fire", 1, 116, True).size, (40, 116))

    def test_active_effect_moves_but_idle_does_not(self):
        idle = render_bar(76, "#71ddb6", "still", 0).tobytes()
        self.assertEqual(idle, render_bar(76, "#71ddb6", "still", 5).tobytes())
        self.assertNotEqual(
            render_bar(76, "#71ddb6", "fire", 0).tobytes(), render_bar(76, "#71ddb6", "fire", 1).tobytes()
        )

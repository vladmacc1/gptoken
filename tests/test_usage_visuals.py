import unittest
import math
from PIL import Image, ImageChops
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

    def oriented_bar(self, remaining, mode, phase, vertical=False, light=False):
        width = 100 if vertical else 346
        image = render_bar(
            remaining,
            "#36b684" if light else "#71ddb6",
            mode,
            phase,
            width,
            vertical,
            track_color="#e2e7ed" if light else "#303843",
        )
        return image.transpose(Image.Transpose.ROTATE_270) if vertical else image

    def test_still_pixels_do_not_depend_on_phase_in_either_orientation(self):
        for vertical in (False, True):
            for light in (False, True):
                for remaining in (0, 1, 42, 100):
                    with self.subTest(vertical=vertical, light=light, remaining=remaining):
                        first = self.oriented_bar(remaining, "still", 0, vertical, light)
                        for phase in (0.7, 5, 100):
                            self.assertEqual(
                                first.tobytes(), self.oriented_bar(remaining, "still", phase, vertical, light).tobytes()
                            )

    def test_active_motion_reaches_first_and_middle_thirds_of_the_fill(self):
        for vertical in (False, True):
            for light in (False, True):
                for mode in ("fire", "lava"):
                    first = self.oriented_bar(72, mode, 0, vertical, light)
                    second = self.oriented_bar(72, mode, 0.85, vertical, light)
                    top = 8 if vertical else 12
                    third = int(first.width * 0.72 / 3)
                    for index in (0, 1):
                        with self.subTest(vertical=vertical, light=light, mode=mode, third=index):
                            region = (index * third + 1, top + 1, (index + 1) * third - 1, top + 23)
                            difference = ImageChops.difference(
                                first.crop(region).convert("RGB"), second.crop(region).convert("RGB")
                            )
                            significant = difference.point(lambda value: 255 if value >= 8 else 0)
                            red, green, blue = significant.split()
                            changed = ImageChops.lighter(ImageChops.lighter(red, green), blue).histogram()[255]
                            area = (region[2] - region[0]) * (region[3] - region[1])
                            self.assertGreater(changed, area * 0.02)

    def test_zero_quota_has_no_active_pixels_or_phase_changes(self):
        for vertical in (False, True):
            for light in (False, True):
                still = self.oriented_bar(0, "still", 0, vertical, light)
                for mode in ("fire", "lava"):
                    for phase in (0, 0.85, 5):
                        with self.subTest(vertical=vertical, light=light, mode=mode, phase=phase):
                            self.assertEqual(
                                still.tobytes(), self.oriented_bar(0, mode, phase, vertical, light).tobytes()
                            )

    def test_active_pixels_stay_within_quota_and_track_with_one_pixel_aa_margin(self):
        for vertical in (False, True):
            for light in (False, True):
                for remaining in (1, 5, 42, 99, 100):
                    still = self.oriented_bar(remaining, "still", 0, vertical, light)
                    top = 8 if vertical else 12
                    endpoint = min(still.width, math.ceil(still.width * remaining / 100) + 1)
                    regions = [
                        (endpoint, 0, still.width, still.height),
                        (0, 0, still.width, top - 1),
                        (0, top + 25, still.width, still.height),
                    ]
                    for mode in ("fire", "lava"):
                        for phase in (0, 0.85):
                            active = self.oriented_bar(remaining, mode, phase, vertical, light)
                            self.assertEqual(active.size, still.size)
                            for region in regions:
                                with self.subTest(
                                    vertical=vertical,
                                    light=light,
                                    remaining=remaining,
                                    mode=mode,
                                    phase=phase,
                                    region=region,
                                ):
                                    self.assertEqual(active.crop(region).tobytes(), still.crop(region).tobytes())

    def test_full_quota_still_has_internal_active_motion(self):
        for vertical in (False, True):
            for light in (False, True):
                for mode in ("fire", "lava"):
                    with self.subTest(vertical=vertical, light=light, mode=mode):
                        first = self.oriented_bar(100, mode, 0, vertical, light)
                        second = self.oriented_bar(100, mode, 0.85, vertical, light)
                        self.assertNotEqual(first.tobytes(), second.tobytes())

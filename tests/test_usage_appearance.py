import unittest
from usage_appearance import STYLES, THEMES, appearance_from_config, widget_size
from usage_presenter import demo_rows, render_static, render_bar_spec, compose_preview


class AppearanceTests(unittest.TestCase):
    def test_legacy_settings_migrate_without_an_unknown_style_or_theme(self):
        self.assertEqual(
            appearance_from_config({"profile": "horizontal"}), {"style": "minimal", "theme": "dark", "history": False}
        )
        self.assertTrue(appearance_from_config({"profile": "detailed"})["history"])
        self.assertEqual(appearance_from_config({"uiStyle": "invalid", "theme": "broken"})["theme"], "dark")

    def test_all_96_style_theme_profile_plan_history_combinations_fit(self):
        now = 1800000000
        for style in STYLES:
            for theme in THEMES:
                for profile in ("horizontal", "square", "mini", "detailed"):
                    for dual in (False, True):
                        for history in (False, True):
                            with self.subTest(style=style, theme=theme, profile=profile, dual=dual, history=history):
                                frame = render_static(
                                    style,
                                    theme,
                                    profile,
                                    demo_rows(dual, now),
                                    plan="plus" if dual else "pro",
                                    history=history,
                                    sync="Обновлено 1 с назад",
                                    activity="Ожидание",
                                    now=now,
                                )
                                self.assertEqual(frame.image.size, widget_size(style, profile, dual, history))
                                width, height = frame.image.size
                                for box in frame.text_boxes:
                                    self.assertGreaterEqual(box[0], 0)
                                    self.assertGreaterEqual(box[1], 0)
                                    self.assertLessEqual(box[2], width)
                                    self.assertLessEqual(box[3], height)
                                for spec in frame.bars:
                                    bar = render_bar_spec(spec)
                                    self.assertGreaterEqual(spec["x"], 0)
                                    self.assertGreaterEqual(spec["y"], 0)
                                    self.assertLessEqual(spec["x"] + bar.width, width)
                                    self.assertLessEqual(spec["y"] + bar.height, height)
                                self.assertEqual(compose_preview(frame).size, frame.image.size)

    def test_styles_have_different_geometry_and_mini_stays_60_pixels(self):
        self.assertNotEqual(widget_size("minimal", "horizontal", True), widget_size("telemetry", "horizontal", True))
        self.assertNotEqual(widget_size("compact", "horizontal", True), widget_size("minimal", "horizontal", True))
        for style in STYLES:
            self.assertEqual(widget_size(style, "mini", True), (60, 180))

    def test_missing_window_keeps_dash_and_empty_track(self):
        rows = demo_rows(True, 1800000000)
        rows[0].update(remaining=None, reset=None, segments=[])
        frame = render_static("minimal", "light", "horizontal", rows, plan="plus", now=1800000000)
        self.assertEqual(frame.bars[0]["remaining"], 0)
        self.assertFalse(frame.bars[0]["valid"])
        self.assertEqual(frame.bars[1]["remaining"], 42)

    def test_themes_change_pixels_without_changing_quota_values(self):
        rows = demo_rows(True, 1800000000)
        dark = render_static("minimal", "dark", "horizontal", rows, now=1800000000)
        light = render_static("minimal", "light", "horizontal", rows, now=1800000000)
        self.assertNotEqual(dark.image.getpixel((100, 10)), light.image.getpixel((100, 10)))
        self.assertEqual([b["remaining"] for b in dark.bars], [b["remaining"] for b in light.bars])

    def test_history_visibility_changes_presentation_not_measurements(self):
        rows = demo_rows(True, 1800000000)
        hidden = render_static("minimal", "dark", "horizontal", rows, history=False, now=1800000000)
        shown = render_static("minimal", "dark", "horizontal", rows, history=True, now=1800000000)
        self.assertGreater(shown.image.height, hidden.image.height)
        self.assertEqual([b["remaining"] for b in shown.bars], [b["remaining"] for b in hidden.bars])

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import usage_pace as pace
except ImportError:
    pace = None


class PaceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(pace, "Расчёт темпа ещё не реализован")
        self.history = pace.PaceHistory()

    def add(self, t, used, reset=36000):
        self.history.add(t, used, reset, 10080, "codex")

    def test_rate_is_percentage_points_per_hour(self):
        self.add(0, 20)
        self.add(120, 21)
        self.add(240, 22)
        state = self.history.evaluate(240, 78, 36000)
        self.assertAlmostEqual(state["rate"], 30)
        self.assertAlmostEqual(state["budget"], 7.85234899328859)
        self.assertEqual(state["mode"], "fire")

    def test_four_minutes_required_before_claiming_speed(self):
        self.add(0, 20)
        self.add(120, 24)
        self.assertEqual(self.history.evaluate(120, 76, 36000)["mode"], "learning")

    def test_no_consumption_is_idle(self):
        for t in (0, 120, 240):
            self.add(t, 20)
        self.assertEqual(self.history.evaluate(240, 80, 36000)["mode"], "idle")

    def test_all_speed_bands_relative_to_remaining_budget(self):
        for delta, expected in ((0.5, "calm"), (1, "elevated"), (2, "fire"), (4, "lava")):
            with self.subTest(expected=expected):
                self.history = pace.PaceHistory()
                self.add(0, 20 - delta)
                self.add(120, 20 - delta / 2)
                self.add(240, 20)
                self.assertEqual(self.history.evaluate(240, 80, 36240)["mode"], expected)

    def test_old_activity_ages_out_of_thirty_minute_window(self):
        for t in range(0, 3720, 120):
            self.add(t, min(t / 120, 10))
        self.assertEqual(self.history.evaluate(3600, 90, 36000)["mode"], "idle")

    def test_reset_does_not_become_negative_usage(self):
        self.add(0, 90)
        self.add(120, 92)
        self.add(240, 1, reset=72000)
        self.assertEqual(self.history.evaluate(240, 99, 72000)["mode"], "learning")

    def test_correction_and_long_gap_restart_measurement(self):
        for series in (((0, 40), (120, 41), (240, 39)), ((0, 40), (120, 41), (800, 50))):
            self.history = pace.PaceHistory()
            for t, used in series:
                self.add(t, used)
            self.assertEqual(self.history.evaluate(series[-1][0], 50, 36000)["mode"], "learning")

    def test_stale_failure_expiration_and_exhaustion_stop_effects(self):
        for t, used in ((0, 20), (120, 22), (240, 24)):
            self.add(t, used)
        self.assertEqual(self.history.evaluate(600, 76, 36000)["mode"], "stale")
        self.assertEqual(self.history.evaluate(240, 76, 36000, failed=True)["mode"], "stale")
        self.assertEqual(self.history.evaluate(240, 76, 240)["mode"], "reset")
        self.assertEqual(self.history.evaluate(240, 0, 36000)["mode"], "empty")

    def test_saved_history_survives_restart(self):
        for t, used in ((0, 20), (120, 21), (240, 22)):
            self.add(t, used)
        restored = pace.PaceHistory(self.history.to_json())
        self.assertEqual(restored.evaluate(240, 78, 36000), self.history.evaluate(240, 78, 36000))

    def test_invalid_and_out_of_order_samples_cannot_poison_history(self):
        self.add(0, 20)
        self.add(120, 21)
        for t, used in ((60, 19), (180, math.nan), (180, -2), (180, 150)):
            self.add(t, used)
        self.add(240, 22)
        self.assertEqual(self.history.evaluate(240, 78, 36000)["rate"], 30)

    def test_colors_follow_remaining_quota_at_boundaries(self):
        expected = [
            (100, "green"),
            (61, "green"),
            (60, "yellow"),
            (41, "yellow"),
            (40, "orange"),
            (16, "orange"),
            (15, "red"),
            (0, "red"),
        ]
        for remaining, color in expected:
            self.assertEqual(pace.quota_band(remaining), color)

    def test_countdown_never_goes_negative(self):
        self.assertEqual(pace.reset_countdown(9000, 0), "До сброса 2 ч 30 мин")
        self.assertEqual(pace.reset_countdown(176400, 0), "До сброса 2 дн, 1 час")
        self.assertEqual(pace.reset_countdown(30, 0), "До сброса менее 1 мин")
        self.assertEqual(pace.reset_countdown(0, 30), "Ожидаем сброс лимита")


if __name__ == "__main__":
    unittest.main()

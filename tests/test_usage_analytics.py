import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import usage_analytics as a
except ImportError:
    a = None


def stamp(day, hour=0):
    return datetime(2026, 10, day, hour, tzinfo=timezone(timedelta(hours=3))).timestamp()


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(a, "Analytics features are not implemented yet")
        self.book = a.UsageBook()

    def feed(self, now, used, reset=None, hours=168):
        reset = reset if reset is not None else stamp(12)
        self.book.ingest(
            {
                "updatedAt": now,
                "bucket": "codex",
                "windows": [{"usedPercent": used, "resetsAt": reset, "windowDurationMins": hours * 60}],
            }
        )
        return next(iter(self.book.windows))

    def test_forecast_reports_exhaustion_or_sufficient_budget(self):
        self.assertEqual(a.forecast(50, 10, 0, 36000)["seconds"], 18000)
        self.assertTrue(a.forecast(50, 10, 0, 36000)["risk"])
        self.assertFalse(a.forecast(50, 2, 0, 36000)["risk"])
        self.assertIsNone(a.forecast(50, None, 0, 36000)["seconds"])
        self.assertEqual(a.forecast(50, 0, 0, 36000)["state"], "idle")
        self.assertEqual(a.forecast(50, 10, 0, 36000, stale=True)["state"], "stale")

    def test_daily_budget_and_plan_marker_have_independent_expected_values(self):
        slot = self.feed(stamp(5), 40, stamp(9))
        self.feed(stamp(5, 12), 50, stamp(9))
        budget = self.book.budget(slot, stamp(5, 12))
        self.assertAlmostEqual(budget["allocation"], 15)
        self.assertAlmostEqual(budget["available"], 5)
        self.assertAlmostEqual(budget["expectedRemaining"], 52.5)
        self.assertAlmostEqual(budget["ahead"], 2.5)

    def test_workdays_exclude_weekend_and_never_divide_by_zero(self):
        self.assertEqual(a.eligible_seconds(stamp(9), stamp(12), True), 86400)
        self.assertEqual(a.eligible_seconds(stamp(10), stamp(12), True), 0)
        self.book.workdays = True
        slot = self.feed(stamp(10), 40, stamp(11))
        self.assertEqual(self.book.budget(slot, stamp(10))["available"], 0)

    def test_session_pause_resume_and_reset(self):
        t = stamp(5)
        slot = self.feed(t, 10)
        self.feed(t + 120, 12)
        self.assertEqual(self.book.session_summary(slot, t + 120)["spent"], 2)
        self.book.pause_session(t + 120)
        self.feed(t + 240, 20)
        self.book.resume_session(t + 300)
        self.feed(t + 360, 21)
        self.feed(t + 480, 23)
        summary = self.book.session_summary(slot, t + 480)
        self.assertEqual(summary["spent"], 4)
        self.assertEqual(summary["seconds"], 300)
        self.book.reset_session(t + 500)
        self.assertEqual(self.book.session_summary(slot, t + 500)["spent"], 0)
        self.book.pause_session(t + 510)
        self.book.reset_session(t + 520)
        self.assertTrue(self.book.session_summary(slot, t + 520)["running"])

    def test_session_handles_reset_without_negative_or_fictitious_spend(self):
        t = stamp(5)
        slot = self.feed(t, 90, t + 200)
        self.feed(t + 120, 92, t + 200)
        self.feed(t + 240, 1, t + 20000)
        summary = self.book.session_summary(slot, t + 240)
        self.assertEqual(summary["spent"], 3)
        self.assertTrue(summary["partial"])

    def test_most_restrictive_window_uses_its_own_rate(self):
        t = stamp(5)
        for i in range(4):
            self.book.ingest(
                {
                    "updatedAt": t + i * 120,
                    "bucket": "codex",
                    "windows": [
                        {"usedPercent": 20 + i, "resetsAt": t + 86400, "windowDurationMins": 10080},
                        {"usedPercent": 89 + i, "resetsAt": t + 18000, "windowDurationMins": 300},
                    ],
                }
            )
        self.assertEqual(self.book.windows[self.book.select(t + 360)]["window"]["windowDurationMins"], 300)
        self.assertEqual(len(self.book.windows), 2)

    def test_absent_windows_do_not_survive_as_active_limits(self):
        self.test_most_restrictive_window_uses_its_own_rate()
        slot = self.feed(stamp(5) + 480, 24)
        self.assertEqual(len(self.book.active), 1)
        self.assertEqual(self.book.select(stamp(5) + 480), slot)

    def test_chart_breaks_at_missing_data_and_reset(self):
        t = stamp(5)
        slot = self.feed(t, 10)
        self.feed(t + 120, 11)
        self.feed(t + 720, 20)
        self.feed(t + 840, 1, stamp(13))
        segments = self.book.chart_segments(slot, t + 840, 3600)
        self.assertEqual([len(s) for s in segments], [2, 1, 1])

    def test_archive_and_active_session_survive_restart(self):
        t = stamp(5)
        slot = self.feed(t, 10)
        self.feed(t + 120, 12)
        restored = a.UsageBook(self.book.to_json())
        self.assertEqual(restored.session_summary(slot, t + 120)["spent"], 2)
        self.assertEqual(restored.chart_segments(slot, t + 120, 86400), self.book.chart_segments(slot, t + 120, 86400))

    def test_alert_frequency_and_reset_notification(self):
        t = stamp(5)
        self.feed(t, 10)
        gate = a.AlertGate()
        self.assertIsNone(gate.check(self.book, t))
        self.feed(t + 120, 16)
        self.assertEqual(gate.check(self.book, t + 120)["kind"], "rapid")
        self.feed(t + 240, 22)
        self.assertIsNone(gate.check(self.book, t + 240))
        self.feed(t + 1800, 1, stamp(13))
        self.assertEqual(gate.check(self.book, t + 1800)["kind"], "reset")

    def test_expired_or_missing_limit_is_not_a_valid_forecast(self):
        self.assertEqual(a.forecast(50, 2, 100, 99)["state"], "reset")
        self.assertEqual(a.forecast(50, 2, 100, None)["state"], "unknown")

    def test_duplicate_observations_do_not_double_count(self):
        t = stamp(5)
        slot = self.feed(t, 10)
        self.feed(t + 120, 12)
        self.feed(t + 120, 12)
        self.assertEqual(self.book.session_summary(slot, t + 120)["spent"], 2)
        self.assertEqual(len(self.book.windows[slot]["samples"]), 2)


if __name__ == "__main__":
    unittest.main()

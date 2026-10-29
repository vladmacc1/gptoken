import unittest
from usage_subscription import normalize_plan, subscription_view, profile_size
from usage_visuals import PROFILES, hit_target
from usage_transport import AccountClient


class SubscriptionTests(unittest.TestCase):
    def windows(self):
        return [{"windowDurationMins": 300, "usedPercent": 32}, {"windowDurationMins": 10080, "usedPercent": 58}]

    def test_plus_has_two_independent_real_windows(self):
        view = subscription_view({"planType": "plus", "windows": self.windows()})
        self.assertTrue(view["dual"])
        self.assertEqual([s["duration"] for s in view["slots"]], [300, 10080])
        self.assertEqual([s["window"]["usedPercent"] for s in view["slots"]], [32, 58])

    def test_missing_plus_window_is_absent_not_zero_or_old_measurement(self):
        view = subscription_view({"planType": "plus", "windows": self.windows()[1:]})
        self.assertTrue(view["dual"])
        self.assertIsNone(view["slots"][0]["window"])
        self.assertEqual(view["slots"][1]["window"]["usedPercent"], 58)

    def test_pro_uses_only_weekly_window_even_if_short_window_is_returned(self):
        view = subscription_view({"planType": "pro", "windows": self.windows()})
        self.assertFalse(view["dual"])
        self.assertEqual([s["duration"] for s in view["slots"]], [10080])

    def test_unknown_subscription_uses_observed_windows_without_guessing_plan(self):
        view = subscription_view({"windows": self.windows()})
        self.assertTrue(view["dual"])
        self.assertIsNone(view["plan"])
        self.assertFalse(subscription_view({})["dual"])

    def test_profile_choice_is_independent_of_automatically_detected_plan(self):
        for profile in PROFILES:
            self.assertEqual(profile_size(profile), PROFILES[profile][:2])
            self.assertGreater(profile_size(profile, True)[1], profile_size(profile)[1])
            self.assertEqual(profile_size(profile, True)[0], profile_size(profile)[0])
        self.assertEqual(hit_target("mini", 60, 30, 290, 314), "menu")

    def test_plan_normalization(self):
        self.assertEqual(normalize_plan(" Plus "), "plus")
        self.assertEqual(normalize_plan("pro_20x"), "pro")
        self.assertEqual(normalize_plan("prolite"), "pro")
        self.assertIsNone(normalize_plan(None))

    def test_runtime_cannot_start_model_turns_or_purchase_anything(self):
        client = AccountClient.__new__(AccountClient)
        for method in (
            "turn/start",
            "thread/start",
            "account/rateLimitResetCredit/consume",
            "account/sendAddCreditsNudgeEmail",
            "account/logout",
        ):
            with self.assertRaises(ValueError):
                client.request(method)

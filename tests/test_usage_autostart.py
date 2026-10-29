import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from usage_autostart import LaunchState
except ImportError:
    LaunchState = None


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(LaunchState, "GPT startup handling is not implemented")
        self.state = LaunchState()

    def test_waits_for_gpt_and_launches_once(self):
        self.assertFalse(self.state.step(set(), False, 0))
        self.assertTrue(self.state.step({42}, False, 2))
        self.assertFalse(self.state.step({42}, False, 4))

    def test_does_not_duplicate_existing_widget(self):
        self.assertFalse(self.state.step({42}, True, 0))
        self.assertFalse(self.state.step({42}, False, 2))

    def test_manual_close_is_respected_until_gpt_restarts(self):
        self.assertTrue(self.state.step({42}, False, 0))
        self.assertFalse(self.state.step({42}, False, 2))
        self.assertFalse(self.state.step(set(), False, 4))
        self.assertTrue(self.state.step({80}, False, 6))

    def test_main_process_restart_is_detected_without_an_empty_poll(self):
        self.assertTrue(self.state.step({42}, False, 0))
        self.assertTrue(self.state.step({80}, False, 3))

    def test_failed_launch_is_retried_with_backoff(self):
        self.assertTrue(self.state.step({42}, False, 0))
        self.state.launch_failed(0)
        self.assertFalse(self.state.step({42}, False, 10))
        self.assertTrue(self.state.step({42}, False, 60))


if __name__ == "__main__":
    unittest.main()

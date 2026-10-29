from datetime import datetime, timezone
import json
from pathlib import Path
import time
import unittest
import uuid
from usage_activity import ActivityMonitor, visual_mode


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / "artifacts" / f"activity-{uuid.uuid4().hex}"
        self.root.mkdir(parents=True)
        self.path = self.root / "turn.jsonl"
        self.monitor = ActivityMonitor(self.root)
        self.now = time.time()

    def append(self, kind, delta=0, finish=True, path=None):
        value = {
            "timestamp": datetime.fromtimestamp(self.now + delta, timezone.utc).isoformat(),
            "type": "event_msg",
            "payload": {"type": kind},
        }
        with (path or self.path).open("ab") as stream:
            stream.write(json.dumps(value).encode() + (b"\n" if finish else b""))

    def test_start_and_complete_are_immediate_without_quota_change(self):
        self.append("task_started")
        self.assertTrue(self.monitor.poll(self.now)["active"])
        self.append("task_complete", 1)
        self.assertFalse(self.monitor.poll(self.now + 1)["active"])

    def test_interrupted_turn_stops_and_incomplete_line_is_not_lost(self):
        self.append("task_started", finish=False)
        self.assertFalse(self.monitor.poll(self.now)["active"])
        with self.path.open("ab") as stream:
            stream.write(b"\n")
        self.assertTrue(self.monitor.poll(self.now + 1)["active"])
        self.append("turn_aborted", 2)
        self.assertFalse(self.monitor.poll(self.now + 2)["active"])

    def test_one_finished_chat_does_not_stop_other_active_chat(self):
        second = self.root / "second.jsonl"
        self.append("task_started")
        self.append("task_started", path=second)
        self.assertEqual(self.monitor.poll(self.now)["count"], 2)
        self.append("task_complete", 1)
        self.assertEqual(self.monitor.poll(self.now + 1)["count"], 1)

    def test_orphaned_start_and_partial_token_pulse_expire(self):
        self.append("task_started")
        self.assertFalse(self.monitor.poll(self.now + 601)["active"])
        self.append("task_complete", 602)
        self.append("token_count", 603)
        self.assertTrue(self.monitor.poll(self.now + 604)["active"])
        self.assertFalse(self.monitor.poll(self.now + 612)["active"])

    def test_historical_high_rate_does_not_keep_fire_alive(self):
        self.assertEqual(visual_mode("lava", {"active": False}, 0, self.now), "still")
        active = {"active": True, "checkedAt": self.now}
        self.assertEqual(visual_mode("lava", active, 0, self.now), "lava")
        self.assertEqual(visual_mode("lava", active, 0, self.now + 6), "still")
        self.assertEqual(visual_mode("lava", active, 0, self.now, valid=False), "still")

    def test_confirmed_quota_pulse_is_short_and_does_not_override_stale(self):
        self.assertEqual(visual_mode("learning", {}, self.now + 8, self.now), "fire")
        self.assertEqual(visual_mode("learning", {}, self.now + 8, self.now + 9), "still")
        self.assertEqual(visual_mode("stale", {}, self.now + 8, self.now), "still")

from concurrent.futures import Future
import queue
import threading
import time
from types import SimpleNamespace
import unittest
from usage_transport import fetch_loop


class TransportTests(unittest.TestCase):
    def run_transport(self, client):
        stop, refresh, updates = threading.Event(), threading.Event(), queue.Queue()
        client.proc = SimpleNamespace(poll=lambda: None)
        client.take_notifications = lambda: []
        client.close = lambda: None
        client.abandon = lambda _: None

        def choose(result):
            return ({"limitId": "codex"}, result["window"], [result["window"]])

        worker = threading.Thread(
            target=fetch_loop, args=(stop, refresh, updates, lambda: client, choose, lambda _: None), daemon=True
        )
        worker.start()
        self.addCleanup(lambda: (stop.set(), worker.join(2)))
        return stop, refresh, updates

    def quota(self, updates):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            result = updates.get(timeout=2)
            if result["kind"] == "quota":
                return result
        self.fail("No quota delivered")

    def test_slow_optional_stats_do_not_delay_first_or_manual_quota(self):
        slow = Future()
        client = SimpleNamespace(call=lambda *a, **kw: {"window": {"usedPercent": 20}}, request=lambda *a: (9, slow))
        stop, refresh, updates = self.run_transport(client)
        self.assertTrue(self.quota(updates)["ok"])
        self.assertFalse(slow.done())
        refresh.set()
        self.assertTrue(self.quota(updates)["ok"])
        self.assertFalse(slow.done())

    def test_click_during_request_is_not_cleared_at_end(self):
        entered, release = threading.Event(), threading.Event()
        calls = []

        def call(*a, **kw):
            calls.append(1)
            if len(calls) == 1:
                entered.set()
                release.wait(1)
            return {"window": {"usedPercent": 20}}

        client = SimpleNamespace(call=call, request=lambda *a: (9, Future()))
        stop, refresh, updates = self.run_transport(client)
        self.assertTrue(entered.wait(1))
        refresh.set()
        release.set()
        self.quota(updates)
        self.quota(updates)
        self.assertEqual(len(calls), 2)

    def test_optional_stats_error_does_not_replace_good_quota(self):
        failed = Future()
        failed.set_exception(RuntimeError("Unavailable"))
        client = SimpleNamespace(call=lambda *a, **kw: {"window": {"usedPercent": 20}}, request=lambda *a: (9, failed))
        stop, refresh, updates = self.run_transport(client)
        self.assertTrue(self.quota(updates)["ok"])

    def test_optional_request_failure_does_not_turn_quota_into_error(self):
        def fail(*args):
            raise OSError("Optional request unavailable")

        client = SimpleNamespace(call=lambda *a, **kw: {"window": {"usedPercent": 20}}, request=fail)
        stop, refresh, updates = self.run_transport(client)
        self.assertTrue(self.quota(updates)["ok"])

    def test_plan_detection_is_independent_of_stalled_token_statistics(self):
        plan = Future()
        plan.set_result({"account": {"planType": "plus", "email": "private@example.invalid"}})
        stats = Future()

        def request(method, *args):
            return (10, plan) if method == "account/read" else (11, stats)

        client = SimpleNamespace(call=lambda *a, **kw: {"window": {"usedPercent": 20}}, request=request)
        stop, refresh, updates = self.run_transport(client)
        self.assertTrue(self.quota(updates)["ok"])
        message = updates.get(timeout=2)
        while message["kind"] != "plan":
            message = updates.get(timeout=2)
        self.assertEqual(message, {"kind": "plan", "planType": "plus"})
        self.assertNotIn("email", str(message))
        self.assertFalse(stats.done())

    def test_plan_from_rate_limit_response_is_immediately_available(self):
        client = SimpleNamespace(
            call=lambda *a, **kw: {"window": {"usedPercent": 20}, "planType": "pro"}, request=lambda *a: (10, Future())
        )
        stop, refresh, updates = self.run_transport(client)
        self.assertEqual(self.quota(updates)["planType"], "pro")
        refresh.set()
        self.assertTrue(self.quota(updates)["ok"])
        refresh.set()
        self.assertTrue(self.quota(updates)["ok"])

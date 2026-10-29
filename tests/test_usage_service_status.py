import io
import json
from http.client import BadStatusLine, IncompleteRead
import unittest
import urllib.request
from types import SimpleNamespace
from unittest.mock import Mock, patch

import usage_service_status as service


def summary():
    return {
        "status": {"indicator": "major"},
        "components": [
            {"id": key, "name": name, "status": "operational"} for key, name in service.CHATGPT_COMPONENTS.items()
        ],
    }


class ParserTests(unittest.TestCase):
    def test_flattened_components_ignore_global_api_and_codex_outage(self):
        value = summary()
        value["components"].extend(
            [
                {"id": "01JSM5RTJWHRWDTS6Q604VEW3B", "name": "Login", "status": "major_outage"},
                {"id": "01KMKFAMWKQ81YWSE1Z18R6VHR", "name": "Codex in ChatGPT Desktop", "status": "major_outage"},
            ]
        )
        result = service.parse_summary(value)
        self.assertEqual(result["state"], "operational")
        self.assertEqual(result["componentCount"], 8)
        self.assertEqual(result["affectedCount"], 0)

    def test_component_severity_and_optional_chatgpt_work(self):
        for upstream, expected in (
            ("operational", "operational"),
            ("degraded_performance", "degraded"),
            ("partial_outage", "degraded"),
            ("under_maintenance", "degraded"),
            ("major_outage", "outage"),
        ):
            with self.subTest(upstream=upstream):
                value = summary()
                value["components"][0]["status"] = upstream
                self.assertEqual(service.parse_summary(value)["state"], expected)
        value = summary()
        work_id = next(iter(service.OPTIONAL_COMPONENTS))
        value["components"].append({"id": work_id, "name": "ChatGPT Work", "status": "major_outage"})
        self.assertEqual(service.parse_summary(value)["state"], "outage")

    def test_missing_component_duplicate_id_or_unknown_status_is_unknown(self):
        missing, duplicate, unknown, malformed = summary(), summary(), summary(), summary()
        missing["components"].pop()
        duplicate["components"].append(dict(duplicate["components"][0]))
        unknown["components"][0]["status"] = "future_status"
        malformed["components"][0]["status"] = []
        for value in (missing, duplicate, unknown, malformed, None, [], {}, {"components": "invalid"}):
            with self.subTest(value=value):
                self.assertEqual(service.parse_summary(value)["state"], "unknown")

    def test_future_chatgpt_group_adds_features_but_not_api_or_codex(self):
        value = summary()
        value["components"].extend(
            [
                {"id": "group", "name": "ChatGPT", "group": True, "status": "major_outage"},
                {"id": "new", "name": "New ChatGPT feature", "group_id": "group", "status": "partial_outage"},
                {"id": "codex", "name": "Codex", "group_id": "group", "status": "major_outage"},
                {"id": "api", "name": "Compliance API", "group_id": "group", "status": "major_outage"},
                {"id": "other", "name": "Other", "group_id": [], "status": "major_outage"},
            ]
        )
        result = service.parse_summary(value)
        self.assertEqual(result["state"], "degraded")
        self.assertEqual(result["componentCount"], 9)

    def test_only_active_incidents_linked_to_chatgpt_affect_status(self):
        chatgpt_id = next(iter(service.CHATGPT_COMPONENTS))
        value = summary()
        value["incidents"] = [
            {"status": "resolved", "impact": "critical", "components": [{"id": chatgpt_id}]},
            {"status": "investigating", "impact": "critical", "component_ids": ["api"]},
            {"status": "investigating", "impact": "critical", "name": "Unscoped incident"},
            {"status": [], "impact": "critical", "components": [{"id": chatgpt_id}]},
        ]
        self.assertEqual(service.parse_summary(value)["state"], "operational")
        value["incidents"].append(
            {"status": "monitoring", "impact": "minor", "components": [{"id": chatgpt_id}], "name": "Private text"}
        )
        result = service.parse_summary(value)
        self.assertEqual(result["state"], "degraded")
        self.assertEqual(result["incidentCount"], 1)
        self.assertNotIn("Private text", str(result))
        value["incidents"].append({"status": "identified", "impact": "critical", "component_ids": [chatgpt_id]})
        self.assertEqual(service.parse_summary(value)["state"], "outage")
        value["incidents"] = {}
        self.assertEqual(service.parse_summary(value)["state"], "unknown")

    def test_stale_or_unmeasured_presentation_never_claims_availability(self):
        status = {**service.initial_state(), "state": "operational", "lastSuccessAt": 1000, "checkedAt": 1000}
        self.assertEqual(service.presentation(status, 1900)["state"], "operational")
        self.assertEqual(service.presentation(status, 1901)["state"], "unknown")
        self.assertEqual(service.presentation(service.initial_state(), 1900)["state"], "unknown")
        status.update(state="outage", lastSuccessAt=None, detail="untrusted remote text")
        self.assertEqual(service.presentation(status, 1900)["state"], "unknown")
        self.assertNotIn("untrusted", str(service.presentation(status, 1900)))
        status["state"] = []
        self.assertEqual(service.presentation(status, 1900)["state"], "unknown")

    def test_group_incident_with_only_excluded_component_links_is_ignored(self):
        chatgpt_id = next(iter(service.CHATGPT_COMPONENTS))
        for excluded in ("codex", "api", "unknown-component"):
            with self.subTest(excluded=excluded):
                value = summary()
                value["components"].extend(
                    [
                        {"id": "group", "name": "ChatGPT", "group": True, "status": "major_outage"},
                        {"id": "codex", "name": "Codex", "group_id": "group", "status": "major_outage"},
                        {"id": "api", "name": "Compliance API", "group_id": "group", "status": "major_outage"},
                    ]
                )
                incident = {"status": "investigating", "impact": "critical", "component_ids": ["group", excluded]}
                value["incidents"] = [incident]
                result = service.parse_summary(value)
                self.assertEqual(result["state"], "operational")
                self.assertEqual(result["incidentCount"], 0)
                incident["component_ids"].append(chatgpt_id)
                self.assertEqual(service.parse_summary(value)["state"], "outage")
                incident["component_ids"] = ["group"]
                self.assertEqual(service.parse_summary(value)["state"], "outage")


class Response(io.BytesIO):
    def __init__(self, data, url=service.SUMMARY_URL, headers=None, code=200):
        super().__init__(data)
        self.url, self.headers, self.code = url, headers or {}, code
        self.read_sizes = []

    def geturl(self):
        return self.url

    def getcode(self):
        return self.code

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class NetworkTests(unittest.TestCase):
    def test_fixed_public_request_has_bounded_read_timeout_and_no_credentials(self):
        response = Response(json.dumps(summary()).encode())
        opener = Mock()
        opener.open.return_value = response
        self.assertEqual(service.fetch_summary(opener), summary())
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, service.SUMMARY_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 8)
        self.assertEqual(response.read_sizes, [service.MAX_BYTES + 1])
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertNotIn("authorization", headers)
        self.assertNotIn("cookie", headers)
        self.assertEqual(headers["accept-encoding"], "identity")

    def test_oversized_body_or_content_length_is_rejected_before_parsing(self):
        for response in (
            Response(b"x" * (service.MAX_BYTES + 1)),
            Response(b"{}", headers={"Content-Length": str(service.MAX_BYTES + 1)}),
        ):
            with self.subTest(headers=response.headers), self.assertRaises(service.StatusDataError):
                service.fetch_summary(SimpleNamespace(open=lambda *args, **kwargs: response))

    def test_invalid_json_encoding_or_final_origin_is_rejected(self):
        for response in (
            Response(b"not json"),
            Response(b"\xff"),
            Response(b"{}", url="https://example.invalid/status"),
            Response(b"{}", url="http://status.openai.com/status"),
            Response(b"{}", code=204),
        ):
            with self.subTest(url=response.url, code=response.code), self.assertRaises(service.StatusDataError):
                service.fetch_summary(SimpleNamespace(open=lambda *args, **kwargs: response))

    def test_nested_non_object_response_never_becomes_a_known_status(self):
        response = Response(b"[" * 3000 + b"]" * 3000)
        try:
            payload = service.fetch_summary(SimpleNamespace(open=lambda *args, **kwargs: response))
        except service.StatusDataError:
            # Older Python parsers reject this depth; newer ones can decode it.
            return
        self.assertEqual(service.parse_summary(payload)["state"], "unknown")

    def test_redirect_rejects_other_hosts_http_userinfo_and_nonstandard_ports(self):
        handler = service.OfficialRedirectHandler()
        request = urllib.request.Request(service.SUMMARY_URL)
        for url in (
            "https://example.invalid/status",
            "http://status.openai.com/status",
            "https://status.openai.com.evil.invalid/status",
            "https://user:pass@status.openai.com/status",
            "https://status.openai.com:8443/status",
        ):
            with self.subTest(url=url), self.assertRaises(service.StatusDataError):
                handler.redirect_request(request, None, 302, "Found", {}, url)
        redirected = handler.redirect_request(request, None, 302, "Found", {}, service.SUMMARY_URL + "?refresh=1")
        self.assertEqual(redirected.host, "status.openai.com")

    def test_default_opener_disables_environment_proxy_credentials(self):
        opener = Mock()
        opener.open.return_value = Response(json.dumps(summary()).encode())
        with patch.object(service.urllib.request, "build_opener", return_value=opener) as build:
            service.fetch_summary()
        handlers = build.call_args.args
        proxy = next(handler for handler in handlers if isinstance(handler, urllib.request.ProxyHandler))
        self.assertEqual(proxy.proxies, {})
        self.assertTrue(any(isinstance(handler, service.OfficialRedirectHandler) for handler in handlers))


class LoopTests(unittest.TestCase):
    def run_loop(self, outcomes, wall_clock=None, cancel_wait=False):
        clock = SimpleNamespace(now=0)
        messages, calls, waits = [], [], []
        stop = SimpleNamespace(stopped=False)
        stop.is_set = lambda: stop.stopped

        def wait(seconds):
            waits.append(seconds)
            clock.now += seconds
            stop.stopped = cancel_wait
            return stop.stopped

        def put(message):
            messages.append(message)
            if len(messages) == len(outcomes):
                stop.stopped = True

        def fetch():
            calls.append(clock.now)
            outcome = outcomes[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        stop.wait = wait
        service.status_loop(
            stop,
            SimpleNamespace(put=put),
            fetch=fetch,
            clock=lambda: clock.now,
            wall_clock=wall_clock or (lambda: 10000 + clock.now),
        )
        return messages, calls, waits

    def test_immediate_poll_success_cadence_and_failure_backoff(self):
        messages, calls, waits = self.run_loop([summary(), OSError("private error"), TimeoutError(), summary()])
        self.assertEqual(calls, [0, 300, 900, 1800])
        self.assertEqual(waits, [300, 600, 900])
        self.assertEqual(
            [message["state"] for message in messages], ["operational", "unknown", "unknown", "operational"]
        )
        self.assertEqual([message["lastSuccessAt"] for message in messages], [10000, 10000, 10000, 11800])
        self.assertTrue(all(message["kind"] == "service_status" for message in messages))
        self.assertNotIn("private error", str(messages))

    def test_schema_failure_backs_off_and_recovery_resets_backoff(self):
        messages, calls, waits = self.run_loop([{}, {}, summary(), ValueError(), summary()])
        self.assertEqual(calls, [0, 600, 1500, 1800, 2400])
        self.assertEqual(
            [message["state"] for message in messages], ["unknown", "unknown", "operational", "unknown", "operational"]
        )

    def test_wall_clock_changes_do_not_change_monotonic_poll_schedule(self):
        stamps = iter([20000, 10000, 40000])
        messages, calls, waits = self.run_loop([summary()] * 3, wall_clock=lambda: next(stamps))
        self.assertEqual(calls, [0, 300, 600])
        self.assertEqual([message["checkedAt"] for message in messages], [20000, 10000, 40000])

    def test_incomplete_or_invalid_http_response_emits_unknown_and_backs_off(self):
        messages, calls, waits = self.run_loop(
            [IncompleteRead(b"private partial response", 100), BadStatusLine("private status line"), summary()]
        )
        self.assertEqual(calls, [0, 600, 1500])
        self.assertEqual(waits, [600, 900])
        self.assertEqual([message["state"] for message in messages], ["unknown", "unknown", "operational"])
        self.assertEqual([message["lastSuccessAt"] for message in messages], [None, None, 11500])
        self.assertNotIn("private", str(messages))

    def test_stop_interrupts_wait_and_does_not_fetch_again(self):
        messages, calls, waits = self.run_loop([summary(), summary()], cancel_wait=True)
        self.assertEqual(calls, [0])
        self.assertEqual(waits, [300])


if __name__ == "__main__":
    unittest.main()

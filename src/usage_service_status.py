"""Public ChatGPT availability metadata; no account, cookies or model requests."""

import json
from http.client import HTTPException
import math
import ssl
import time
import urllib.parse
import urllib.request

SUMMARY_URL = "https://status.openai.com/api/v2/summary.json"
STATUS_URL = "https://status.openai.com/"
MAX_BYTES = 1024 * 1024
TIMEOUT = 8
POLL_SECONDS = 300
STALE_SECONDS = 900

# Verified against the official summary on 2026-10-29. Names alone are ambiguous:
# the flattened response also contains a different Login component for the API.
CHATGPT_COMPONENTS = {
    "01JMXBNJXGV1T5GT2M9XA83XNG": "Conversations",
    "01JMXBNJXG1S2D9V65P1ZZTD94": "Login",
    "01JMXBNJXGKKP51D4DEJ2HZJ8Q": "Search",
    "01JMXBNJXG1YMQPPCPCQX3MPA2": "File uploads",
    "01JMXBNJXGGT5SR5DB9J7GYY48": "Voice mode",
    "01JSFK5QX36ZRW0TW0ZV0ZYFXQ": "GPTs",
    "01JQ7EKW990MSPSWVXC7VPV2ZJ": "Image Generation",
    "01JSYVYQSWMJ9QG35XHP08BHA7": "Deep Research",
}
OPTIONAL_COMPONENTS = {"01KX45G1SH21AX5DT93D4HMF0P": "ChatGPT Work"}
COMPONENT_STATES = {
    "operational": "operational",
    "degraded_performance": "degraded",
    "partial_outage": "degraded",
    "major_outage": "outage",
    "under_maintenance": "degraded",
}
SEVERITY = {"operational": 0, "degraded": 1, "outage": 2}
ACTIVE_INCIDENTS = frozenset({"investigating", "identified", "monitoring", "in_progress", "verifying"})
LABELS = {
    "operational": "Сбоев ChatGPT не заявлено",
    "degraded": "Ограничения ChatGPT",
    "outage": "Крупный сбой ChatGPT",
    "unknown": "Статус ChatGPT неизвестен",
}
DETAILS = {
    "operational": "Официальный статус основных сервисов ChatGPT: работают штатно.",
    "degraded": "OpenAI сообщает об ограничениях в работе сервисов ChatGPT.",
    "outage": "OpenAI сообщает о серьёзном сбое сервисов ChatGPT.",
    "unknown": "Не удалось получить полный актуальный статус ChatGPT.",
}


class StatusDataError(ValueError):
    """An invalid, oversized or incorrectly redirected public status response."""


def initial_state():
    return {
        "kind": "service_status",
        "state": "unknown",
        "checkedAt": None,
        "lastSuccessAt": None,
        "detail": "Проверяем status.openai.com…",
        "componentCount": 0,
        "affectedCount": 0,
        "incidentCount": 0,
    }


def _parsed(state="unknown", component_count=0, affected_count=0, incident_count=0):
    return {
        "state": state,
        "detail": DETAILS[state],
        "componentCount": component_count,
        "affectedCount": affected_count,
        "incidentCount": incident_count,
    }


def parse_summary(payload):
    """Select known ChatGPT services, never the site's global/API/Codex status."""
    if not isinstance(payload, dict) or not isinstance(payload.get("components"), list):
        return _parsed()
    components = payload["components"]
    if len(components) > 5000:
        return _parsed()
    by_id = {}
    for component in components:
        if not isinstance(component, dict) or not isinstance(component.get("id"), str):
            continue
        component_id = component["id"]
        if component_id in by_id:
            return _parsed()
        by_id[component_id] = component
    if not CHATGPT_COMPONENTS.keys() <= by_id.keys():
        return _parsed()
    selected_ids = set(CHATGPT_COMPONENTS) | (OPTIONAL_COMPONENTS.keys() & by_id.keys())
    # Accept additional explicitly grouped ChatGPT features if grouping is restored.
    # Do not use a group's aggregate state: it could include a Codex-only outage.
    group_ids = {key for key, value in by_id.items() if value.get("name") == "ChatGPT" and value.get("group") is True}
    for key, component in by_id.items():
        name = component.get("name", "")
        if (
            isinstance(component.get("group_id"), str)
            and component["group_id"] in group_ids
            and isinstance(name, str)
            and "codex" not in name.casefold()
            and "api" not in name.casefold()
        ):
            selected_ids.add(key)
    states = [
        COMPONENT_STATES.get(by_id[key]["status"]) if isinstance(by_id[key].get("status"), str) else None
        for key in selected_ids
    ]
    if any(state is None for state in states):
        return _parsed()
    state = max(states, key=SEVERITY.__getitem__)
    affected = sum(value != "operational" for value in states)
    incidents = payload.get("incidents", [])
    if not isinstance(incidents, list) or len(incidents) > 5000:
        return _parsed()
    relevant_incidents = 0
    for incident in incidents:
        if (
            not isinstance(incident, dict)
            or not isinstance(incident.get("status"), str)
            or incident["status"] not in ACTIVE_INCIDENTS
        ):
            continue
        links = incident.get("components", [])
        ids = incident.get("component_ids", [])
        linked = {item for item in ids if isinstance(item, str)} if isinstance(ids, list) else set()
        if isinstance(links, list):
            linked.update(item["id"] for item in links if isinstance(item, dict) and isinstance(item.get("id"), str))
            linked.update(item for item in links if isinstance(item, str))
        selected_link = bool(linked & selected_ids)
        group_only_link = bool(linked & group_ids) and not (linked - selected_ids - group_ids)
        if not selected_link and not group_only_link:
            continue
        relevant_incidents += 1
        impact = "outage" if incident.get("impact") in ("major", "critical") else "degraded"
        state = max((state, impact), key=SEVERITY.__getitem__)
    return _parsed(state, len(selected_ids), affected, relevant_incidents)


def _official_url(url):
    try:
        value = urllib.parse.urlsplit(url)
        return (
            value.scheme == "https"
            and value.hostname == "status.openai.com"
            and value.port in (None, 443)
            and value.username is None
            and value.password is None
        )
    except (TypeError, ValueError):
        return False


class OfficialRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        if not _official_url(newurl):
            raise StatusDataError("Public status redirect rejected")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch_summary(opener=None):
    """Fetch at most one MiB from the fixed public HTTPS origin, without credentials."""
    if opener is None:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            OfficialRedirectHandler(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )
    request = urllib.request.Request(
        SUMMARY_URL,
        headers={"Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": "GPTOKEN service status"},
        method="GET",
    )
    with opener.open(request, timeout=TIMEOUT) as response:
        if not _official_url(response.geturl()) or response.getcode() != 200:
            raise StatusDataError("Unexpected public status response")
        length = response.headers.get("Content-Length")
        if length is not None:
            try:
                too_large = int(length) > MAX_BYTES
            except (TypeError, ValueError):
                too_large = False
            if too_large:
                raise StatusDataError("Public status response too large")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise StatusDataError("Public status response too large")
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise StatusDataError("Invalid public status JSON") from error


def presentation(status, now=None):
    """Return controlled UI text, discarding stale successful observations."""
    now = time.time() if now is None else now
    status = status if isinstance(status, dict) else initial_state()
    state = status.get("state", "unknown")
    if not isinstance(state, str) or state not in LABELS:
        state = "unknown"
    last_success = status.get("lastSuccessAt")
    valid_time = isinstance(last_success, (int, float)) and math.isfinite(last_success)
    stale = valid_time and now - last_success > STALE_SECONDS
    if not valid_time or stale:
        state = "unknown"
    detail = DETAILS[state]
    if stale:
        detail = "Данные старше 15 минут. Свежий статус доступен на status.openai.com."
    elif state == "unknown" and status.get("checkedAt") is None:
        detail = "Проверяем status.openai.com…"
    return {"state": state, "label": LABELS[state], "detail": detail}


def status_loop(stop, updates, *, fetch=None, clock=time.monotonic, wall_clock=time.time):
    """Poll immediately, every five minutes, or after bounded failure backoff."""
    fetch = fetch_summary if fetch is None else fetch
    next_poll, failures, last_success = clock(), 0, None
    while not stop.is_set():
        delay = next_poll - clock()
        if delay > 0:
            if stop.wait(delay):
                return
            continue
        try:
            result = parse_summary(fetch())
        except (OSError, ValueError, TimeoutError, HTTPException):
            result = _parsed()
        checked_at = wall_clock()
        if stop.is_set():
            return
        if result["state"] != "unknown":
            failures, last_success, interval = 0, checked_at, POLL_SECONDS
        else:
            failures += 1
            interval = 600 if failures == 1 else 900
        updates.put({"kind": "service_status", **result, "checkedAt": checked_at, "lastSuccessAt": last_success})
        next_poll = clock() + interval

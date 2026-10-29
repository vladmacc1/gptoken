"""Local observation history, sessions, budgets and notification decisions."""

from datetime import datetime, timedelta, timezone
import math
from usage_pace import PaceHistory

MOSCOW = timezone(timedelta(hours=3))


def local_day(timestamp):
    return datetime.fromtimestamp(timestamp, MOSCOW).date().isoformat()


def day_end(timestamp):
    value = datetime.fromtimestamp(timestamp, MOSCOW)
    return (value.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()


def eligible_seconds(start, end, workdays=False):
    if end is None or end <= start:
        return 0.0
    total, cursor = 0.0, start
    # Rate-limit windows are finite. Cap malformed server horizons at two years.
    for _ in range(733):
        if cursor >= end:
            break
        stop = min(end, day_end(cursor))
        if not workdays or datetime.fromtimestamp(cursor, MOSCOW).weekday() < 5:
            total += stop - cursor
        cursor = stop
    return total


def forecast(remaining, rate, now, reset, stale=False):
    state, seconds, risk = "learning", None, False
    if stale:
        state = "stale"
    elif reset is None:
        state = "unknown"
    elif reset <= now:
        state = "reset"
    elif remaining <= 0:
        state, seconds, risk = "empty", 0.0, True
    elif rate is not None and rate > 0:
        seconds = remaining / rate * 3600
        risk = seconds < reset - now
        state = "risk" if risk else "safe"
    elif rate == 0:
        state = "idle"
    return {"state": state, "seconds": seconds, "risk": risk}


def duration_text(seconds):
    minutes = max(0, int(seconds // 60))
    if minutes < 1:
        return "<1 мин"
    days, rest = divmod(minutes, 1440)
    hours, minutes = divmod(rest, 60)
    if days:
        return f"{days} дн {hours} ч"
    return f"{hours} ч {minutes} мин" if hours else f"{minutes} мин"


def window_name(window):
    mins = window.get("windowDurationMins")
    if mins == 10080:
        return "Неделя"
    if isinstance(mins, (int, float)) and mins > 0:
        return f"{mins / 60:g} ч" if mins >= 60 else f"{mins:g} мин"
    return "Лимит"


class UsageBook:
    def __init__(self, saved=None):
        saved = saved if isinstance(saved, dict) else {}
        self.windows = saved.get("windows", {}) if isinstance(saved.get("windows"), dict) else {}
        self.active = [key for key in saved.get("active", []) if key in self.windows]
        self.workdays = bool(saved.get("workdays", False))
        self.session = saved.get("session") if isinstance(saved.get("session"), dict) else None
        self.paces = {}
        for key, entry in list(self.windows.items()):
            if not isinstance(entry, dict) or not isinstance(entry.get("samples"), list) or "window" not in entry:
                self.windows.pop(key)
                continue
            self.paces[key] = PaceHistory(entry.get("pace"))
        self.active = [key for key in self.active if key in self.windows]

    def ingest(self, data):
        now = data["updatedAt"]
        active = []
        for index, window in enumerate(data.get("windows") or [data.get("window")]):
            if not isinstance(window, dict):
                continue
            used, reset = window.get("usedPercent"), window.get("resetsAt")
            if not isinstance(used, (int, float)) or not math.isfinite(used) or not 0 <= used <= 100:
                continue
            if reset is not None and (not isinstance(reset, (int, float)) or not math.isfinite(reset)):
                continue
            bucket = data.get("bucket", "codex")
            key = f"{bucket}:{window.get('windowDurationMins')}"
            if key in active:
                key += f":{index}"
            active.append(key)
            entry = self.windows.setdefault(key, {"samples": [], "window": window, "plan": None})
            samples = entry["samples"]
            if samples and now <= samples[-1][0]:
                continue
            if self.session is None:
                self.reset_session(now)
            self.record_session(key, now, used, reset)
            samples.append([now, used, reset])
            entry["samples"] = [s for s in samples if s[0] >= now - 7 * 86400][-60000:]
            entry["window"] = dict(window)
            pace = self.paces.setdefault(key, PaceHistory())
            pace.add(now, used, reset, window.get("windowDurationMins"), bucket)
            entry["pace"] = pace.to_json()
            plan = entry.get("plan")
            if (
                not plan
                or plan["day"] != local_day(now)
                or plan["reset"] != reset
                or plan.get("workdays") != self.workdays
            ):
                entry["plan"] = {
                    "at": now,
                    "remaining": 100 - used,
                    "day": local_day(now),
                    "reset": reset,
                    "workdays": self.workdays,
                }
        self.active = active

    def evaluate(self, key, now, failed=False):
        entry = self.windows[key]
        w = entry["window"]
        remaining = 100 - w["usedPercent"]
        pace = self.paces[key].evaluate(now, remaining, w.get("resetsAt"), failed)
        prediction = forecast(remaining, pace["rate"], now, w.get("resetsAt"), pace["mode"] == "stale")
        return {"remaining": remaining, "pace": pace, "forecast": prediction, "window": w}

    def select(self, now, requested="auto", failed=False):
        if requested in self.active:
            return requested
        if not self.active:
            return None
        states = {key: self.evaluate(key, now, failed) for key in self.active}
        risks = [key for key, s in states.items() if s["forecast"]["risk"]]
        if risks:
            return min(risks, key=lambda k: states[k]["forecast"]["seconds"])
        return min(self.active, key=lambda k: states[k]["remaining"])

    def budget(self, key, now):
        entry = self.windows[key]
        plan = entry.get("plan")
        if not plan or plan["day"] != local_day(now) or not plan["reset"] or plan["reset"] <= now:
            return None
        total = eligible_seconds(plan["at"], plan["reset"], self.workdays)
        today = eligible_seconds(plan["at"], min(day_end(plan["at"]), plan["reset"]), self.workdays)
        elapsed = eligible_seconds(plan["at"], min(now, plan["reset"]), self.workdays)
        remaining = 100 - entry["window"]["usedPercent"]
        allocation = plan["remaining"] * today / total if total else 0
        expected = plan["remaining"] * (1 - elapsed / total) if total else plan["remaining"]
        spent = max(0, plan["remaining"] - remaining)
        return {
            "allocation": allocation,
            "available": max(0, min(remaining, allocation - spent)),
            "expectedRemaining": expected,
            "ahead": expected - remaining,
            "spent": spent,
        }

    def set_workdays(self, enabled, now):
        self.workdays = bool(enabled)
        for entry in self.windows.values():
            w = entry["window"]
            entry["plan"] = {
                "at": now,
                "remaining": 100 - w["usedPercent"],
                "day": local_day(now),
                "reset": w.get("resetsAt"),
                "workdays": self.workdays,
            }

    def reset_session(self, now):
        self.session = {"running": True, "since": now, "elapsed": 0, "started": now, "limits": {}}

    def pause_session(self, now):
        if self.session and self.session["running"]:
            self.session["elapsed"] += max(0, now - self.session["since"])
            self.session["running"] = False
            for value in self.session["limits"].values():
                value["anchor"] = None

    def resume_session(self, now):
        if self.session is None:
            self.reset_session(now)
        if not self.session["running"]:
            self.session["running"], self.session["since"] = True, now

    def record_session(self, key, now, used, reset):
        if not self.session or not self.session["running"]:
            return
        value = self.session["limits"].setdefault(key, {"spent": 0.0, "anchor": None, "partial": False})
        prev = value["anchor"]
        if prev:
            if prev[2] != reset:
                value["spent"] += used
                value["partial"] = True
            elif used >= prev[1]:
                value["spent"] += used - prev[1]
            else:
                value["partial"] = True
        value["anchor"] = [now, used, reset]

    def session_summary(self, key, now):
        s = self.session or {"running": False, "elapsed": 0, "since": now, "limits": {}}
        value = s["limits"].get(key, {"spent": 0, "partial": False, "anchor": None})
        return {
            "running": s["running"],
            "spent": value["spent"],
            "partial": value["partial"],
            "seconds": s["elapsed"] + (max(0, now - s["since"]) if s["running"] else 0),
            "measured": value["anchor"] is not None,
        }

    def chart_segments(self, key, now, period):
        segments = []
        previous = None
        for sample in self.windows[key]["samples"]:
            if sample[0] < now - period or sample[0] > now:
                continue
            if previous is None or sample[0] - previous[0] > 300 or sample[2] != previous[2] or sample[1] < previous[1]:
                segments.append([])
            segments[-1].append([sample[0], 100 - sample[1]])
            previous = sample
        return segments

    def to_json(self):
        return {
            "version": 1,
            "windows": self.windows,
            "active": self.active,
            "session": self.session,
            "workdays": self.workdays,
        }


class AlertGate:
    def __init__(self, saved=None):
        saved = saved if isinstance(saved, dict) else {}
        self.last = saved.get("last", 0)
        self.previous = saved.get("previous", {})

    def check(self, book, now, enabled=True, cooldown=900, failed=False):
        events = []
        for key in book.active:
            state = book.evaluate(key, now, failed)
            if state["pace"]["mode"] == "stale":
                continue
            entry = book.windows[key]
            reset = state["window"].get("resetsAt")
            prev = self.previous.get(key)
            candidates = [s for s in entry["samples"] if now - 600 <= s[0] <= now and s[2] == reset]
            rapid = (
                len(candidates) >= 2
                and candidates[-1][0] - candidates[0][0] >= 120
                and candidates[-1][1] - candidates[0][1] >= 5
            )
            current = {
                "reset": reset,
                "remaining": state["remaining"],
                "risk": state["forecast"]["risk"],
                "rapid": rapid,
            }
            if prev:
                if reset != prev["reset"] and current["remaining"] > prev["remaining"]:
                    events.append(
                        {"kind": "reset", "text": f"{window_name(state['window'])}: лимит обновился", "priority": 3}
                    )
                elif current["remaining"] == 0 and prev["remaining"] > 0:
                    events.append(
                        {"kind": "empty", "text": f"{window_name(state['window'])}: лимит исчерпан", "priority": 2}
                    )
                elif rapid and not prev["rapid"]:
                    events.append({"kind": "rapid", "text": "За последние 10 мин ушло ≥5 п.п. лимита", "priority": 1})
                elif current["risk"] and not prev["risk"]:
                    events.append(
                        {"kind": "risk", "text": "При текущем темпе лимит закончится до сброса", "priority": 0}
                    )
            self.previous[key] = current
        if enabled and events and now - self.last >= cooldown:
            self.last = now
            return max(events, key=lambda e: e["priority"])
        return None

    def to_json(self):
        return {"last": self.last, "previous": self.previous}

"""Read only local lifecycle markers. Never retain messages or send telemetry."""

from datetime import datetime
import json
import os
from pathlib import Path
import time


class ActivityMonitor:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions"
        self.files = {}
        self.last_discovery = -100
        self.available = False

    def poll(self, now=None):
        now = time.time() if now is None else now
        if now - self.last_discovery >= 2:
            self.last_discovery = now
            self.available = self.root.is_dir()
            try:
                for directory, _, names in os.walk(self.root):
                    for name in names:
                        if not name.endswith(".jsonl"):
                            continue
                        path = Path(directory) / name
                        if path not in self.files and now - path.stat().st_mtime < 7200:
                            self.files[path] = {"offset": 0, "buffer": b"", "active": False, "at": 0}
            except OSError:
                self.available = False
        for path, state in list(self.files.items()):
            try:
                stat = path.stat()
                if now - stat.st_mtime > 7200:
                    self.files.pop(path)
                    continue
                if stat.st_size < state["offset"]:
                    state.update(offset=0, buffer=b"", active=False, at=0)
                if stat.st_size == state["offset"]:
                    continue
                with path.open("rb") as stream:
                    previous_offset = state["offset"]
                    start = max(state["offset"], stat.st_size - 1024 * 1024)
                    stream.seek(start)
                    raw = stream.read(1024 * 1024)
                    state["offset"] = stream.tell()
                if start > previous_offset:
                    state["buffer"] = b""
                # An initial tail can start inside a JSON record; invalid lines are ignored.
                lines = (state["buffer"] + raw).split(b"\n")
                state["buffer"] = lines.pop()
                for line in lines:
                    if b'"event_msg"' not in line:
                        continue
                    try:
                        record = json.loads(line)
                        payload = record.get("payload") or {}
                        kind = payload.get("type")
                        if record.get("type") != "event_msg" or kind not in (
                            "task_started",
                            "task_complete",
                            "turn_aborted",
                            "token_count",
                        ):
                            continue
                        at = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00")).timestamp()
                    except (ValueError, TypeError, KeyError, AttributeError):
                        continue
                    state["at"] = at
                    if kind == "task_started":
                        state["active"] = True
                    elif kind in ("task_complete", "turn_aborted"):
                        state["active"] = False
                    elif not state["active"]:
                        # A missing start marker must not leave an indefinite active state.
                        state["pulse"] = at
                    # A completed/aborted turn also cancels any partial token pulse.
                    if kind in ("task_complete", "turn_aborted"):
                        state["pulse"] = 0
            except OSError:
                self.files.pop(path, None)
        active = sum(
            1
            for state in self.files.values()
            if (state["active"] and now - state["at"] < 600) or now - state.get("pulse", 0) < 8
        )
        return {
            "active": bool(active),
            "count": active,
            "available": self.available,
            "source": "local-lifecycle",
            "checkedAt": now,
        }


def activity_loop(stop, updates, monitor=None):
    monitor = monitor or ActivityMonitor()
    while not stop.is_set():
        try:
            updates.put({"kind": "activity", **monitor.poll()})
        except (OSError, ValueError):
            updates.put({"kind": "activity", "active": False, "available": False, "checkedAt": time.time()})
        stop.wait(1)


def visual_mode(pace_mode, activity, quota_pulse_until, now, valid=True):
    if not valid or pace_mode in ("stale", "reset", "empty", "unknown"):
        return "still"
    if activity.get("active") and now - activity.get("checkedAt", 0) < 5:
        return "lava" if pace_mode == "lava" else "fire"
    return "fire" if now < quota_pulse_until else "still"

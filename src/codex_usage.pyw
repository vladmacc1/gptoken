"""Local, read-only Codex account usage indicator. No model requests are sent."""

import argparse
import sys
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import queue
import threading
import time

from app_runtime import data_directory, RESOURCE_DIR, VERSION, Signals, request_shutdown, write_json
from usage_discovery import find_codex

BASE = data_directory()
ASSETS = RESOURCE_DIR / "assets"
PUBLIC_RELEASE = True
MONITOR_ENABLED = threading.Event()
STARTUP_ISSUE = None


def SET_ACTIVITY(enabled):
    MONITOR_ENABLED.set() if enabled else MONITOR_ENABLED.clear()


CONFIG = BASE / "position.json"
STATUS = BASE / "status.json"
STOP = threading.Event()
REFRESH = threading.Event()
UPDATES = queue.Queue()
USER32 = ctypes.windll.user32


def save_json(path, value):
    try:
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
    except OSError:
        pass


from usage_transport import AccountClient, fetch_loop as transport_loop
from usage_activity import ActivityMonitor

ACTIVITY = threading.Event()


def watch_activity():
    monitor = None
    while not STOP.is_set():
        if not MONITOR_ENABLED.is_set():
            monitor = None
            ACTIVITY.clear()
            UPDATES.put({"kind": "activity", "active": False, "available": False, "checkedAt": time.time()})
            STOP.wait(1)
            continue
        try:
            monitor = monitor or ActivityMonitor()
            state = monitor.poll()
            ACTIVITY.set() if state["active"] else ACTIVITY.clear()
            UPDATES.put({"kind": "activity", **state})
        except (OSError, ValueError):
            ACTIVITY.clear()
            UPDATES.put({"kind": "activity", "active": False, "available": False, "checkedAt": time.time()})
        STOP.wait(1)


def choose_bucket(result):
    buckets = result.get("rateLimitsByLimitId") or {}
    bucket = buckets.get("codex") or result.get("rateLimits") or next(iter(buckets.values()), {})
    windows = [w for w in (bucket.get("primary"), bucket.get("secondary")) if w and w.get("usedPercent") is not None]
    weekly = next((w for w in windows if w.get("windowDurationMins") == 10080), None)
    return bucket, weekly or (windows[0] if windows else None), windows


def fetch_loop():
    def connected_client():
        global STARTUP_ISSUE
        executable = find_codex()
        STARTUP_ISSUE = None
        return AccountClient(executable, BASE, STOP)

    threading.Thread(target=watch_activity, daemon=True).start()
    transport_loop(
        STOP,
        REFRESH,
        UPDATES,
        connected_client,
        choose_bucket,
        lambda data: save_json(BASE / "quota-cache.json", data),
        active=ACTIVITY.is_set,
    )


def monitors():
    bounds = []

    class Info(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
    )

    def callback(handle, dc, rect, param):
        info = Info()
        info.cbSize = ctypes.sizeof(info)
        USER32.GetMonitorInfoW(handle, ctypes.byref(info))
        r = info.rcWork
        bounds.append((r.left, r.top, r.right, r.bottom))
        return True

    cb = callback_type(callback)
    USER32.EnumDisplayMonitors(None, None, cb, 0)
    return bounds or [(0, 0, 1920, 1080)]


def compact(value):
    if value is None:
        return "—"
    if value >= 1e9:
        return f"{value / 1e9:.2f}".replace(".", ",") + " млрд"
    if value >= 1e6:
        return f"{value / 1e6:.2f}".replace(".", ",") + " млн"
    return f"{value:,}".replace(",", " ")


from usage_ui import Widget


def main():
    global BASE, CONFIG, STATUS, STARTUP_ISSUE
    parser = argparse.ArgumentParser(description="VLADMACC Codex Usage Widget")
    parser.add_argument("--settings", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--quit", action="store_true")
    parser.add_argument("--data-dir")
    parser.add_argument("--self-test", metavar="REPORT_JSON")
    parser.add_argument("--smoke-test", metavar="REPORT_JSON")
    args = parser.parse_args()
    if args.smoke_test and not args.data_dir:
        parser.error("--smoke-test requires an isolated --data-dir")
    BASE = data_directory(args.data_dir)
    if args.smoke_test and (BASE == data_directory() or (BASE.exists() and any(BASE.iterdir()))):
        parser.error("--smoke-test requires a new empty data directory outside the normal user data")
    CONFIG, STATUS = BASE / "position.json", BASE / "status.json"
    if args.self_test:
        from release_checks import self_test

        return self_test(Path(args.self_test), BASE)
    if args.quit:
        return 0 if request_shutdown(BASE) else 1
    if args.watch:
        from usage_autostart import main as watch_main

        return watch_main(BASE)
    first_run = not CONFIG.exists()
    BASE.mkdir(parents=True, exist_ok=True)
    signals = Signals(BASE, create=True)
    if not signals.acquire("widget"):
        signals.send("settings")
        signals.close()
        return 0
    try:
        USER32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass
    try:
        find_codex()
    except FileNotFoundError:
        STARTUP_ISSUE = "codex_missing"
    if args.smoke_test:
        from release_checks import smoke_test

        try:
            return smoke_test(sys.modules[__name__], Path(args.smoke_test))
        finally:
            signals.close()
    try:
        widget = Widget(sys.modules[__name__])

        def commands():
            if signals.received("stop"):
                widget.close()
                return
            if signals.received("settings"):
                widget.open_admin()
            widget.root.after(200, commands)

        widget.root.after(200, commands)
        if args.settings or STARTUP_ISSUE or first_run:

            def open_settings():
                widget.open_admin()
                if STARTUP_ISSUE or first_run:
                    widget.admin.navigate("data")

            widget.root.after(400, open_settings)
        widget.run()
        return 0
    finally:
        signals.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Keep credentials and upstream responses out of crash reports.
        write_json(BASE / "startup-error.json", {"version": VERSION, "error": "startup_failed"})
        ctypes.windll.user32.MessageBoxW(
            None,
            "Не удалось запустить виджет. Откройте инструкцию или сообщите об ошибке в репозитории приложения.",
            "VLADMACC · Codex Usage Widget",
            0x10,
        )
        raise SystemExit(1)

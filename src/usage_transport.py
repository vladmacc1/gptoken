"""Concurrent read-only JSON-RPC. Slow summaries never hold up quota delivery."""

from concurrent.futures import Future, TimeoutError
import json
import subprocess
import threading
import time
from usage_subscription import normalize_plan
from app_runtime import VERSION


class AccountClient:
    ALLOWED_METHODS = frozenset({"initialize", "account/rateLimits/read", "account/usage/read", "account/read"})

    def __init__(self, executable, cwd, stop):
        self.stop = stop
        self.pending, self.sequence = {}, 0
        self.lock = threading.Lock()
        self.notifications = []
        self.proc = subprocess.Popen(
            [executable, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=str(cwd),
        )
        threading.Thread(target=self.read, daemon=True).start()
        try:
            self.call(
                "initialize",
                {
                    "clientInfo": {"name": "local_usage_widget", "title": "Codex Usage", "version": VERSION},
                    "capabilities": {"experimentalApi": True},
                },
                timeout=12,
            )
            self.send({"method": "initialized", "params": {}})
        except Exception:
            self.close()
            raise

    def send(self, value):
        if value.get("method") != "initialized":
            raise ValueError("Only the initialization acknowledgement is allowed")
        with self.lock:
            self.proc.stdin.write(json.dumps(value) + "\n")
            self.proc.stdin.flush()

    def request(self, method, params=None):
        if method not in self.ALLOWED_METHODS:
            raise ValueError("Only read-only account methods are allowed")
        future = Future()
        with self.lock:
            self.sequence += 1
            request_id = self.sequence
            self.pending[request_id] = future
            try:
                self.proc.stdin.write(json.dumps({"method": method, "id": request_id, "params": params or {}}) + "\n")
                self.proc.stdin.flush()
            except (OSError, ValueError):
                self.pending.pop(request_id, None)
                raise
        return request_id, future

    def read(self):
        try:
            for line in self.proc.stdout:
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                with self.lock:
                    future = self.pending.pop(value.get("id"), None)
                    if value.get("method") == "account/rateLimits/updated":
                        self.notifications.append(value.get("params") or {})
                        self.notifications = self.notifications[-4:]
                    elif value.get("method") == "account/updated":
                        self.notifications.append({"accountPlanType": (value.get("params") or {}).get("planType")})
                if future is not None and not future.done():
                    if "error" in value:
                        future.set_exception(RuntimeError("Данные недоступны"))
                    else:
                        future.set_result(value.get("result") or {})
        finally:
            with self.lock:
                pending, self.pending = self.pending, {}
            for future in pending.values():
                if not future.done():
                    future.set_exception(RuntimeError("Соединение прервано"))

    def abandon(self, request_id):
        with self.lock:
            self.pending.pop(request_id, None)

    def take_notifications(self):
        with self.lock:
            values, self.notifications = self.notifications, []
            return values

    def call(self, method, params=None, timeout=10):
        request_id, future = self.request(method, params)
        deadline = time.monotonic() + timeout
        try:
            while not self.stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    return future.result(timeout=min(0.2, remaining))
                except TimeoutError:
                    pass
            raise RuntimeError("Закрыто" if self.stop.is_set() else "Нет ответа")
        finally:
            self.abandon(request_id)

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def fetch_loop(
    stop, refresh, updates, make_client, choose_bucket, save_cache, active=lambda: False, clock=time.monotonic
):
    client, stats, summary, daily = None, None, {}, []
    next_poll, next_stats = 0, 0
    last_data = None
    was_active = False
    plan_request, next_plan, plan_type = None, 0, None
    try:
        while not stop.is_set():
            now = clock()
            is_active = active()
            if is_active != was_active:
                next_poll = min(next_poll, now)
                was_active = is_active
            manual = refresh.is_set()
            if manual:
                refresh.clear()  # Clear before request, so a click during it remains queued.
            if manual or now >= next_poll:
                updates.put({"kind": "refresh", "state": "loading"})
                try:
                    if client is None or client.proc.poll() is not None:
                        client = make_client()
                        stats = None
                        plan_request, next_plan, plan_type = None, 0, None
                    started = clock()
                    result = client.call("account/rateLimits/read", timeout=10)
                    bucket, window, windows = choose_bucket(result)
                    if window is None:
                        raise RuntimeError("Лимит не предоставлен")
                    last_data = {
                        "kind": "quota",
                        "ok": True,
                        "updatedAt": time.time(),
                        "bucket": bucket.get("limitId", "codex"),
                        "window": window,
                        "windows": windows,
                        "planType": normalize_plan(bucket.get("planType"))
                        or normalize_plan(result.get("planType"))
                        or plan_type,
                        "summary": summary,
                        "daily": daily,
                        "requestMs": round((clock() - started) * 1000),
                    }
                    updates.put(dict(last_data))
                    save_cache(last_data)
                    next_poll = clock() + (12 if active() else 45)
                    if stats is None and now >= next_stats:
                        next_stats = clock() + 600
                        try:
                            request_id, future = client.request("account/usage/read")
                            stats = (request_id, future, clock())
                        except Exception:
                            stats = None
                except Exception:
                    updates.put({"kind": "quota", "ok": False, "checkedAt": time.time()})
                    if client:
                        client.close()
                    client, stats = None, None
                    next_poll = clock() + 15
            if client:
                if plan_request is None and clock() >= next_plan:
                    next_plan = clock() + 60
                    try:
                        request_id, future = client.request("account/read", {"refreshToken": False})
                        plan_request = (request_id, future, clock())
                    except Exception:
                        pass
                if plan_request:
                    request_id, future, requested = plan_request
                    if future.done():
                        try:
                            # Only planType is retained. Email, account identifiers and credentials are discarded.
                            account = future.result().get("account") or {}
                            detected = normalize_plan(account.get("planType"))
                            if detected:
                                plan_type = detected
                                updates.put({"kind": "plan", "planType": plan_type})
                                if last_data:
                                    last_data["planType"] = plan_type
                                    save_cache(last_data)
                        except Exception:
                            pass
                        plan_request = None
                    elif clock() - requested > 6:
                        client.abandon(request_id)
                        plan_request = None
                # Notifications from this connection are hints; authoritative reads remain the fallback.
                notices = client.take_notifications()
                for notice in notices:
                    if "accountPlanType" in notice:
                        plan_type = normalize_plan(notice["accountPlanType"])
                        updates.put({"kind": "plan", "planType": plan_type})
                        next_plan = 0
                if notices:
                    next_poll = min(next_poll, clock() + 2)
                if stats:
                    request_id, future, requested = stats
                    if future.done():
                        try:
                            usage = future.result()
                            summary, daily = usage.get("summary") or {}, usage.get("dailyUsageBuckets") or []
                            updates.put({"kind": "summary", "summary": summary, "daily": daily})
                            if last_data:
                                last_data.update(summary=summary, daily=daily)
                                save_cache(last_data)
                        except Exception:
                            pass
                        stats = None
                    elif clock() - requested > 6:
                        client.abandon(request_id)
                        stats = None
            # A new local turn advances an idle poll without resetting the request every second.
            if active():
                next_poll = min(next_poll, clock() + 12)
            stop.wait(0.1)
    finally:
        if client:
            client.close()

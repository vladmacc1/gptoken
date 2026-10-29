"""Frameless Windows presentation for the existing local account reader."""

import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import os
import queue
import threading
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk
from usage_pace import COLORS, PaceHistory, quota_band


from usage_visuals import PROFILES, profile_from_config, hit_target
from usage_activity import visual_mode
from usage_subscription import subscription_view


from usage_analytics import UsageBook, AlertGate, forecast, duration_text, window_name, MOSCOW
from usage_layout import side_geometry
from usage_appearance import (
    THEMES,
    STYLES,
    FONT_FAMILY,
    FONT_SEMIBOLD,
    appearance_from_config,
    widget_size,
    chart_explanation,
)
from usage_presenter import render_static, render_bar_spec


class Widget:
    WIDTH, HEIGHT = 382, 374
    BG, FG, MUTED, DIM = "#191d24", "#f0f3f7", "#a4adbb", "#707c8e"
    TRANSPARENT = "#010203"

    def __init__(self, api):
        self.api = api
        self.config = self.read_json(api.CONFIG, {})
        self.activity_enabled = bool(self.config.get("activityEnabled", False))
        if hasattr(api, "SET_ACTIVITY"):
            api.SET_ACTIVITY(self.activity_enabled)
        appearance = appearance_from_config(self.config)
        self.ui_style, self.theme, self.history_enabled = (
            appearance["style"],
            appearance["theme"],
            appearance["history"],
        )
        self.set_palette()
        self.admin = None
        self.rendered_frame = None
        self.bar_render_keys, self.animated_values = {}, {}
        self.static_photo = None
        self.brand_photos = []
        self.archive_path = api.BASE / "usage-history.json"
        self.book = UsageBook(self.read_json(self.archive_path, {}))
        self.alerts = AlertGate(self.config.get("alertState"))
        self.profile = profile_from_config(self.config)
        self.WIDTH, self.HEIGHT, _ = PROFILES[self.profile]
        self.compact_mode = self.profile != "detailed"
        self.period = self.config.get("chartPeriod", 3600)
        if self.period not in (3600, 86400, 604800):
            self.period = 3600
        self.selected = self.config.get("selectedLimit", "auto")
        self.alert_interval = self.config.get("alertInterval", 15)
        if self.alert_interval not in (0, 15, 30, 60):
            self.alert_interval = 15
        # Migrate genuine observations from v2, without including them in a new session.
        if not self.book.windows:
            legacy = PaceHistory(self.read_json(api.BASE / "pace-history.json", {}))
            if legacy.key and legacy.samples:
                bucket, duration, reset = legacy.key
                key = f"{bucket}:{duration}"
                self.book.windows[key] = {
                    "window": {"usedPercent": legacy.samples[-1][1], "windowDurationMins": duration, "resetsAt": reset},
                    "plan": None,
                    "samples": [[t, used, reset] for t, used in legacy.samples],
                    "pace": legacy.to_json(),
                }
                self.book.paces[key] = legacy
        self.data, self.failed, self.popup, self.toast = None, False, None, None
        self.cached = True
        self.refresh_state = "loading"
        self.activity = {"active": False, "available": False, "checkedAt": 0}
        self.quota_pulse_until = 0
        self.last_render_key = None
        cached = self.read_json(api.BASE / "quota-cache.json", {})
        if cached.get("ok") and cached.get("updatedAt") and cached.get("windows"):
            self.data = cached
            if not self.book.active:
                self.book.ingest(cached)
        elif self.book.active:
            entry = self.book.windows[self.book.active[0]]
            if entry["samples"]:
                self.data = {
                    "ok": True,
                    "updatedAt": entry["samples"][-1][0],
                    "windows": [self.book.windows[k]["window"] for k in self.book.active],
                    "summary": {},
                }
        self.subscription = subscription_view(self.data)
        self.dual = self.subscription["dual"]
        self.WIDTH, self.HEIGHT = widget_size(self.ui_style, self.profile, self.dual, self.history_enabled)
        self.presented = []
        self.dual_photos, self.dual_render_keys = {}, {}
        self.pending_notice = None
        self.popup_kind = None
        self.popup_canvas, self.panel_buttons, self.menu_rows = None, {}, []
        self.hover_after, self.leave_after, self.hover_target = None, None, None
        self.drag_origin, self.dragging = None, False
        self.animation = bool(self.config.get("animation", True))
        self.topmost = bool(self.config.get("topmost", True))
        self.opacity = min(1.0, max(0.65, float(self.config.get("opacity", 1))))
        self.root = tk.Tk()
        self.root.title("Codex Usage")
        self.root.overrideredirect(True)
        self.root.configure(bg=self.TRANSPARENT)
        self.root.attributes("-transparentcolor", self.TRANSPARENT)
        self.root.attributes("-topmost", self.topmost)
        self.root.attributes("-alpha", self.opacity)
        self.root.resizable(False, False)
        self.header_buttons = {}
        self.header_images = {}
        self.canvas = tk.Canvas(
            self.root, width=self.WIDTH, height=self.HEIGHT, bg=self.TRANSPARENT, bd=0, highlightthickness=0
        )
        self.canvas.pack()
        self.background_item = self.canvas.create_image(0, 0, anchor="nw")
        self.bar_item = self.canvas.create_image(18, 78, anchor="nw")
        self.second_bar_item = self.canvas.create_image(18, 170, anchor="nw", state="hidden")
        self.bar_photo = None
        self.mode, self.slot = "learning", None
        self.remaining, self.display_remaining = 0.0, 0.0
        self.color = COLORS["green"]
        self.pace = {"mode": "learning", "rate": None, "ratio": None, "budget": None, "spanMinutes": 0}
        self.prediction = forecast(0, None, time.time(), None)
        self.today = None
        self.last_frame, self.last_phase = time.monotonic(), 0
        self.last_report, self.last_refresh_click = 0, 0
        self.build_background()
        screens = api.monitors()
        left = min(screens, key=lambda r: r[0])
        try:
            x, y = int(self.config["x"]), int(self.config["y"])
        except (KeyError, TypeError, ValueError):
            x, y = left[0] + 38, left[3] - self.HEIGHT - 20
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+0+0")
        self.root.update_idletasks()
        self.fit_position(x, y)
        self.canvas.bind("<ButtonPress-1>", self.drag_start)
        self.canvas.bind("<B1-Motion>", self.drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.drag_end)
        self.canvas.bind("<Button-3>", self.toggle_menu)
        self.canvas.bind("<Motion>", self.pointer)
        self.canvas.bind("<Leave>", self.schedule_leave)
        self.root.bind("<Escape>", lambda e: self.close_popup())
        self.root.bind("<Control-r>", lambda e: self.refresh())
        self.root.bind("<Alt-F4>", lambda e: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.draw()
        self.display_remaining = self.remaining
        self.receive()
        self.animate()
        self.tick()
        threading.Thread(target=api.fetch_loop, daemon=True).start()

    @staticmethod
    def read_json(path, fallback):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            return result if isinstance(result, type(fallback)) else fallback
        except (OSError, ValueError):
            return fallback

    def save_book(self):
        self.api.save_json(self.archive_path, self.book.to_json())

    def save_settings(self):
        self.config.update(
            x=self.root.winfo_x(),
            y=self.root.winfo_y(),
            topmost=self.topmost,
            animation=self.animation,
            opacity=self.opacity,
            compact=self.compact_mode,
            profile=self.profile,
            uiStyle=self.ui_style,
            theme=self.theme,
            historyEnabled=self.history_enabled,
            activityEnabled=self.activity_enabled,
            chartPeriod=self.period,
            selectedLimit=self.selected,
            alertInterval=self.alert_interval,
            alertState=self.alerts.to_json(),
        )
        self.api.save_json(self.api.CONFIG, self.config)

    def move(self, x, y):
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{int(x)}+{int(y)}")

    def fit_position(self, x, y):
        screens = self.api.monitors()
        screen = next((r for r in screens if r[0] <= x < r[2] and r[1] <= y < r[3]), screens[0])
        self.move(
            max(screen[0] + 8, min(x, screen[2] - self.WIDTH - 8)),
            max(screen[1] + 8, min(y, screen[3] - self.HEIGHT - 8)),
        )

    def set_palette(self):
        p = THEMES[self.theme]
        self.BG, self.FG, self.MUTED, self.DIM = p["bg"], p["fg"], p["muted"], p["dim"]
        self.PANEL, self.BORDER, self.HOVER, self.TRACK = p["panel"], p["border"], p["hover"], p["track"]

    def build_background(self):
        self.canvas.configure(width=self.WIDTH, height=self.HEIGHT)
        self.canvas.delete("background")
        self.canvas.tag_lower(self.background_item)
        self.last_render_key, self.bar_render_keys = None, {}
        self.canvas.itemconfigure(self.second_bar_item, state="normal" if self.dual else "hidden")
        self.build_header_controls()
        self.root.after_idle(self.round_window)

    def build_header_controls(self):
        for button in self.header_buttons.values():
            button.destroy()
        self.header_buttons, self.header_images = {}, {}
        if self.profile == "mini":
            return
        # Native Tk buttons receive the click themselves, independently of dragging the canvas.
        for name, center, action in (
            ("menu", self.WIDTH - 28, self.toggle_menu),
            ("refresh", self.WIDTH - 64, self.refresh),
        ):
            image = Image.new("RGBA", (24, 24))
            draw = ImageDraw.Draw(image)
            if name == "menu":
                for x in (6, 12, 18):
                    draw.ellipse((x - 1, 11, x + 1, 13), fill=self.MUTED)
            else:
                draw.arc((5, 5, 19, 19), start=40, end=325, fill=self.MUTED, width=2)
                draw.line((18, 4, 19, 9, 14, 8), fill=self.MUTED, width=2)
            photo = ImageTk.PhotoImage(image)
            button = tk.Button(
                self.canvas,
                image=photo,
                command=action,
                bg=self.BG,
                activebackground="#2b333f",
                bd=0,
                highlightthickness=0,
                relief="flat",
                cursor="hand2",
                takefocus=True,
            )
            button.place(x=center - 18, y=8, width=36, height=36)
            button.bind("<Enter>", self.control_enter)
            button.bind("<Leave>", self.schedule_leave)
            self.header_buttons[name], self.header_images[name] = button, photo

    def control_enter(self, event=None):
        if self.leave_after:
            self.root.after_cancel(self.leave_after)
            self.leave_after = None
        self.cancel_hover()

    def settings_enter(self, event=None):
        self.control_enter()
        return

    def round_window(self):
        # Tk draws the rounded card at its final size. No native region can retain an old clip.
        self.root.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
        hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        user32.SetWindowRgn(hwnd, None, True)

    def cancel_hover(self):
        if self.hover_after:
            self.root.after_cancel(self.hover_after)
        self.hover_after, self.hover_target = None, None

    def hover_action(self, name, action):
        # Kept for old callers; all navigation is explicitly clicked in v4.1.
        return

    def pointer(self, event):
        if not self.dragging:
            target = hit_target(self.profile, self.WIDTH, event.x, event.y, self.HEIGHT)
            self.canvas.configure(cursor="hand2" if target else "fleur")

    def schedule_leave(self, event=None):
        self.cancel_hover()
        if self.leave_after:
            self.root.after_cancel(self.leave_after)
            self.leave_after = None

    def check_pointer(self):
        # Leaving the widget or side panel never dismisses an explicitly opened panel.
        self.leave_after = None

    def toggle_menu(self, event=None):
        if self.popup:
            self.close_popup()
        else:
            self.open_menu()

    def drag_start(self, event):
        self.cancel_hover()
        if hit_target(self.profile, self.WIDTH, event.x, event.y, self.HEIGHT) != "menu":
            self.close_popup()
        self.drag_origin = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())
        self.dragging = False

    def drag_move(self, event):
        if self.drag_origin is None:
            return
        mx, my, x, y = self.drag_origin
        dx, dy = event.x_root - mx, event.y_root - my
        if abs(dx) + abs(dy) > 4:
            self.dragging = True
            self.close_popup()
            self.move(x + dx, y + dy)

    def drag_end(self, event):
        if not self.dragging:
            target = hit_target(self.profile, self.WIDTH, event.x, event.y, self.HEIGHT)
            if target == "menu":
                self.toggle_menu()
            elif target == "refresh":
                self.refresh()
            elif target == "limits":
                self.show_limits()
            else:
                self.show_details()
        self.dragging, self.drag_origin = False, None
        self.save_settings()

    def refresh(self):
        self.close_popup()
        self.last_refresh_click = time.monotonic()
        self.refresh_state = "loading"
        self.api.REFRESH.set()
        self.draw()
        self.report()

    def text(self, x, y, text, size=12, fill=None, bold=False, anchor="w"):
        return self.canvas.create_text(
            x,
            y,
            text=text,
            anchor=anchor,
            fill=fill or self.FG,
            font=(FONT_FAMILY, -size, "bold" if bold else "normal"),
            tags="text",
        )

    def forecast_text(self):
        p = self.prediction
        if p["state"] == "risk":
            return "Хватит ≈ " + duration_text(p["seconds"]), "При текущем темпе · раньше сброса"
        if p["state"] == "safe":
            return "Хватит до сброса", "При текущем темпе · ≈ " + duration_text(p["seconds"]) + " работы"
        return {
            "empty": ("Лимит исчерпан", "Ждём подтверждения сброса"),
            "stale": ("Прогноз приостановлен", "Ожидаем свежие данные"),
            "reset": ("Ожидаем сброс", "Проверяем остаток на сервере"),
            "idle": ("Расхода пока нет", "Прогноз появится при расходе"),
            "learning": ("Собираем данные для прогноза", "Первые измерения через 4 минуты"),
            "unknown": ("Прогноз недоступен", "Время сброса неизвестно"),
        }[p["state"]]

    def sync_text(self):
        if self.cached and self.refresh_state == "loading":
            return "Сохранено · обновляем"
        if self.refresh_state == "loading":
            return "Обновляем…"
        if self.failed:
            return "Нет связи · повторяем"
        if self.cached:
            return "Сохранённые данные"
        if not self.data:
            return "Подключение…"
        age = max(0, int(time.time() - self.data["updatedAt"]))
        return f"Обновлено {age} с назад" if age < 60 else f"Обновлено {age // 60} мин назад"

    def activity_text(self):
        if self.activity.get("active") and time.time() - self.activity.get("checkedAt", 0) < 5:
            return "Идёт работа"
        if time.time() < self.quota_pulse_until:
            return "Лимит изменился"
        return "Ожидание" if self.activity.get("available") or not self.activity_enabled else "Активность недоступна"

    def update_subscription(self):
        self.subscription = subscription_view(self.data)
        self.dual = self.subscription["dual"]
        size = widget_size(self.ui_style, self.profile, self.dual, self.history_enabled)
        if size != (self.WIDTH, self.HEIGHT):
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.close_popup()
            self.WIDTH, self.HEIGHT = size
            self.build_background()
            self.fit_position(x, y)
            self.root.update_idletasks()
        self.presented = []
        for slot in self.subscription["slots"]:
            key = next(
                (
                    k
                    for k in self.book.active
                    if self.book.windows[k]["window"].get("windowDurationMins") == slot["duration"]
                ),
                None,
            )
            # A missing window in the current response must not use an old historical measurement.
            if slot["window"] is None:
                key = None
            self.presented.append(
                {**slot, "key": key, "state": self.book.evaluate(key, time.time(), self.failed) if key else None}
            )

    def presentation_rows(self, history=None):
        show_history = self.history_enabled if history is None else history
        rows = []
        now = time.time()
        for item in self.presented:
            state = item["state"]
            rows.append(
                {
                    "label": item["label"],
                    "duration": item["duration"],
                    "remaining": state["remaining"] if state else None,
                    "reset": state["window"].get("resetsAt") if state else None,
                    "mode": state["pace"]["mode"] if state else "unknown",
                    "muted": self.cached or self.failed,
                    "segments": self.book.chart_segments(item["key"], now, self.period)
                    if show_history and item["key"]
                    else [],
                }
            )
        return rows

    def draw(self):
        self.update_subscription()
        now = time.time()
        for tag in ("text", "chart", "plan"):
            self.canvas.delete(tag)
        visible = [p["key"] for p in self.presented if p["key"]]
        chosen = self.book.select(now, self.selected, self.failed) if self.data else None
        self.slot = chosen if chosen in visible else (visible[0] if visible else None)
        if self.slot:
            state = self.book.evaluate(self.slot, now, self.failed)
            self.remaining, self.pace, self.prediction = state["remaining"], state["pace"], state["forecast"]
            self.mode, self.color = self.pace["mode"], THEMES[self.theme][quota_band(self.remaining)]
            self.today = self.book.budget(self.slot, now)
        else:
            self.mode, self.today = "stale" if self.failed else "learning", None
        self.rendered_frame = render_static(
            self.ui_style,
            self.theme,
            self.profile,
            self.presentation_rows(),
            plan=self.subscription["plan"],
            history=self.history_enabled,
            sync=self.sync_text(),
            activity=self.activity_text(),
            now=now,
            period=self.period,
        )
        self.static_photo = ImageTk.PhotoImage(self.rendered_frame.image)
        self.canvas.itemconfigure(self.background_item, image=self.static_photo)
        for index, spec in enumerate(self.rendered_frame.bars):
            self.canvas.coords(self.bar_item if index == 0 else self.second_bar_item, spec["x"], spec["y"])
        self.canvas.tag_lower(self.background_item)

    def draw_chart(self, canvas, x, y, width, height, period, tag="chart", key=None, color=None):
        now = time.time()
        canvas.create_line(x, y + height, x + width, y + height, fill=self.BORDER, tags=tag)
        key = key or self.slot
        color = color or self.color
        if not key:
            return
        segments = self.book.chart_segments(key, now, period)
        for segment in segments:
            points = []
            for t, remaining in segment:
                points.extend((x + (t - now + period) / period * width, y + (100 - remaining) / 100 * height))
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=2, tags=tag)
            elif points:
                px, py = points
                canvas.create_oval(px - 2, py - 2, px + 2, py + 2, fill=color, outline="", tags=tag)
        if not segments:
            canvas.create_text(
                x + width / 2,
                y + height / 2,
                text="История начнётся с первого измерения",
                fill=self.DIM,
                font=(FONT_FAMILY, -10),
                tags=tag,
            )

    def animate(self):
        now = time.monotonic()
        dt, self.last_frame = min(0.15, now - self.last_frame), now
        specs = self.rendered_frame.bars if self.rendered_frame else []
        modes = [
            visual_mode(
                spec["mode"],
                self.activity,
                self.quota_pulse_until,
                time.time(),
                valid=spec["valid"] and not self.cached and not self.failed,
            )
            for spec in specs
        ]
        motion = self.animation and any(mode != "still" for mode in modes)
        if motion:
            self.last_phase += dt * 1.4
        for index, (spec, mode) in enumerate(zip(specs, modes)):
            value = self.animated_values.get(index, spec["remaining"])
            value += (spec["remaining"] - value) * min(1, dt * 10)
            if abs(value - spec["remaining"]) < 0.02:
                value = spec["remaining"]
            self.animated_values[index] = value
            mode = mode if self.animation else "still"
            key = (
                round(value, 2),
                spec["color"],
                spec["track"],
                spec["width"],
                spec["vertical"],
                spec.get("displayWidth"),
                mode,
                round(self.last_phase, 3) if mode != "still" else 0,
            )
            if self.bar_render_keys.get(index) != key:
                image = render_bar_spec({**spec, "remaining": value}, self.last_phase, mode)
                photo = ImageTk.PhotoImage(image)
                self.dual_photos[index] = photo
                self.canvas.itemconfigure(self.bar_item if index == 0 else self.second_bar_item, image=photo)
                self.bar_render_keys[index] = key
                if index == 0:
                    self.bar_photo, self.display_remaining = photo, value
        self.root.after(50 if motion else 150, self.animate)

    def receive(self):
        changed = False
        while True:
            try:
                result = self.api.UPDATES.get_nowait()
            except queue.Empty:
                break
            kind = result.get("kind", "quota")
            if kind == "activity":
                changed = changed or self.activity.get("active") != result.get("active")
                self.activity = result
                continue
            if kind == "refresh":
                self.refresh_state = result["state"]
                changed = True
                continue
            if kind == "plan":
                if self.data:
                    self.data["planType"] = result.get("planType")
                changed = True
                continue
            if kind == "summary":
                if self.data:
                    self.data.update(summary=result["summary"], daily=result.get("daily", []))
                changed = True
                continue
            self.failed = not result.get("ok")
            self.refresh_state = "error" if self.failed else "success"
            if result.get("ok"):
                first = self.data is None or self.cached
                previous = {k: v["window"].copy() for k, v in self.book.windows.items()}
                self.data, self.cached = result, False
                self.book.ingest(result)
                if not first:
                    for k in self.book.active:
                        before, after = previous.get(k), self.book.windows[k]["window"]
                        if (
                            before
                            and before.get("resetsAt") == after.get("resetsAt")
                            and after["usedPercent"] > before["usedPercent"]
                        ):
                            self.quota_pulse_until = time.time() + 8
                self.save_book()
                self.draw()
                if first:
                    self.display_remaining = self.remaining
                notice = self.alerts.check(
                    self.book, result["updatedAt"], enabled=self.alert_interval > 0, cooldown=self.alert_interval * 60
                )
                self.save_settings()
                if notice:
                    self.show_notice(notice["text"])
            changed = True
        if changed:
            self.draw()
            self.report()
            if self.popup_kind == "details":
                self.update_details()
            if self.admin:
                self.admin.schedule_preview()
        self.root.after(100, self.receive)

    def tick(self):
        self.draw()
        if self.pending_notice and not self.popup:
            message, self.pending_notice = self.pending_notice, None
            self.show_notice(message)
        if time.monotonic() - self.last_report >= 5:
            self.report()
            if self.popup_kind == "details":
                self.update_details()
        self.root.after(1000, self.tick)

    def report(self):
        self.last_report = time.monotonic()
        report = {
            "version": getattr(self.api, "VERSION", "5.1.0"),
            "activityEnabled": self.activity_enabled,
            "profile": self.profile,
            "cached": self.cached,
            "refreshState": self.refresh_state,
            "adminOpen": bool(self.admin and self.admin.exists()),
            "controlsVersion": 4,
            "uiStyle": self.ui_style,
            "theme": self.theme,
            "historyEnabled": self.history_enabled,
            "fontFamily": FONT_FAMILY,
            "fontSemibold": FONT_SEMIBOLD,
            "menuMode": "click",
            "planType": self.subscription["plan"],
            "layout": "dual" if self.dual else "single",
            "displayWindows": [s["duration"] for s in self.subscription["slots"]],
            "popupKind": self.popup_kind,
            "popupMapped": bool(self.popup and self.popup.winfo_ismapped()),
            "activity": self.activity,
            "visualMode": visual_mode(
                self.mode, self.activity, self.quota_pulse_until, time.time(), valid=not self.cached and not self.failed
            ),
            "pid": os.getpid(),
            "ok": bool(self.slot) and not self.cached and not self.failed and self.mode != "stale",
            "x": self.root.winfo_x(),
            "y": self.root.winfo_y(),
            "topmost": self.topmost,
            "frameless": bool(self.root.overrideredirect()),
            "animation": self.animation,
            "compact": self.compact_mode,
            "checkedAt": time.time(),
            "geometry": self.root.geometry(),
            "pace": self.pace,
            "forecast": self.prediction,
            "selectedLimit": self.selected,
            "activeLimit": self.slot,
            "limitCount": len(self.book.active),
            "monitors": self.api.monitors(),
        }
        if self.slot:
            report.update(
                updatedAt=self.data["updatedAt"],
                window=self.book.windows[self.slot]["window"],
                lifetimeTokens=self.data["summary"].get("lifetimeTokens"),
                remaining=self.remaining,
                colorBand=quota_band(self.remaining),
                dailyBudget=self.today,
                session=self.book.session_summary(self.slot, time.time()),
                sampleCount=len(self.book.windows[self.slot]["samples"]),
            )
        self.api.save_json(self.api.STATUS, report)

    def close_popup(self):
        self.cancel_hover()
        if self.popup:
            self.popup.destroy()
        self.popup, self.popup_kind, self.popup_canvas = None, None, None

    def popup_shell(self, kind, width, height):
        self.close_popup()
        x, y, width, height = side_geometry(
            (self.root.winfo_x(), self.root.winfo_y(), self.WIDTH, self.HEIGHT), self.api.monitors(), width, height
        )
        popup = tk.Toplevel(self.root)
        popup.withdraw()
        self.popup, self.popup_kind = popup, kind
        popup.transient(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", self.topmost)
        popup.configure(bg=self.BORDER)
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.bind("<Escape>", lambda e: self.close_popup())
        popup.bind("<Leave>", self.schedule_leave)
        popup.deiconify()
        return popup, width, height

    def panel(self, kind, title, width=292, height=444):
        popup, width, height = self.popup_shell(kind, width, height)
        frame = tk.Frame(popup, bg=self.PANEL, padx=12, pady=10)
        frame.pack(fill="both", expand=True, padx=1, pady=1)
        header = tk.Frame(frame, bg=self.PANEL)
        header.pack(fill="x", pady=(0, 5))
        tk.Label(header, text=title, bg=self.PANEL, fg=self.MUTED, font=(FONT_FAMILY, -12)).pack(side="left")
        self.panel_close_button = tk.Button(
            header,
            text="×",
            command=self.close_popup,
            bg=self.PANEL,
            fg=self.MUTED,
            activebackground=self.HOVER,
            bd=0,
            font=(FONT_FAMILY, -16),
            cursor="hand2",
        )
        self.panel_close_button.pack(side="right")
        self.panel_buttons = {}
        return frame, width, height

    def button(self, frame, label, action, hover=None, key=None):
        button = tk.Button(
            frame,
            text=label,
            command=action,
            anchor="w",
            bd=0,
            bg=self.PANEL,
            fg=self.FG,
            activebackground=self.HOVER,
            activeforeground=self.FG,
            font=(FONT_FAMILY, -12),
            padx=8,
            pady=6,
            cursor="hand2",
            highlightthickness=0,
        )
        button.pack(fill="x", pady=1)
        if key:
            self.panel_buttons[key] = button
        return button

    def open_menu(self, event=None):
        frame, _, _ = self.panel("menu", "Настройки виджета", height=566)
        self.menu_rows = []
        choices = [
            ("Панель управления  ›", self.open_admin, None, "admin"),
            ("Обновить сейчас", self.refresh, None, "refresh"),
            ("Сводка и графики  ›" if self.dual else "Сводка и график  ›", self.show_details, "details", "details"),
            ("Все лимиты  ›", self.show_limits, "limits", "limits"),
            ("Размер и вид  ›", self.show_profiles, "profiles", "profiles"),
            (
                "Пауза сеанса" if self.book.session and self.book.session["running"] else "Продолжить сеанс",
                self.toggle_session,
                None,
                "session",
            ),
            ("Начать новый сеанс", self.reset_session, None, "reset_session"),
            (
                "Бюджет · " + ("только будни" if self.book.workdays else "все дни"),
                self.toggle_workdays,
                None,
                "workdays",
            ),
            (
                "Уведомления · " + (f"{self.alert_interval} мин" if self.alert_interval else "выкл"),
                self.cycle_alerts,
                None,
                "alerts",
            ),
            (("✓  " if self.topmost else "○  ") + "Поверх всех окон", self.toggle_topmost, None, "topmost"),
            (("✓  " if self.animation else "○  ") + "Анимация", self.toggle_animation, None, "animation"),
            (f"Непрозрачность · {round(self.opacity * 100)}%", self.cycle_opacity, None, "opacity"),
            ("Закрыть виджет", self.close, None, "close"),
        ]
        for label, action, hover, key in choices:
            self.menu_rows.append(self.button(frame, label, action, hover, key))
        self.studio_footer(frame)

    def show_profiles(self):
        frame, _, _ = self.panel("profiles", "Размер и вид", height=242)
        for key, (_, _, label) in PROFILES.items():
            width, height = widget_size(self.ui_style, key, self.dual, self.history_enabled)
            label = label.split(" · ")[0] + f" · {width} × {height}"
            if self.dual and key == "square":
                label = f"Компактный · {width} × {height}"
            self.button(
                frame, ("✓  " if key == self.profile else "    ") + label, lambda k=key: self.set_profile(k), key=key
            )
        self.button(frame, "‹ Настройки", self.open_menu, "menu")

    def set_profile(self, profile):
        if profile in PROFILES:
            self.apply_preferences({"profile": profile})

    def apply_preferences(self, values):
        self.close_popup()
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.ui_style = values.get("style", self.ui_style)
        self.theme = values.get("theme", self.theme)
        self.profile = values.get("profile", self.profile)
        if self.ui_style not in STYLES:
            self.ui_style = "minimal"
        if self.theme not in THEMES:
            self.theme = "dark"
        if self.profile not in PROFILES:
            self.profile = "horizontal"
        self.history_enabled = bool(values.get("history", self.history_enabled))
        self.animation = bool(values.get("animation", self.animation))
        self.activity_enabled = bool(values.get("activity", self.activity_enabled))
        if hasattr(self.api, "SET_ACTIVITY"):
            self.api.SET_ACTIVITY(self.activity_enabled)
        self.topmost = bool(values.get("topmost", self.topmost))
        self.opacity = min(1.0, max(0.65, float(values.get("opacity", self.opacity))))
        interval = values.get("alerts", self.alert_interval)
        self.alert_interval = interval if interval in (0, 15, 30, 60) else 15
        if "workdays" in values and bool(values["workdays"]) != self.book.workdays:
            self.book.set_workdays(bool(values["workdays"]), time.time())
            self.save_book()
        self.compact_mode = self.profile != "detailed"
        self.set_palette()
        self.WIDTH, self.HEIGHT = widget_size(self.ui_style, self.profile, self.dual, self.history_enabled)
        self.root.attributes("-topmost", self.topmost)
        self.root.attributes("-alpha", self.opacity)
        self.build_background()
        self.fit_position(x, y)
        self.root.update_idletasks()
        self.round_window()
        self.draw()
        self.save_settings()
        self.report()

    def studio_footer(self, parent):
        footer = tk.Frame(parent, bg=self.PANEL)
        self.brand_footer = footer
        footer.pack(side="bottom", fill="x", pady=(5, 0))
        tk.Label(footer, text="Сделано в дизайн-студии", bg=self.PANEL, fg=self.DIM, font=(FONT_FAMILY, -10)).pack(
            anchor="w"
        )
        path = getattr(self.api, "ASSETS", self.api.BASE / "assets") / "vladmacc-logo.png"
        if path.exists():
            image = Image.open(path).convert("RGB")
            image.thumbnail((136, 62), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.brand_photos.append(photo)
            self.brand_photos = self.brand_photos[-8:]
            tk.Label(footer, image=photo, bg="#000000", bd=0).pack(anchor="w", pady=(3, 0))
        else:
            tk.Label(footer, text="VLADMACC", bg=self.PANEL, fg=self.FG, font=(FONT_SEMIBOLD, -17)).pack(anchor="w")

    def open_admin(self):
        self.close_popup()
        if self.admin and self.admin.exists():
            self.admin.window.deiconify()
            self.admin.window.lift()
            return
        from usage_admin import SettingsPanel

        self.admin = SettingsPanel(self)

    def toggle_compact(self):
        self.set_profile("horizontal" if self.profile == "detailed" else "detailed")

    def toggle_session(self):
        if self.book.session and self.book.session["running"]:
            self.book.pause_session(time.time())
        else:
            self.book.resume_session(time.time())
        self.save_book()
        self.draw()
        if self.popup_kind == "menu":
            self.open_menu()

    def reset_session(self):
        self.book.reset_session(time.time())
        self.save_book()
        self.draw()
        self.open_menu()

    def toggle_workdays(self):
        self.book.set_workdays(not self.book.workdays, time.time())
        self.save_book()
        self.draw()
        self.open_menu()

    def cycle_alerts(self):
        values = [15, 30, 60, 0]
        self.alert_interval = values[(values.index(self.alert_interval) + 1) % len(values)]
        self.save_settings()
        self.open_menu()

    def toggle_topmost(self):
        self.topmost = not self.topmost
        self.root.attributes("-topmost", self.topmost)
        self.save_settings()
        self.open_menu()

    def toggle_animation(self):
        self.animation = not self.animation
        self.save_settings()
        self.open_menu()

    def cycle_opacity(self):
        self.opacity = 0.85 if self.opacity > 0.9 else 0.70 if self.opacity > 0.75 else 1.0
        self.root.attributes("-alpha", self.opacity)
        self.save_settings()
        self.open_menu()

    def set_period(self, period):
        self.period = period
        self.save_settings()
        self.draw()
        if self.popup_kind == "details":
            self.update_details()

    def select_limit(self, key):
        self.selected = key
        self.save_settings()
        self.draw()
        self.show_limits()

    def show_limits(self):
        frame, width, _ = self.panel("limits", "Доступные лимиты", height=160 + 52 * len(self.book.active))
        self.button(
            frame,
            ("✓  " if self.selected == "auto" else "○  ") + "Авто · закончится раньше",
            lambda: self.select_limit("auto"),
            key="auto",
        )
        if not self.book.active:
            tk.Label(frame, text="Ждём данные аккаунта", bg=self.PANEL, fg=self.MUTED).pack(pady=12)
        for key in self.book.active:
            s = self.book.evaluate(key, time.time(), self.failed)
            name = window_name(s["window"])
            marker = "✓  " if self.selected == key else "○  "
            self.button(
                frame, f"{marker}{name} · осталось {s['remaining']:g}%", lambda k=key: self.select_limit(k), key=key
            )
        tk.Label(
            frame,
            text="Каждый лимит имеет свою историю.\nПроценты разных окон не складываются.",
            bg=self.PANEL,
            fg=self.DIM,
            font=(FONT_FAMILY, -10),
            justify="left",
            wraplength=width - 30,
        ).pack(pady=10)

    def show_details(self):
        frame, width, height = self.panel("details", "Расход аккаунта", width=414, height=690 if self.dual else 548)
        tk.Label(
            frame,
            text=chart_explanation(),
            bg=self.PANEL,
            fg=self.MUTED,
            font=(FONT_FAMILY, -10),
            justify="left",
            wraplength=width - 28,
        ).pack(fill="x", pady=(0, 8))
        toolbar = tk.Frame(frame, bg=self.PANEL)
        toolbar.pack(fill="x")
        self.period_buttons = {}
        for seconds, name in ((3600, "1 час"), (86400, "24 часа"), (604800, "7 дней")):
            button = tk.Button(
                toolbar,
                text=name,
                command=lambda p=seconds: self.set_period(p),
                bd=0,
                bg=self.TRACK,
                fg=self.FG,
                activebackground=self.HOVER,
                font=(FONT_FAMILY, -11),
                padx=10,
                pady=5,
            )
            button.pack(side="left", padx=(0, 4))
            self.period_buttons[seconds] = button
        self.popup_canvas = tk.Canvas(
            frame, width=width - 28, height=290 if self.dual else 168, bg=self.PANEL, bd=0, highlightthickness=0
        )
        self.popup_canvas.pack(fill="x", pady=(8, 6))
        detail_frame = tk.Frame(frame, bg=self.PANEL)
        detail_frame.pack(fill="both", expand=True)
        scrollbar = tk.Scrollbar(detail_frame)
        scrollbar.pack(side="right", fill="y")
        self.details_label = tk.Text(
            detail_frame,
            bg=self.PANEL,
            fg=self.MUTED,
            font=(FONT_FAMILY, -11),
            wrap="word",
            height=1,
            bd=0,
            highlightthickness=0,
            state="disabled",
            yscrollcommand=scrollbar.set,
        )
        self.details_label.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.details_label.yview)
        self.button(frame, "‹ Настройки", self.open_menu, "menu")
        self.popup.update_idletasks()
        self.update_details()

    def set_details_text(self, text):
        position = self.details_label.yview()[0]
        self.details_label.configure(state="normal")
        self.details_label.delete("1.0", "end")
        self.details_label.insert("1.0", text)
        self.details_label.configure(state="disabled")
        self.details_label.yview_moveto(position)

    def update_details(self):
        if not self.popup_canvas or self.popup_kind != "details":
            return
        c = self.popup_canvas
        c.delete("all")
        for seconds, button in self.period_buttons.items():
            button.configure(bg=self.HOVER if seconds == self.period else self.TRACK)
        width = max(150, self.popup.winfo_width() - 28)
        now = time.time()
        if self.dual:
            for index, slot in enumerate(self.presented):
                top = 12 + index * 142
                c.create_text(2, top, text=slot["label"], anchor="w", fill=self.FG, font=(FONT_FAMILY, -11, "bold"))
                for value in (100, 0):
                    y = top + 20 + (100 - value) / 100 * 82
                    c.create_text(2, y, text=f"{value}%", anchor="w", fill=self.DIM, font=(FONT_FAMILY, -9))
                    c.create_line(35, y, width - 5, y, fill=self.BORDER, dash=(2, 5))
                if slot["key"]:
                    self.draw_chart(
                        c,
                        35,
                        top + 20,
                        width - 40,
                        82,
                        self.period,
                        key=slot["key"],
                        color=COLORS[quota_band(slot["state"]["remaining"])],
                    )
                else:
                    c.create_text(
                        45, top + 60, text="Нет измерений", anchor="w", fill=self.DIM, font=(FONT_FAMILY, -10)
                    )
                c.create_text(width - 5, top + 119, text="сейчас", anchor="e", fill=self.DIM, font=(FONT_FAMILY, -9))
        else:
            for value in (100, 50, 0):
                y = 12 + (100 - value) / 100 * 128
                c.create_text(2, y, text=f"{value}%", anchor="w", fill=self.DIM, font=(FONT_FAMILY, -10))
                c.create_line(35, y, width - 5, y, fill=self.BORDER, dash=(2, 5))
            self.draw_chart(c, 35, 12, width - 40, 128, self.period)
            left = datetime.fromtimestamp(now - self.period, MOSCOW).strftime("%d.%m %H:%M")
            c.create_text(35, 157, text=left, anchor="w", fill=self.DIM, font=(FONT_FAMILY, -9))
            c.create_text(width - 5, 157, text="сейчас", anchor="e", fill=self.DIM, font=(FONT_FAMILY, -9))
        if not self.slot:
            self.set_details_text("История появится после получения данных.")
            return
        session = self.book.session_summary(self.slot, now)
        primary, secondary = self.forecast_text()
        lines = [
            primary,
            secondary,
            "",
            f"Сеанс аккаунта: {session['spent']:.1f} п.п. за {duration_text(session['seconds'])}",
        ]
        if self.dual:
            lines.extend(
                [""]
                + [
                    slot["label"]
                    + ": "
                    + (f"осталось {slot['state']['remaining']:g}%" if slot["state"] else "ожидаем данные")
                    for slot in self.presented
                ]
            )
        if session["partial"]:
            lines.append("Сеанс пересёк сброс: расход — нижняя оценка.")
        if self.today:
            lines.extend(
                [
                    f"Бюджет сегодня: {self.today['allocation']:.1f} п.п.; осталось {self.today['available']:.1f}",
                    f"Отметка плана: сохранить {self.today['expectedRemaining']:.1f}% к этому моменту.",
                    f"Отклонение: {abs(self.today['ahead']):.1f} п.п. "
                    + ("сверх плана" if self.today["ahead"] > 0 else "в запасе"),
                ]
            )
        total = self.data["summary"].get("lifetimeTokens") if self.data else None
        lines.extend(
            [
                "",
                "Токенов за всё время: " + (f"{total:,}".replace(",", " ") if total is not None else "нет данных"),
                "Лимит и токены — разные показатели.",
                "История хранится 7 дней. Разрывы — пропуски данных.",
                "Темп — среднее до 30 мин; прогноз приблизительный.",
                "Плановый остаток показан выше числом.",
                "Анимация: локальная работа или подтверждённое изменение лимита.",
                "Бюджет начинается с первого измерения дня.",
                "Уведомления: резкий расход, риск исчерпания, сброс.",
            ]
        )
        self.set_details_text("\n".join(lines))

    def show_notice(self, message):
        if self.popup:
            self.pending_notice = message
            return
        if self.toast:
            self.toast.destroy()
        x, y, width, height = side_geometry(
            (self.root.winfo_x(), self.root.winfo_y(), self.WIDTH, self.HEIGHT), self.api.monitors(), 294, 92
        )
        popup = tk.Toplevel(self.root)
        self.toast = popup
        popup.overrideredirect(True)
        popup.attributes("-topmost", self.topmost)
        popup.configure(bg=self.PANEL)
        popup.geometry(f"{width}x{height}+{x}+{y}")
        tk.Label(
            popup, text="Codex · уведомление", fg=self.FG, bg=self.PANEL, font=(FONT_FAMILY, -12, "bold"), anchor="w"
        ).pack(fill="x", padx=14, pady=(10, 3))
        label = tk.Label(
            popup,
            text=message,
            fg=self.MUTED,
            bg=self.PANEL,
            font=(FONT_FAMILY, -11),
            wraplength=width - 28,
            justify="left",
        )
        label.pack(anchor="w", padx=14)

        def dismiss(event=None):
            if self.toast is popup:
                popup.destroy()
                self.toast = None

        popup.bind("<Button-1>", dismiss)
        self.root.after(10000, dismiss)

    def close(self):
        self.api.STOP.set()
        self.api.REFRESH.set()
        self.save_settings()
        self.save_book()
        self.close_popup()
        if self.toast:
            self.toast.destroy()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        for _ in range(40):
            if threading.active_count() <= 1:
                break
            time.sleep(0.1)

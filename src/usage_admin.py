"""Visual local settings. Draft previews never change the user's subscription or live widget."""

from datetime import datetime
import time
import tkinter as tk
from PIL import Image, ImageTk
from usage_appearance import STYLES, THEMES, PROFILE_NAMES, FONT_FAMILY, FONT_SEMIBOLD, chart_explanation
from usage_presenter import render_static, compose_preview, demo_rows
from usage_analytics import MOSCOW


class SettingsPanel:
    def __init__(self, owner):
        self.owner = owner
        self.window = tk.Toplevel(owner.root)
        self.window.title("Настройки виджета · VLADMACC")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda event: self.close())
        screen = next((r for r in owner.api.monitors() if r[0] <= owner.root.winfo_x() < r[2]), owner.api.monitors()[0])
        width, height = min(1060, screen[2] - screen[0] - 48), min(820, screen[3] - screen[1] - 48)
        x, y = screen[0] + (screen[2] - screen[0] - width) // 2, screen[1] + (screen[3] - screen[1] - height) // 2
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.minsize(min(width, 880), min(height, 680))
        self.page, self.after_preview = "appearance", None
        self.photos, self.style_buttons = [], {}
        self.status = tk.StringVar(self.window, "Выберите оформление и нажмите «Применить»")
        self.vars = {
            "style": tk.StringVar(self.window, owner.ui_style),
            "theme": tk.StringVar(self.window, owner.theme),
            "profile": tk.StringVar(self.window, owner.profile),
            "history": tk.BooleanVar(self.window, owner.history_enabled),
            "activity": tk.BooleanVar(self.window, owner.activity_enabled),
            "animation": tk.BooleanVar(self.window, owner.animation),
            "topmost": tk.BooleanVar(self.window, owner.topmost),
            "opacity": tk.StringVar(self.window, str(round(owner.opacity * 100))),
            "alerts": tk.StringVar(self.window, str(owner.alert_interval)),
            "workdays": tk.BooleanVar(self.window, owner.book.workdays),
            "example": tk.StringVar(self.window, "account"),
        }
        self.rebuild()
        self.window.lift()

    def exists(self):
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def label(self, parent, text="", size=12, bold=False, color=None, **kw):
        return tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=color or self.p["fg"],
            font=(FONT_SEMIBOLD if bold else FONT_FAMILY, -size),
            **kw,
        )

    def button(self, parent, text, command, selected=False, **kw):
        spacing = {"padx": 12, "pady": 8}
        spacing.update(kw)
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.p["hover"] if selected else self.p["panel"],
            fg=self.p["fg"],
            activebackground=self.p["hover"],
            activeforeground=self.p["fg"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.p["border"],
            cursor="hand2",
            font=(FONT_FAMILY, -12),
            **spacing,
        )

    def checkbox(self, parent, text, name):
        return tk.Checkbutton(
            parent,
            text=text,
            variable=self.vars[name],
            command=self.changed,
            bg=parent.cget("bg"),
            fg=self.p["fg"],
            activebackground=parent.cget("bg"),
            activeforeground=self.p["fg"],
            selectcolor=self.p["panel"],
            font=(FONT_FAMILY, -12),
            bd=0,
            highlightthickness=0,
            anchor="w",
            cursor="hand2",
        )

    def logo(self, parent, size=(142, 66)):
        path = getattr(self.owner.api, "ASSETS", self.owner.api.BASE / "assets") / "vladmacc-logo.png"
        if path.exists():
            image = Image.open(path).convert("RGB")
            image.thumbnail(size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.photos.append(photo)
            tk.Label(parent, image=photo, bg="#000000", bd=0).pack(anchor="w")
        else:
            self.label(parent, "VLADMACC", 18, True).pack(anchor="w")

    def rebuild(self):
        if self.after_preview:
            self.window.after_cancel(self.after_preview)
            self.after_preview = None
        for child in self.window.winfo_children():
            child.destroy()
        self.photos, self.style_buttons = [], {}
        self.p = THEMES[self.vars["theme"].get()]
        self.window.configure(bg=self.p["bg"])
        header = tk.Frame(self.window, bg=self.p["bg"], padx=22, pady=16)
        header.pack(fill="x")
        self.label(header, "Настройки виджета", 23, True).pack(anchor="w")
        self.label(header, "Оформление, поведение и данные — в одном месте", 11, color=self.p["muted"]).pack(
            anchor="w", pady=(4, 0)
        )
        footer = tk.Frame(self.window, bg=self.p["panel"], padx=20, pady=10)
        footer.pack(side="bottom", fill="x")
        brand = tk.Frame(footer, bg=self.p["panel"])
        brand.pack(side="left")
        self.label(brand, "Сделано в дизайн-студии", 10, color=self.p["muted"]).pack(anchor="w", pady=(0, 3))
        self.logo(brand, (132, 61))
        actions = tk.Frame(footer, bg=self.p["panel"])
        actions.pack(side="right")
        self.apply_button = self.button(actions, "Применить", self.apply, selected=True)
        self.apply_button.pack(side="right", padx=(10, 0))
        self.button(actions, "Отмена", self.close).pack(side="right")
        self.label(footer, "", 10, color=self.p["muted"], textvariable=self.status, wraplength=300).pack(
            side="right", padx=22
        )
        body = tk.Frame(self.window, bg=self.p["bg"])
        body.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        navigation = tk.Frame(body, bg=self.p["bg"], width=150)
        navigation.pack(side="left", fill="y", padx=(0, 18))
        navigation.pack_propagate(False)
        for key, name in (
            ("appearance", "Оформление"),
            ("behavior", "Поведение"),
            ("data", "Лимиты и данные"),
            ("about", "О студии"),
        ):
            self.button(navigation, name, lambda k=key: self.navigate(k), selected=self.page == key, anchor="w").pack(
                fill="x", pady=(0, 8)
            )
        self.content = tk.Frame(body, bg=self.p["bg"])
        self.content.pack(side="left", fill="both", expand=True)
        getattr(self, "page_" + self.page)()

    def navigate(self, page):
        self.page = page
        self.rebuild()

    def changed(self):
        self.status.set("Изменения ещё не применены")
        self.schedule_preview()

    def select_style(self, style):
        self.vars["style"].set(style)
        self.status.set("Изменения ещё не применены")
        self.rebuild()

    def select_theme(self, theme):
        self.vars["theme"].set(theme)
        self.status.set("Изменения ещё не применены")
        self.rebuild()

    def set_example(self, example):
        self.vars["example"].set(example)
        self.schedule_preview()

    def page_appearance(self):
        controls = tk.Frame(self.content, bg=self.p["bg"])
        controls.pack(fill="x")
        self.label(controls, "Тема", 12, True).pack(side="left", padx=(0, 12))
        for key, title in (("dark", "Тёмная"), ("light", "Светлая")):
            self.button(
                controls, title, lambda k=key: self.select_theme(k), selected=self.vars["theme"].get() == key
            ).pack(side="left", padx=(0, 6))
        self.label(controls, "Размер", 12, True).pack(side="left", padx=(20, 8))
        self.profile_label = tk.StringVar(self.window, PROFILE_NAMES[self.vars["profile"].get()])
        profile = tk.OptionMenu(controls, self.profile_label, *PROFILE_NAMES.values())
        profile.configure(
            bg=self.p["panel"],
            fg=self.p["fg"],
            activebackground=self.p["hover"],
            font=(FONT_FAMILY, -12),
            bd=0,
            highlightthickness=0,
            width=20,
        )
        menu = profile["menu"]
        menu.delete(0, "end")
        for key, title in PROFILE_NAMES.items():
            menu.add_command(label=title, command=lambda k=key: (self.vars["profile"].set(k), self.changed()))
        # Keep the visible name friendly; the stored value remains stable for compatibility.
        self.profile_control = profile
        profile.pack(side="left")
        self.history_control = self.checkbox(self.content, "Показывать графики истории", "history")
        self.history_control.pack(anchor="w", pady=(12, 9))
        panes = tk.Frame(self.content, bg=self.p["bg"])
        panes.pack(fill="both", expand=True)
        cards = tk.Frame(panes, bg=self.p["bg"], width=220)
        cards.pack(side="left", fill="y", padx=(0, 20))
        cards.pack_propagate(False)
        now = time.time()
        for key, (title, description) in STYLES.items():
            frame = render_static(
                key,
                self.vars["theme"].get(),
                "horizontal",
                demo_rows(True, now),
                plan="plus",
                history=key == "telemetry",
                sync="Пример",
                now=now,
            )
            image = compose_preview(frame)
            image.thumbnail((202, 82), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.photos.append(photo)
            btn = tk.Button(
                cards,
                image=photo,
                text=title,
                compound="top",
                command=lambda k=key: self.select_style(k),
                bg=self.p["hover"] if self.vars["style"].get() == key else self.p["panel"],
                fg=self.p["fg"],
                activebackground=self.p["hover"],
                activeforeground=self.p["fg"],
                font=(FONT_FAMILY, -12),
                bd=0,
                highlightthickness=2,
                highlightbackground=self.p["fg"] if self.vars["style"].get() == key else self.p["border"],
                cursor="hand2",
                padx=6,
                pady=8,
            )
            btn.pack(fill="x", pady=(0, 10))
            self.style_buttons[key] = btn
        right = tk.Frame(panes, bg=self.p["bg"])
        right.pack(side="left", fill="both", expand=True)
        self.label(right, "Предпросмотр", 15, True).pack(anchor="w")
        examples = tk.Frame(right, bg=self.p["bg"])
        examples.pack(fill="x", pady=(8, 8))
        for key, title in (("account", "Мой аккаунт"), ("plus", "Пример Plus"), ("pro", "Пример Pro")):
            self.button(examples, title, lambda k=key: self.set_example(k), padx=6).pack(side="left", padx=(0, 4))
        self.preview_label = tk.Label(right, bg=self.p["panel"], bd=0)
        self.preview_label.bind("<Configure>", lambda event: self.schedule_preview())
        self.preview_caption = self.label(right, "", 10, color=self.p["muted"], wraplength=410, justify="left")
        self.label(
            right, chart_explanation(), 10, color=self.p["muted"], wraplength=410, justify="left", anchor="w"
        ).pack(side="bottom", fill="x", pady=(0, 4))
        self.preview_caption.pack(side="bottom", anchor="w", pady=(6, 5))
        self.preview_label.pack(fill="both", expand=True)
        self.schedule_preview()

    def schedule_preview(self):
        if not self.exists() or self.after_preview:
            return
        self.after_preview = self.window.after(90, self.render_preview)

    def render_preview(self):
        self.after_preview = None
        if not self.exists():
            return
        if self.page == "data":
            self.update_data()
            return
        if self.page != "appearance":
            return
        now, example = time.time(), self.vars["example"].get()
        if example == "account":
            rows, plan = self.owner.presentation_rows(self.vars["history"].get()), self.owner.subscription["plan"]
        else:
            rows, plan = demo_rows(example == "plus", now, self.owner.period), example
        self.preview_frame = render_static(
            self.vars["style"].get(),
            self.vars["theme"].get(),
            self.vars["profile"].get(),
            rows,
            plan=plan,
            history=self.vars["history"].get(),
            sync=self.owner.sync_text() if example == "account" else "Демонстрационные данные",
            activity=self.owner.activity_text() if example == "account" else "Пример",
            now=now,
            period=self.owner.period,
        )
        image = compose_preview(self.preview_frame)
        self.window.update_idletasks()
        max_w = max(220, self.preview_label.winfo_width() - 20)
        max_h = max(160, self.preview_label.winfo_height() - 16)
        scale = min(1, max_w / image.width, max_h / image.height)
        if scale < 1:
            image = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS
            )
        self.preview_photo = ImageTk.PhotoImage(image)
        self.preview_label.configure(image=self.preview_photo)
        source = "Текущий аккаунт" if example == "account" else "Только пример, подписка не меняется"
        self.preview_caption.configure(
            text=f"{source} · {self.preview_frame.image.width} × {self.preview_frame.image.height} px · масштаб {round(scale * 100)}%"
        )
        self.profile_label.set(PROFILE_NAMES[self.vars["profile"].get()])
        self.history_control.configure(state="disabled" if self.vars["profile"].get() == "mini" else "normal")

    def page_behavior(self):
        self.label(self.content, "Поведение виджета", 18, True).pack(anchor="w", pady=(4, 18))
        self.checkbox(self.content, "Поверх всех окон", "topmost").pack(anchor="w", pady=6)
        self.checkbox(self.content, "Анимация полосы", "animation").pack(anchor="w", pady=6)
        self.checkbox(self.content, "Быстрый отклик по локальным журналам Codex", "activity").pack(anchor="w", pady=6)
        self.label(
            self.content,
            "Необязательно. Читает технические маркеры начала/завершения работы,\n"
            "не сохраняет тексты чатов и не отправляет журналы. По умолчанию выключено.",
            10,
            color=self.p["muted"],
            justify="left",
        ).pack(anchor="w", pady=(0, 5))
        self.checkbox(self.content, "Распределять дневной бюджет только на будни", "workdays").pack(anchor="w", pady=6)
        for title, key, choices in (
            ("Непрозрачность, %", "opacity", ("100", "85", "70")),
            ("Интервал уведомлений, мин (0 — выключено)", "alerts", ("15", "30", "60", "0")),
        ):
            self.label(self.content, title, 12).pack(anchor="w", pady=(18, 7))
            menu = tk.OptionMenu(self.content, self.vars[key], *choices, command=lambda _: self.changed())
            menu.configure(
                bg=self.p["panel"],
                fg=self.p["fg"],
                activebackground=self.p["hover"],
                font=(FONT_FAMILY, -12),
                bd=0,
                highlightthickness=0,
            )
            menu.pack(anchor="w")
        self.label(
            self.content,
            "Опрос данных и расчёты продолжаются при выключенной анимации.\n"
            "Предпросмотр статичен; анимация проигрывается в виджете.\n"
            "Изменения вступят в силу после нажатия «Применить».",
            11,
            color=self.p["muted"],
            justify="left",
        ).pack(anchor="w", pady=(25, 0))

    def page_data(self):
        self.label(self.content, "Лимиты и данные", 18, True).pack(anchor="w", pady=(4, 18))
        self.data_label = self.label(self.content, "", 13, justify="left", anchor="nw", wraplength=650)
        self.data_label.pack(anchor="w")
        self.button(self.content, "Обновить данные", self.owner.refresh).pack(anchor="w", pady=22)
        self.label(self.content, chart_explanation(), 12, color=self.p["muted"], wraplength=650, justify="left").pack(
            anchor="w"
        )
        self.label(
            self.content,
            "Оформление не меняет подписку и не запускает запросы к модели.\n"
            "История хранится локально. Общие проценты разных окон не складываются.",
            11,
            color=self.p["muted"],
            justify="left",
        ).pack(anchor="w", pady=22)
        self.update_data()

    def update_data(self):
        if not self.exists() or self.page != "data":
            return
        plan = self.owner.subscription["plan"]
        updated = self.owner.data.get("updatedAt") if self.owner.data else None
        if getattr(self.owner.api, "STARTUP_ISSUE", None) == "codex_missing":
            self.data_label.configure(
                text="Для лимитов нужен установленный Codex.\n\n"
                "1. Установите официальный Codex для Windows.\n"
                "2. Откройте его и войдите в свой аккаунт ChatGPT.\n"
                "3. Перезапустите виджет. Отдельный Python устанавливать не нужно.\n\n"
                "Если Codex установлен нестандартно, укажите полный путь к codex.exe\n"
                "в переменной VLADMACC_CODEX_PATH и перезапустите виджет."
            )
            return
        lines = [
            "Подписка: " + (plan.title() if plan else "определяем"),
            "Последнее измерение: "
            + (datetime.fromtimestamp(updated, MOSCOW).strftime("%d.%m %H:%M:%S") if updated else "ожидаем"),
            "Фоновая работа: 0 модельных токенов",
            "",
        ]
        for row in self.owner.presentation_rows(False):
            lines.append(
                row["label"]
                + ": "
                + (f"осталось {row['remaining']:g}%" if row["remaining"] is not None else "нет измерения")
            )
        if self.owner.slot:
            primary, secondary = self.owner.forecast_text()
            session = self.owner.book.session_summary(self.owner.slot, time.time())
            lines.extend(
                [
                    "",
                    primary,
                    secondary,
                    f"Текущий сеанс: {session['spent']:.1f} п.п." + (" · нижняя оценка" if session["partial"] else ""),
                ]
            )
            if self.owner.today:
                lines.append(f"Доступно по плану сегодня: {self.owner.today['available']:.1f} п.п.")
        self.data_label.configure(text="\n".join(lines))

    def page_about(self):
        self.label(self.content, "VLADMACC", 24, True).pack(anchor="w", pady=(6, 18))
        self.logo(self.content, (300, 140))
        self.label(self.content, "Сделано в дизайн-студии VLADMACC", 16, True).pack(anchor="w", pady=(24, 10))
        self.label(
            self.content,
            "Локальный виджет лимитов Codex для Windows.\n\n"
            "Все варианты используют одну типографику: Segoe UI и Segoe UI Semibold — "
            "близкое системное воспроизведение первого концепта.\n\n"
            "Логотип предоставлен владельцем студии и используется без перерисовки.",
            12,
            color=self.p["muted"],
            wraplength=650,
            justify="left",
        ).pack(anchor="w")

    def values(self):
        return {
            "style": self.vars["style"].get(),
            "theme": self.vars["theme"].get(),
            "profile": self.vars["profile"].get(),
            "history": self.vars["history"].get(),
            "activity": self.vars["activity"].get(),
            "animation": self.vars["animation"].get(),
            "topmost": self.vars["topmost"].get(),
            "opacity": float(self.vars["opacity"].get()) / 100,
            "alerts": int(self.vars["alerts"].get()),
            "workdays": self.vars["workdays"].get(),
        }

    def apply(self):
        self.owner.apply_preferences(self.values())
        self.status.set("Сохранено. Виджет обновлён")
        self.schedule_preview()

    def close(self):
        if self.after_preview:
            self.window.after_cancel(self.after_preview)
            self.after_preview = None
        self.window.destroy()
        self.owner.admin = None

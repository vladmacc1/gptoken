"""One appearance model for the widget, previews and saved settings."""

FONT_FAMILY = "Segoe UI"
FONT_SEMIBOLD = "Segoe UI Semibold"
STYLES = {
    "minimal": ("Мягкий минимализм", "Крупные проценты и спокойные карточки"),
    "telemetry": ("Приборная панель", "Лимиты рядом, больше данных на одной панели"),
    "compact": ("Компактный", "Короткие строки и узкая батарейка"),
}
PROFILE_NAMES = {
    "horizontal": "Горизонтальный",
    "square": "Компактная карточка",
    "mini": "Батарейка · 60 px",
    "detailed": "Подробный",
}
THEMES = {
    "dark": {
        "bg": "#191d24",
        "panel": "#222833",
        "fg": "#f0f3f7",
        "muted": "#a4adbb",
        "dim": "#7d899b",
        "border": "#343c49",
        "hover": "#343e4e",
        "track": "#303843",
        "green": "#71ddb6",
        "yellow": "#edce68",
        "orange": "#f79a55",
        "red": "#f36f79",
    },
    "light": {
        "bg": "#ffffff",
        "panel": "#f1f4f7",
        "fg": "#1b2432",
        "muted": "#586778",
        "dim": "#6c7887",
        "border": "#d8dfe7",
        "hover": "#e4eaf1",
        "track": "#e2e7ed",
        "green": "#36b684",
        "yellow": "#d4ab39",
        "orange": "#df8b3f",
        "red": "#d95a69",
    },
}


def appearance_from_config(config):
    style = config.get("uiStyle", "minimal")
    theme = config.get("theme", "dark")
    return {
        "style": style if style in STYLES else "minimal",
        "theme": theme if theme in THEMES else "dark",
        "history": bool(
            config.get(
                "historyEnabled",
                config.get("profile", "horizontal" if config.get("compact", False) else "detailed") == "detailed",
            )
        ),
    }


def widget_size(style, profile, dual, history=False):
    style = style if style in STYLES else "minimal"
    if profile == "mini":
        return 60, 180
    if style == "minimal":
        width = 220 if profile == "square" else 382
        height = (306 if dual else 194) if profile != "square" else (332 if dual else 220)
    elif style == "telemetry":
        width = (300 if dual else 240) if profile == "square" else (442 if dual else 382)
        height = 244 if profile == "square" else 224
    else:
        width = 244 if profile == "square" else (380 if dual else 320)
        height = (258 if dual else 188) if profile == "square" else (212 if dual else 140)
    if profile == "detailed":
        width = max(width, 382 if style != "telemetry" else 442)
        height += 38
    if history:
        height += 96 if style == "telemetry" else ((100 if style == "compact" else 82) * (2 if dual else 1))
    return width, height


def chart_explanation():
    return (
        "Полоса — сколько лимита осталось сейчас. Линия истории — как остаток менялся со временем: "
        "выше означает больше запаса, падение — расход. Это не токены в секунду. "
        "Графики можно скрыть: сбор данных и расчёты продолжатся."
    )

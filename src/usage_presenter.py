"""Pure Pillow renderer shared by the actual widget and admin thumbnails."""

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from usage_appearance import THEMES, widget_size
from usage_pace import quota_band, reset_countdown
from usage_visuals import render_bar


@lru_cache(maxsize=64)
def ui_font(size, semibold=False):
    root = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    name = "seguisb.ttf" if semibold else "segoeui.ttf"
    if (root / name).exists():
        return ImageFont.truetype(str(root / name), size)
    if (root / "arial.ttf").exists():
        return ImageFont.truetype(str(root / "arial.ttf"), size)
    return ImageFont.load_default(size=size)


@dataclass
class Frame:
    image: Image.Image
    bars: list
    text_boxes: list


def service_color(theme, state):
    palette = THEMES.get(theme, THEMES["dark"])
    return palette[{"operational": "green", "degraded": "yellow", "outage": "red"}.get(state, "dim")]


def render_static(
    style,
    theme,
    profile,
    rows,
    plan=None,
    history=False,
    sync="",
    activity="",
    now=0,
    period=3600,
    service_state="unknown",
):
    p = THEMES.get(theme, THEMES["dark"])
    width, height = widget_size(style, profile, len(rows) > 1, history)
    im = Image.new("RGBA", (width, height))
    d = ImageDraw.Draw(im)
    radius = 10 if style == "telemetry" else 14
    d.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=p["bg"], outline=p["border"])
    bars, boxes = [], []

    def text(x, y, value, size=12, color=None, bold=False, anchor="lm", max_width=None):
        value = str(value)
        font = ui_font(size, bold)
        if max_width:
            while value and d.textlength(value, font=font) > max_width:
                value = value[:-2] + "…" if not value.endswith("…") else value[:-2] + "…"
                if value == "…":
                    break
        d.text((x, y), value, fill=color or p["fg"], font=font, anchor=anchor)
        boxes.append(d.textbbox((x, y), value, font=font, anchor=anchor))

    def bar(row, x, track_y, length, vertical=False, display_width=None):
        remaining = row.get("remaining")
        color = p[quota_band(remaining)] if remaining is not None and not row.get("muted") else p["dim"]
        bars.append(
            {
                "x": int(round(x)),
                "y": int(round(track_y if vertical else track_y - 12)),
                "width": length,
                "vertical": vertical,
                "displayWidth": display_width,
                "remaining": remaining or 0,
                "color": color,
                "track": p["track"],
                "mode": row.get("mode", "learning"),
                "valid": remaining is not None and not row.get("muted"),
            }
        )

    def history_chart(row, x, y, w, h=42):
        text(x, y - 9, "Остаток · " + ("1 ч" if period == 3600 else "24 ч" if period == 86400 else "7 дн"), 9, p["dim"])
        d.line((x, y + h, x + w, y + h), fill=p["border"])
        text(x, y + 3, "100%", 8, p["dim"])
        text(x, y + h - 3, "0%", 8, p["dim"])
        text(x + 32, y + h + 10, "Раньше", 8, p["dim"])
        text(x + w, y + h + 10, "Сейчас", 8, p["dim"], anchor="rm")
        for segment in row.get("segments", []):
            points = [
                (x + 31 + (t - now + period) / period * (w - 31), y + (100 - r) / 100 * h)
                for t, r in segment
                if now - period <= t <= now
            ]
            color = p[quota_band(row["remaining"])] if row.get("remaining") is not None else p["dim"]
            if len(points) > 1:
                d.line(points, fill=color, width=2)
            elif points:
                px, py = points[0]
                d.ellipse((px - 1, py - 1, px + 1, py + 1), fill=color)
        if not row.get("segments"):
            text(x + 32, y + h / 2, "Ждём измерения", 10, p["dim"], max_width=w - 32)

    if profile == "mini":
        d.ellipse((7, 7, 13, 13), fill=service_color(theme, service_state))
        count = len(rows)
        for i, row in enumerate(rows):
            center = 30 if count == 1 else (18, 42)[i]
            label = "5 ч" if row.get("duration") == 300 else "7 д"
            text(center, 19, label, 9, p["muted"], anchor="mm")
            percent = f"{row['remaining']:g}%" if row.get("remaining") is not None else "—"
            text(
                center,
                157,
                percent,
                19 if count == 1 else 11,
                p["muted"] if row.get("muted") else p["fg"],
                bold=True,
                anchor="mm",
            )
            photo_width = 38 if count == 1 else 24
            d.rectangle((center - 4, 29, center + 4, 32), fill=p["border"])
            bar(row, center - photo_width // 2, 36, 100, True, photo_width)
        return Frame(im, bars, boxes)

    title = "Codex" + (" · Plus" if plan == "plus" else " · Pro" if plan == "pro" else "")
    d.ellipse((14, 22, 22, 30), fill=service_color(theme, service_state))
    text(34, 26, title, 16, bold=True, max_width=width - 130)
    # The preview and real native header buttons use the same centres.
    for dx in (-6, 0, 6):
        d.ellipse((width - 28 + dx - 1, 25, width - 28 + dx + 1, 27), fill=p["muted"])
    d.arc((width - 71, 19, width - 57, 33), start=35, end=325, fill=p["muted"], width=2)
    if style == "telemetry":
        d.line((18, 48, width - 18, 48), fill=p["border"])
        count = len(rows)
        lane = (width - 36) / count
        for i, row in enumerate(rows):
            x, col_w = int(18 + i * lane), int(lane - (12 if count > 1 else 0))
            if i:
                d.line((x - 7, 62, x - 7, height - 42), fill=p["border"])
            text(x, 72, row["label"], 12, p["muted"])
            text(
                x,
                108,
                f"{row['remaining']:g}%" if row.get("remaining") is not None else "—",
                36,
                p["muted"] if row.get("muted") else p["fg"],
                bold=True,
            )
            bar(row, x, 139, col_w)
            reset = reset_countdown(row.get("reset"), now) if row.get("remaining") is not None else "Нет измерения"
            text(x, 182, reset.replace("До сброса ", "Сброс: "), 10, p["muted"], max_width=col_w)
            if history:
                history_chart(row, x, 215, col_w, 36)
    else:
        small = profile == "square"
        top = 62
        available = height - 101
        lane_h = available / len(rows)
        for i, row in enumerate(rows):
            y = top + i * lane_h
            max_w = width - 36
            if style == "minimal":
                text(18, y + 2, row["label"], 12, p["muted"])
                text(
                    width - 18,
                    y + 21,
                    f"{row['remaining']:g}%" if row.get("remaining") is not None else "—",
                    30,
                    p["muted"] if row.get("muted") else p["fg"],
                    bold=True,
                    anchor="rm",
                )
                bar(row, 18, y + 45, max_w)
                reset_y = y + 83
            else:
                text(18, y, row["label"], 11, p["muted"])
                if not small:
                    text(
                        width - 18,
                        y,
                        reset_countdown(row.get("reset"), now).replace("До сброса ", ""),
                        10,
                        p["muted"],
                        anchor="rm",
                        max_width=max_w - 78,
                    )
                text(
                    18,
                    y + 32,
                    f"{row['remaining']:g}%" if row.get("remaining") is not None else "—",
                    25,
                    p["muted"] if row.get("muted") else p["fg"],
                    bold=True,
                )
                bar(row, 91, y + 24, width - 109)
                reset_y = y + 67
            if style == "minimal" or small or row.get("remaining") is None:
                reset = (
                    reset_countdown(row.get("reset"), now)
                    if row.get("remaining") is not None
                    else "Ожидаем данные лимита"
                )
                text(18, reset_y, reset, 10, p["muted"], max_width=max_w)
            if history:
                chart_y = reset_y + 26
                history_chart(row, 18, chart_y, max_w, 32)
            if i and style == "minimal":
                d.line((18, y - 13, width - 18, y - 13), fill=p["border"])
    if profile == "detailed" and not history:
        text(18, height - 45, "История скрыта · расчёты продолжаются", 10, p["dim"], max_width=width - 36)
    if width >= 300:
        text(18, height - 18, activity, 9, p["dim"], max_width=(width - 36) // 2)
        text(width - 18, height - 18, sync, 9, p["dim"], anchor="rm", max_width=(width - 36) // 2)
    else:
        text(18, height - 18, sync, 9, p["dim"], max_width=width - 36)
    return Frame(im, bars, boxes)


def render_bar_spec(spec, phase=0, mode="still"):
    image = render_bar(
        spec["remaining"],
        spec["color"],
        mode,
        phase,
        width=spec["width"],
        vertical=spec["vertical"],
        track_color=spec["track"],
    )
    if spec.get("displayWidth"):
        image = image.resize((spec["displayWidth"], image.height), Image.Resampling.LANCZOS)
    return image


def compose_preview(frame):
    image = frame.image.copy()
    for spec in frame.bars:
        image.alpha_composite(render_bar_spec(spec), (int(spec["x"]), int(spec["y"])))
    return image


def demo_rows(dual=True, now=0, period=3600):
    result = []
    for duration, label, remaining, reset in (
        (300, "5 часов", 68, now + 9000),
        (10080, "Неделя", 42, now + 4.5 * 86400),
    ):
        if not dual and duration == 300:
            continue
        segment = [[now - period + j * period / 20, min(100, remaining + (20 - j) * 0.5)] for j in range(21)]
        result.append(
            {
                "duration": duration,
                "label": label,
                "remaining": remaining,
                "reset": reset,
                "mode": "calm",
                "segments": [segment],
            }
        )
    return result

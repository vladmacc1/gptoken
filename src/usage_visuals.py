"""Shared geometry and crisp, font-independent widget graphics."""

import math
from PIL import Image, ImageDraw

PROFILES = {
    "horizontal": (382, 156, "Горизонтальный · 382 × 156"),
    "square": (220, 220, "Квадратный · 220 × 220"),
    "mini": (60, 180, "Батарейка · 60 × 180"),
    "detailed": (382, 374, "Подробный · 382 × 374"),
}


def profile_from_config(config):
    value = config.get("profile")
    if value in PROFILES:
        return value
    return "horizontal" if config.get("compact", False) else "detailed"


def header_targets(profile, width, height=180):
    if profile == "mini":
        return {"menu": (0, 0, width, height)}
    return {
        "menu": (width - 46, 8, width - 10, 44),
        "refresh": (width - 82, 8, width - 46, 44),
        "limits": (98, 10, width - 88, 43) if width > 300 else (16, 174, width - 16, 213),
    }


def hit_target(profile, width, x, y, height=180):
    for name, (left, top, right, bottom) in header_targets(profile, width, height).items():
        if left <= x < right and top <= y < bottom:
            return name
    return None


def render_bar(remaining, color, mode, phase, width=346, vertical=False, track_color="#303843"):
    """Rectangular 24px fill; the same fluid/fire effect rotates with the battery."""
    scale, height = 2, 48 if not vertical else 40
    image = Image.new("RGBA", (width * scale, height * scale))
    d = ImageDraw.Draw(image)
    top = 12 if not vertical else 8
    y, bottom = top * scale, (top + 24) * scale - 1
    d.rectangle((0, y, width * scale - 1, bottom), fill=track_color)
    end = int(max(0, min(100, remaining)) / 100 * width * scale)
    if end:
        base = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
        # Thin columns are much cheaper than a full-window repaint.
        for x in range(0, end, 3):
            shimmer = 0.12 + 0.12 * math.sin(x / 55 - phase * 3) if mode != "still" else 0.06
            tint = tuple(int(c + (255 - c) * shimmer) for c in base)
            d.rectangle((x, y, min(x + 2, end - 1), bottom), fill=(*tint, 255))
        if mode in ("fire", "lava"):
            lava = mode == "lava"
            start, finish = max(0, end - 70), min(width * scale - 1, end + 24)
            for layer, color in enumerate(("#ef683f", "#ffb35b", "#fff0bb")):
                points = [(start, y + 10)]
                for i in range(33):
                    u = i / 32
                    wave = 0.7 + 0.2 * math.sin(u * 21 - phase * 7) + 0.1 * math.sin(u * 32 + phase * 3)
                    rise = math.sin(math.pi * u) ** 0.8 * wave * (22 if lava else 18) * (1 - layer * 0.27)
                    points.append((start + (finish - start) * u, y + 8 - rise))
                points.extend([(finish, y + 10), (start, y + 10)])
                d.polygon(points, fill=color)
            if lava:
                for i in range(4):
                    x = int((phase * 50 + i * 65) % max(1, end))
                    d.line((x, bottom - 8, min(end - 1, x + 24), y + 15), fill="#ffedb3", width=2)
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    return image.transpose(Image.Transpose.ROTATE_90) if vertical else image


def draw_icon(canvas, kind, x, y, color, phase=0):
    options = {"fill": color, "width": 1.8, "capstyle": "round", "tags": "text"}
    if kind == "menu":
        for dx in (-6, 0, 6):
            canvas.create_oval(x + dx - 1.5, y - 1.5, x + dx + 1.5, y + 1.5, fill=color, outline="", tags="text")
    elif kind == "refresh":
        start = 45 + phase * 180
        canvas.create_arc(
            x - 7, y - 7, x + 7, y + 7, start=start, extent=285, style="arc", outline=color, width=1.8, tags="text"
        )
        angle = math.radians(start)
        tx, ty = x + 7 * math.cos(angle), y - 7 * math.sin(angle)
        tangent = angle + math.pi / 2
        # Two short strokes join the arc; no font glyph or mismatched arrow character.
        for offset in (-0.65, 0.65):
            canvas.create_line(
                tx, ty, tx + 5 * math.cos(tangent + offset), ty - 5 * math.sin(tangent + offset), **options
            )

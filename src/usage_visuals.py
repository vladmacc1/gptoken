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
    """Clipped luminous ribbons; motion never changes the measured fill boundary."""
    scale, height = 2, 48 if not vertical else 40
    image = Image.new("RGBA", (width, height))
    d = ImageDraw.Draw(image)
    top = 12 if not vertical else 8
    d.rectangle((0, top, width - 1, top + 23), fill=track_color)
    end = int(max(0, min(100, remaining)) / 100 * width * scale)
    if end:
        base = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
        tint = tuple(int(c + (255 - c) * 0.06) for c in base)
        fill = Image.new("RGB", (end, 24 * scale), tint)
        if mode in ("fire", "lava"):
            _draw_ribbons(fill, base, phase, mode == "lava")
        # Resize the fill alone, then paste inside its boundary. Resampling an
        # entire animated image would leak coloured pixels into the empty track.
        fill = fill.resize(((end + 1) // scale, 24), Image.Resampling.LANCZOS)
        image.paste(fill, (0, top))
    return image.transpose(Image.Transpose.ROTATE_90) if vertical else image


def _draw_ribbons(fill, base, phase, intense):
    """Original CPU renderer: broad flowing bands with small bright cores.

    Only the tiny filled rectangle is drawn, without blur, shaders or a browser.
    Broad forms also survive the narrow battery's final downscale.
    """
    d = ImageDraw.Draw(fill)
    width, height = fill.size
    speed = phase * (3.2 if intense else 2.4)
    for x in range(0, width, 4):
        light = 0.68 + 0.22 * math.sin(x / 58 - speed)
        tint = tuple(int(c * light) for c in base)
        d.rectangle((x, 0, min(x + 3, width - 1), height - 1), fill=tint)

    # Two interweaving ribbons keep the whole fill alive, including at 100%.
    xs = list(range(-8, width + 8, 6))
    for ribbon in range(2):
        offset = ribbon * math.pi
        points = [
            (
                x,
                height / 2 + 12 * math.sin(x / 62 - speed + offset) + 5 * math.sin(x / 27 - speed * 0.7 + offset),
            )
            for x in xs
        ]
        for thickness, mix in ((23, 0.08), (13, 0.32), (5, 0.76), (2, 0.94)):
            tint = tuple(int(c + (255 - c) * mix) for c in base)
            d.line(points, fill=tint, width=thickness)

    # Short moving glints add direction without moving the quota endpoint.
    spacing = 170 if intense else 230
    travel = (phase * (135 if intense else 100)) % spacing
    for start in range(-spacing, width + spacing, spacing):
        head = start + travel
        points = [(head - 40, height - 3), (head - 20, height / 2), (head, 3)]
        d.line(points, fill=tuple(int(c + (255 - c) * 0.45) for c in base), width=8)
        d.line(points, fill=tuple(int(c + (255 - c) * 0.9) for c in base), width=3)


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

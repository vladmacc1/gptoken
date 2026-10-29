def side_geometry(widget, screens, width, height):
    """Keep a popup beside its owner, even near display edges or with negative x."""
    x, y, owner_w, owner_h = widget
    screen = next((s for s in screens if s[0] <= x + owner_w / 2 < s[2] and s[1] <= y + owner_h / 2 < s[3]), screens[0])
    gap, inset = 8, 8
    room_right = screen[2] - inset - (x + owner_w + gap)
    room_left = x - gap - (screen[0] + inset)
    right = room_right >= width or (room_left < width and room_right >= room_left)
    available = room_right if right else room_left
    if available < 1:
        raise ValueError("No horizontal room for side panel")
    width = min(width, int(available))
    height = min(height, screen[3] - screen[1] - inset * 2)
    px = x + owner_w + gap if right else x - gap - width
    py = max(screen[1] + inset, min(y, screen[3] - height - inset))
    return int(px), int(py), int(width), int(height)

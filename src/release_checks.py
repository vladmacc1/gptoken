"""Explicit offline diagnostics, usable inside the distributed executable."""

import hashlib
from pathlib import Path
import queue
import sys
import time
from app_runtime import RESOURCE_DIR, VERSION, write_json


def self_test(report, data_dir):
    from PIL import Image
    import tkinter
    from usage_presenter import render_static, compose_preview, demo_rows
    from usage_transport import AccountClient

    logo = RESOURCE_DIR / "assets" / "vladmacc-logo.png"
    Image.open(logo).verify()
    count = 0
    for style in ("minimal", "telemetry", "compact"):
        for theme in ("dark", "light"):
            for profile in ("horizontal", "square", "mini", "detailed"):
                for dual in (False, True):
                    for history in (False, True):
                        frame = render_static(
                            style,
                            theme,
                            profile,
                            demo_rows(dual, 1800000000),
                            plan="plus" if dual else "pro",
                            history=history,
                            now=1800000000,
                        )
                        compose_preview(frame)
                        count += 1
    result = {
        "ok": True,
        "version": VERSION,
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": sys.version.split()[0],
        "tcl": tkinter.TclVersion,
        "renderedCombinations": count,
        "logoSha256": hashlib.sha256(logo.read_bytes()).hexdigest(),
        "modelCallsAllowed": "turn/start" in AccountClient.ALLOWED_METHODS,
        "dataOutsideResources": not Path(data_dir).resolve().is_relative_to(RESOURCE_DIR.resolve()),
    }
    assert not result["modelCallsAllowed"] and result["dataOutsideResources"]
    write_json(report, result)
    return 0


def smoke_test(api, report):
    from usage_ui import Widget

    api.fetch_loop = lambda: None
    api.UPDATES = queue.Queue()
    api.save_json(
        api.CONFIG,
        {
            "profile": "horizontal",
            "uiStyle": "minimal",
            "theme": "dark",
            "activityEnabled": False,
            "alertInterval": 0,
            "x": 200,
            "y": 100,
        },
    )
    widget = Widget(api)
    errors = []
    widget.root.title("Codex Usage Widget · isolated packaging check")
    widget.root.report_callback_exception = lambda kind, value, tb: errors.append(str(kind))

    def pump(seconds=0.1):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            widget.root.update()
            time.sleep(0.005)

    try:
        now = time.time()
        windows = [
            {"windowDurationMins": 300, "usedPercent": 32, "resetsAt": now + 9000},
            {"windowDurationMins": 10080, "usedPercent": 58, "resetsAt": now + 4 * 86400},
        ]
        api.UPDATES.put(
            {
                "kind": "quota",
                "ok": True,
                "updatedAt": now,
                "bucket": "codex",
                "planType": "plus",
                "windows": windows,
                "summary": {},
            }
        )
        pump(0.2)
        assert widget.dual and not widget.activity_enabled
        for style in ("minimal", "telemetry", "compact"):
            for theme in ("dark", "light"):
                widget.apply_preferences({"style": style, "theme": theme, "history": False})
                pump(0.05)
                assert widget.theme == theme and widget.ui_style == style
        menu_checks = 0
        for profile in ("horizontal", "square", "detailed", "mini"):
            widget.apply_preferences({"profile": profile})
            pump(0.05)
            if profile == "mini":
                widget.canvas.event_generate("<Button-3>", x=20, y=20)
            else:
                button = widget.header_buttons["menu"]
                button.event_generate("<Enter>")
                pump(0.05)
                assert widget.popup is None  # Hover must not open the menu.
                button.invoke()
            pump()
            assert widget.popup and widget.popup.winfo_viewable()
            popup = widget.popup
            assert (
                popup.winfo_x() + popup.winfo_width() <= widget.root.winfo_x()
                or popup.winfo_x() >= widget.root.winfo_x() + widget.root.winfo_width()
            )
            widget.panel_close_button.invoke()
            pump(0.03)
            assert widget.popup is None
            if profile != "mini":
                widget.header_buttons["menu"].invoke()
                pump(0.03)
                widget.header_buttons["menu"].invoke()
                assert widget.popup is None
            menu_checks += 1
        widget.apply_preferences({"profile": "horizontal"})
        widget.header_buttons["refresh"].invoke()
        assert api.REFRESH.is_set()
        widget.header_buttons["menu"].invoke()
        pump()
        assert widget.popup and widget.popup.winfo_viewable()
        widget.panel_buttons["admin"].invoke()
        pump(0.3)
        assert widget.admin and widget.admin.exists()
        for page in ("appearance", "behavior", "data", "about"):
            widget.admin.navigate(page)
            pump(0.1)
        widget.admin.close()
        assert not errors
        write_json(
            report,
            {
                "ok": True,
                "version": VERSION,
                "frozen": bool(getattr(sys, "frozen", False)),
                "gui": True,
                "themes": 2,
                "styles": 3,
                "adminPages": 4,
                "menuProfiles": menu_checks,
                "menuHoverOpens": False,
                "sidePlacement": True,
                "nativeRefresh": True,
                "localActivityDefault": widget.activity_enabled,
                "callbackErrors": errors,
            },
        )
        return 0
    finally:
        widget.close()

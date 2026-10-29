"""Plan-aware presentation; never invent quota measurements."""

from usage_visuals import PROFILES


def normalize_plan(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    if value in ("pro", "prolite", "pro_lite", "pro_5x", "pro_20x"):
        return "pro"
    return value or None


def subscription_view(data):
    data = data or {}
    plan = normalize_plan(data.get("planType"))
    windows = [w for w in data.get("windows", []) if isinstance(w, dict)]
    by_duration = {w.get("windowDurationMins"): w for w in windows}
    if plan == "plus":
        durations = [300, 10080]
    elif plan == "pro":
        durations = [10080]
    else:
        durations = [d for d in (300, 10080) if d in by_duration]
        if not durations:
            durations = list(by_duration)[:2] or [10080]
    return {
        "plan": plan,
        "dual": len(durations) == 2,
        "slots": [
            {
                "duration": d,
                "label": "5 часов" if d == 300 else "Неделя" if d == 10080 else "Лимит",
                "window": by_duration.get(d),
            }
            for d in durations
        ],
    }


def profile_size(profile, dual=False):
    if not dual:
        return PROFILES[profile][:2]
    return {"horizontal": (382, 250), "square": (220, 324), "mini": (60, 314), "detailed": (382, 520)}[profile]

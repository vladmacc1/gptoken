"""Quota history and presentation rules. No account access or GUI side effects."""

import math

COLORS = {"green": "#71ddb6", "yellow": "#edce68", "orange": "#f79a55", "red": "#f36f79"}
MODE_NAMES = {
    "learning": "Измеряем темп",
    "idle": "Расхода пока нет",
    "calm": "Ровный темп",
    "elevated": "Темп выше нормы",
    "fire": "Быстрый расход",
    "lava": "Очень быстрый расход",
    "stale": "Нет свежих данных",
    "reset": "Ожидаем сброс",
    "empty": "Лимит исчерпан",
    "unknown": "Темп недоступен",
}


def quota_band(remaining):
    return "red" if remaining <= 15 else "orange" if remaining <= 40 else "yellow" if remaining <= 60 else "green"


def plural(n, one, few, many):
    return one if n % 10 == 1 and n % 100 != 11 else few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def reset_countdown(reset, now):
    if reset is None:
        return "Время сброса недоступно"
    seconds = max(0, reset - now)
    if seconds == 0:
        return "Ожидаем сброс лимита"
    if seconds < 60:
        return "До сброса менее 1 мин"
    days, hours = int(seconds // 86400), int(seconds % 86400 // 3600)
    if seconds < 3600:
        return f"До сброса {int(seconds // 60)} мин"
    if seconds < 86400:
        return f"До сброса {hours} ч {int(seconds % 3600 // 60)} мин"
    return f"До сброса {days} дн, {hours} {plural(hours, 'час', 'часа', 'часов')}"


class PaceHistory:
    def __init__(self, saved=None):
        self.key = None
        self.samples = []
        if isinstance(saved, dict):
            key = saved.get("key")
            if isinstance(key, list) and len(key) == 3:
                self.key = key
                for item in (saved.get("samples") or [])[-300:]:
                    if isinstance(item, list) and len(item) == 2:
                        self.add(item[0], item[1], key[2], key[1], key[0])

    def add(self, timestamp, used, reset, duration, bucket):
        try:
            timestamp, used = float(timestamp), float(used)
            reset = float(reset) if reset is not None else None
            if not all(math.isfinite(v) for v in (timestamp, used)) or not 0 <= used <= 100:
                return
            if reset is not None and not math.isfinite(reset):
                return
        except (TypeError, ValueError):
            return
        key = [bucket, duration, reset]
        if self.key != key:
            self.samples = []
            self.key = key
        if self.samples:
            last_t, last_used = self.samples[-1]
            if timestamp <= last_t:
                return
            if timestamp - last_t > 300 or used < last_used:
                self.samples = []
        self.samples.append([timestamp, used])
        cutoff = timestamp - 1800
        # Keep one sample before the cutoff for interpolation at exactly 30 minutes.
        while len(self.samples) > 2 and self.samples[1][0] <= cutoff:
            self.samples.pop(0)
        self.samples = self.samples[-300:]

    def evaluate(self, now, remaining, reset, failed=False):
        result = {"mode": "learning", "rate": None, "budget": None, "ratio": None, "spanMinutes": 0}
        if failed or (self.samples and now - self.samples[-1][0] > 300):
            result["mode"] = "stale"
            return result
        if reset is None:
            result["mode"] = "unknown"
            return result
        if reset <= now:
            result["mode"] = "reset"
            return result
        if remaining <= 0:
            result["mode"] = "empty"
            return result
        result["budget"] = remaining / ((reset - now) / 3600)
        if len(self.samples) < 3:
            return result
        end_t, end_used = self.samples[-1]
        start_t, start_used = self.samples[0]
        cutoff = end_t - 1800
        if start_t < cutoff:
            next_t, next_used = self.samples[1]
            start_used += (next_used - start_used) * (cutoff - start_t) / (next_t - start_t)
            start_t = cutoff
        span = end_t - start_t
        result["spanMinutes"] = span / 60
        if span < 240:
            return result
        rate = max(0, (end_used - start_used) / span * 3600)
        ratio = rate / result["budget"]
        mode = (
            "idle"
            if rate == 0
            else "calm"
            if ratio <= 1
            else "elevated"
            if ratio < 2
            else "fire"
            if ratio < 4
            else "lava"
        )
        result.update(mode=mode, rate=rate, ratio=ratio)
        return result

    def to_json(self):
        return {"key": self.key, "samples": self.samples}

from __future__ import annotations

import math


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def format_money(amount: float) -> str:
    if abs(amount - round(amount)) < 1e-9:
        return f"₹{int(round(amount))}"
    return f"₹{amount:.2f}"


def format_minutes(minutes: float) -> str:
    total = int(round(minutes))
    if total < 60:
        return f"{total} min"
    return f"{total // 60} h {total % 60:02d} min"


def format_distance(meters: float) -> str:
    if meters < 1000:
        return f"{int(round(meters))} m"
    return f"{meters / 1000:.2f} km"


def minutes_to_hhmm(minutes: float) -> str:
    total = int(round(minutes)) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def hhmm_to_minutes(value: str) -> int:
    hour, minute = value.strip().split(":")
    return int(hour) * 60 + int(minute)

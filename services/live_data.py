from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from urllib.request import urlopen

FEED_TIMEOUT_S = 5


@dataclass
class LiveStatus:
    source: str = "unavailable"
    delays: dict[str, float] = field(default_factory=dict)
    suspended: list[tuple[str, str, str]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    updated_at: str = ""

    @property
    def is_static(self) -> bool:
        return self.source != "live"

    @property
    def has_disruptions(self) -> bool:
        return bool(self.delays or self.suspended)


def _simulate(now: datetime) -> LiveStatus:
    slot = (now.hour + now.minute // 20) % 3
    status = LiveStatus(source="simulated", updated_at=now.strftime("%H:%M"))
    if slot == 0:
        status.delays = {"METRO_RED": 10.0}
        status.messages = ["Metro Red Line is running about 10 minutes late."]
    elif slot == 1:
        status.suspended = [("METRO_BLUE", "MGBS", "NAM")]
        status.messages = [
            "Metro Blue Line is suspended between MG Bus Station and Nampally; "
            "buses are the alternative."
        ]
    else:
        status.delays = {"BUS_8A": 8.0, "BUS_100": 6.0}
        status.messages = [
            "Bus 8A is delayed about 8 minutes and Bus 100 about 6 minutes by traffic."
        ]
    return status


def _from_payload(payload: dict, now: datetime) -> LiveStatus:
    status = LiveStatus(source="live", updated_at=now.strftime("%H:%M"))
    for service_id, minutes in (payload.get("delays") or {}).items():
        try:
            status.delays[str(service_id)] = float(minutes)
        except (TypeError, ValueError):
            continue
    for entry in payload.get("suspended") or []:
        if isinstance(entry, (list, tuple)) and len(entry) == 3:
            status.suspended.append((str(entry[0]), str(entry[1]), str(entry[2])))
    for message in payload.get("messages") or []:
        status.messages.append(str(message))
    return status


def fetch_live(url: str | None = None, simulate: bool = False) -> LiveStatus:
    now = datetime.now()
    if simulate:
        return _simulate(now)
    url = url or os.getenv("TRANSIT_LIVE_URL", "").strip()
    if not url:
        status = LiveStatus(source="unavailable", updated_at=now.strftime("%H:%M"))
        status.messages.append(
            "Live feed not configured — results use the latest static schedule (simulated)."
        )
        return status
    try:
        if url.startswith("file://"):
            from urllib.request import urlopen

            with urlopen(url, timeout=FEED_TIMEOUT_S) as response:
                data = response.read().decode("utf-8")
            return _from_payload(json.loads(data), now)
        try:
            import requests  # type: ignore

            response = requests.get(url, timeout=FEED_TIMEOUT_S)
            response.raise_for_status()
            return _from_payload(response.json(), now)
        except Exception:
            from urllib.request import urlopen

            with urlopen(url, timeout=FEED_TIMEOUT_S) as response:
                data = response.read().decode("utf-8")
            return _from_payload(json.loads(data), now)
    except Exception:
        status = LiveStatus(source="unavailable", updated_at=now.strftime("%H:%M"))
        status.messages.append(
            "Live feed unreachable — results use the latest static schedule."
        )
        return status

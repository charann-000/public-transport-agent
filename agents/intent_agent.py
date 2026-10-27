from __future__ import annotations

import re

from agents.base import LLMClient
from models.journey import Mode
from models.route import IntentResult, JourneyRequest
from utils.texting import find_deadline, find_departure

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
ALL_MODES = {"metro", "bus", "train"}
LOOKAHEAD = r"(?=\s+(?:before|by|tomorrow|today|tonight|at|with|keep|avoid|budget|around|on|prefer|leave|depart|please|pls|kindly|now)\b|[.,;!?]|$)"

ORIGIN_DEST_PATTERNS = [
    (re.compile(rf"\breach\s+(.+?)\s+from\s+(.+?){LOOKAHEAD}", re.I), (1, 0)),
    (re.compile(rf"\b(?:go|get(?:ting)?|travel|trip|journey)\s+to\s+(.+?)\s+from\s+(.+?){LOOKAHEAD}", re.I), (1, 0)),
    (re.compile(rf"\b(?:travel|trip|journey|go)\s+(?:from\s+)?(.+?)\s+to\s+(.+?){LOOKAHEAD}", re.I), (0, 1)),
    (re.compile(rf"\bfrom\s+(.+?)\s+to\s+(.+?){LOOKAHEAD}", re.I), (0, 1)),
    (re.compile(rf"\bto\s+(.+?)\s+from\s+(.+?){LOOKAHEAD}", re.I), (1, 0)),
    (re.compile(rf"^\s*(.+?)\s+to\s+(.+?){LOOKAHEAD}", re.I), (0, 1)),
]
BUDGET_PATTERNS = [
    r"(?:below|under|within|less than|no more than|not more than|more than|up to|at most)\s*(?:₹|rs\.?\s*|inr\s*|rupees?\s*)?(\d{1,4})(?!\s*(?:transfer|change|walk|station|km|meter|metre|minute|min\b))",
    r"(?:₹|rs\.?\s*|inr\s*|rupees?\s+)(\d{1,4})",
    r"(?:budget|fare|cost|price)(?:\s+(?:of|is|limit|cap))?\s*(?:₹|rs\.?|inr\s*|rupees?\s*)?(\d{1,4})(?!\s*(?:transfer|change|walk|station))",
]

TRANSFER_PATTERNS = [
    (re.compile(
        r"(?:avoid|no|without|limit)?\s*(?:more than|over|greater than)\s+"
        r"(one|two|three|four|five|\d+)\s*(?:transfer|change)s?", re.I), False),
    (re.compile(
        r"(?:max(?:imum)?|at most|up to|no more than|within|no greater than|under|"
        r"only|just)\s+(?:only\s+|just\s+)?(one|two|three|four|five|\d+)\s*"
        r"(?:transfer|change)s?", re.I), False),
    (re.compile(
        r"(one|two|three|four|five|\d+)\s*(?:transfer|change)s?\s+(?:or )?"
        r"(?:fewer|less|maximum|max|at most)", re.I), False),
    (re.compile(r"without\s+(?:any\s+|a\s+)?(?:extra\s+)?(?:transfer|change)s?", re.I), True),
    (re.compile(r"\bno\s+(?:transfer|change)s?\b", re.I), True),
    (re.compile(r"\b(?:direct|non[\s-]?stop|no changes)\b", re.I), True),
]

WALK_PATTERNS = [
    re.compile(
        r"(?:walk|walking|walkable)(?:\s+\w+){0,3}?\s*(\d+(?:\.\d+)?)\s*"
        r"(km|kilomet(?:er|re)s?|m|meters?|metres?)", re.I),
    re.compile(
        r"(?:within|under|below|max(?:imum)?|up to|no more than|less than)\s+"
        r"(\d+(?:\.\d+)?)\s*(km|kilomet(?:er|re)s?|m|meters?|metres?)\s+"
        r"(?:of\s+)?(?:walk|walking)", re.I),
]

ONLY_MODE_RE = re.compile(
    r"\b(?:only|just)\s+(metro|bus|train)(?:es|s)?\b|\b(metro|bus|train)(?:es|s)?\s+(?:only|alone)\b", re.I
)
EXCLUDE_MODE_RE = re.compile(
    r"\b(?:no|without|avoid|skip|don't)\s+(metro|bus|train)(?:es|s)?\b", re.I
)
LIST_MODE_RE = re.compile(r"\b(metro|bus|train)(?:es|s)?\b", re.I)
PREFER_RE = re.compile(r"\b(?:prefer|use|take|via|by|with|modes?|services?)\b", re.I)
AND_JUNCTION_RE = re.compile(r"\band\b|[,/]")

PRIORITY_KEYWORDS = [
    ("time", re.compile(r"\b(fastest|quickest|quick|in a hurry|hurry|least time|save time)\b", re.I)),
    ("fare", re.compile(r"\b(cheapest|lowest fare|least expensive|save money|cheap|budget-friendly)\b", re.I)),
    ("transfers", re.compile(r"\b(fewest transfer|least transfer|fewest change|least change|simplest)\b", re.I)),
    ("walk", re.compile(r"\b(least walking|minimi[sz]e walking|less walking|short walk|little walking)\b", re.I)),
    ("reliability", re.compile(r"\b(reliable|reliability|on[- ]time|punctual)\b", re.I)),
]

DATE_RE = re.compile(
    r"\b(today|tomorrow|tonight|day after tomorrow|"
    r"on\s+(?:mon|tues|wednes|thurs|fri|satur|sun)day)\b", re.I
)


def _token_to_int(token: str) -> int | None:
    token = token.lower()
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def _clean_place(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" .,!?;:")
    value = re.sub(
        r"\s+(?:before|by|tomorrow|today|tonight|at|with|keep|avoid|budget|prefer|leave|depart|please|pls|kindly|now)\b.*$",
        "", value, flags=re.I
    )
    return value.strip(" .,!?;:")


def parse_origin_destination(text: str) -> tuple[str | None, str | None]:
    for pattern, order in ORIGIN_DEST_PATTERNS:
        match = pattern.search(text)
        if match:
            origin = _clean_place(match.group(order[0] + 1))
            dest = _clean_place(match.group(order[1] + 1))
            if origin and dest and origin.lower() != dest.lower():
                return origin, dest
    return None, None


def parse_budget(text: str) -> float | None:
    for pattern in BUDGET_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            value = float(match.group(1))
            if 1 <= value <= 100000:
                return value
    return None


def parse_max_transfers(text: str) -> int | None:
    for pattern, zero in TRANSFER_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if zero:
            return 0
        value = _token_to_int(match.group(1))
        if value is not None and value <= 20:
            return value
    return None


def parse_max_walk(text: str) -> float | None:
    for pattern in WALK_PATTERNS:
        match = pattern.search(text)
        if match:
            value = float(match.group(1))
            unit = match.group(2).lower()
            meters = value * 1000 if unit.startswith("k") else value
            if 0 < meters <= 50000:
                return meters
    return None


def parse_modes(text: str) -> list[Mode] | None:
    excluded = {m.group(1).lower() for m in EXCLUDE_MODE_RE.finditer(text)}
    if excluded:
        kept = ALL_MODES - excluded
        return sorted(Mode(m) for m in kept) if kept else None
    only = ONLY_MODE_RE.search(text)
    if only:
        token = (only.group(1) or only.group(2) or "").lower().rstrip("s")
        if token in ALL_MODES:
            return [Mode(token)]
    if PREFER_RE.search(text) or AND_JUNCTION_RE.search(text):
        listed = {m.group(1).lower().rstrip("s") for m in LIST_MODE_RE.finditer(text)}
        listed &= ALL_MODES
        if listed:
            return [Mode(m) for m in sorted(listed)]
    return None


def parse_priorities(text: str, budget_found: bool, transfers_found: bool,
                     walk_found: bool) -> list[str]:
    priorities: list[str] = []
    for name, pattern in PRIORITY_KEYWORDS:
        if pattern.search(text):
            priorities.append(name)
    if budget_found and "fare" not in priorities:
        priorities.append("fare")
    if transfers_found and "transfers" not in priorities:
        priorities.append("transfers")
    if walk_found and "walk" not in priorities:
        priorities.append("walk")
    return priorities or ["balanced"]


def parse_date_note(text: str) -> str | None:
    match = DATE_RE.search(text)
    return match.group(0) if match else None


def rules_extract(request: JourneyRequest) -> JourneyRequest:
    text = request.text or ""
    if not text.strip():
        return request
    origin, dest = parse_origin_destination(text)
    if not request.origin and origin:
        request.origin = origin
    if not request.destination and dest:
        request.destination = dest
    if not request.arrival_deadline:
        request.arrival_deadline = find_deadline(text)
    if not request.departure_time:
        departure = find_departure(text)
        if departure and departure != request.arrival_deadline:
            request.departure_time = departure
    budget = parse_budget(text)
    if budget is not None and request.budget is None:
        request.budget = budget
    transfers = parse_max_transfers(text)
    if transfers is not None and request.max_transfers is None:
        request.max_transfers = transfers
    walk = parse_max_walk(text)
    if walk is not None and request.max_walk_m is None:
        request.max_walk_m = walk
    modes = parse_modes(text)
    if modes is not None and request.modes is None:
        request.modes = modes
    priorities = parse_priorities(
        text,
        budget_found=budget is not None,
        transfers_found=transfers is not None,
        walk_found=walk is not None,
    )
    merged = list(request.priorities)
    for item in priorities:
        if item not in merged:
            merged.append(item)
    request.priorities = merged
    if not request.date_note:
        request.date_note = parse_date_note(text)
    return request


LLM_SYSTEM = """You extract structured travel constraints from a natural language trip request.
Return ONLY a JSON object with these keys:
origin (string or null), destination (string or null),
departure_time ("HH:MM" 24h or null), arrival_deadline ("HH:MM" 24h or null),
budget (number or null), max_transfers (integer or null),
max_walk_m (number or null), modes (array of "metro"|"bus"|"train" or null),
priorities (array of "time"|"fare"|"transfers"|"walk"|"reliability"),
date_note (string or null).
Use null for anything not mentioned. Never invent values."""


def _coerce_llm(payload: dict, request: JourneyRequest) -> None:
    def as_str(value):
        return value if isinstance(value, str) and value.strip() else None

    def as_time(value):
        value = as_str(value)
        if value and re.match(r"^\d{1,2}:\d{2}$", value):
            hour, minute = value.split(":")
            if 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59:
                return f"{int(hour):02d}:{minute}"
        return None

    def as_number(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and re.match(r"^\d+(\.\d+)?$", value.strip()):
            return float(value)
        return None

    if payload.get("origin") and not request.origin:
        request.origin = as_str(payload["origin"]) or request.origin
    if payload.get("destination") and not request.destination:
        request.destination = as_str(payload["destination"]) or request.destination
    if request.departure_time is None:
        request.departure_time = as_time(payload.get("departure_time"))
    if request.arrival_deadline is None:
        request.arrival_deadline = as_time(payload.get("arrival_deadline"))
    if request.budget is None:
        request.budget = as_number(payload.get("budget"))
    if request.max_transfers is None:
        transfers = as_number(payload.get("max_transfers"))
        if transfers is not None and transfers >= 0:
            request.max_transfers = int(transfers)
    if request.max_walk_m is None:
        walk = as_number(payload.get("max_walk_m"))
        if walk is not None and walk > 0:
            request.max_walk_m = walk
    if request.modes is None and isinstance(payload.get("modes"), list):
        modes = []
        for item in payload["modes"]:
            value = str(item).lower().rstrip("s")
            if value in ALL_MODES and value not in modes:
                modes.append(value)
        if modes:
            request.modes = [Mode(m) for m in modes]
    if isinstance(payload.get("priorities"), list):
        allowed = {"time", "fare", "transfers", "walk", "reliability", "balanced"}
        for item in payload["priorities"]:
            value = str(item).lower().strip()
            if value in allowed and value not in request.priorities:
                request.priorities.append(value)
    if request.date_note is None:
        request.date_note = as_str(payload.get("date_note"))


class IntentAgent:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    def extract(self, request: JourneyRequest) -> IntentResult:
        request = rules_extract(request)
        source = "rules"
        if request.text and self.llm.available:
            payload = self.llm.complete_json(request.text, system=LLM_SYSTEM)
            if payload:
                _coerce_llm(payload, request)
                source = "llm"
        missing = []
        if not request.origin:
            missing.append("origin")
        if not request.destination:
            missing.append("destination")
        return IntentResult(request=request, source=source, missing=missing)

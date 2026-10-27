from __future__ import annotations

import re
from typing import Optional

STOP_ALIASES = {
    "hitec": "hitec city",
    "hitec city": "hitec city",
    "itec city": "hitec city",
    "lb nagar": "lb nagar",
    "l b nagar": "lb nagar",
    "mg bus station": "mg bus station",
    "mahatma gandhi bus station": "mg bus station",
    "mgb": "mg bus station",
    "mgbus": "mg bus station",
    "m g bus station": "mg bus station",
    "mgbs": "mg bus station",
    "ame": "ameerpet",
    "ameerpet": "ameerpet",
    "jbs": "jubilee bus station",
    "jubilee bus station": "jubilee bus station",
    "jubilee bus stand": "jubilee bus station",
    "secunderabad": "secunderabad",
    "secunderabad station": "secunderabad",
    "miyapur": "miyapur",
    "nagole": "nagole",
    "kphb colony": "kphb colony",
    "kphb": "kphb colony",
    "begumpet": "begumpet",
    "parade": "parade",
    "jubilee bus station": "jubilee bus station",
    "secunderabad": "secunderabad",
    "shah ali banda": "shah ali banda",
    "charminar": "charminar",
    "hyderabad deccan": "hyderabad deccan",
    "lakdikapul": "lakdikapul",
    "uppal": "uppal",
    "tarnaka": "tarnaka",
    "mettguda": "mettaguda",
    "mettaguda": "mettaguda",
}


def normalize_name(name: str) -> str:
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def match_stop(query: str) -> Optional[str]:
    key = normalize_name(query)
    if not key:
        return None
    if key in STOP_ALIASES:
        return STOP_ALIASES[key]
    best = None
    best_score = 0.5
    for k, v in STOP_ALIASES.items():
        if k in key or key in k:
            score = len(set(k.split()) & set(key.split())) / max(1, len(k.split()))
            if score > best_score:
                best = v
                best_score = score
    return best

TIME_PAT = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.|AM|PM|A\.M\.|P\.M\.)?", re.I)

def parse_time_token(token: str) -> str | None:
    m = TIME_PAT.search(token or '')
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    mer = (m.group(3) or '').lower().replace('.', '')
    if mer == 'pm' and hour < 12:
        hour += 12
    if mer == 'am' and hour == 12:
        hour = 0
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return f'{hour:02d}:{minute:02d}'

DEADLINE_RE = re.compile(r"(?:before|by|arrive(?:\s+by)?|reach(?:\s+by)?)\s+(?P<t>\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)", re.I)

def find_deadline(text: str) -> str | None:
    m = DEADLINE_RE.search(text or '')
    if not m:
        return None
    return parse_time_token(m.group('t'))

DEPART_RE = re.compile(r"(?:depart(?:ing)?|leave(?:ing)?|start(?:ing)?|board)\s*(?:at|by)?\s*(?P<t>\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)", re.I)
AT_RE = re.compile(r"at\s+(?P<t>\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)", re.I)

def find_departure(text: str) -> str | None:
    m = DEPART_RE.search(text or '')
    if not m:
        m = AT_RE.search(text or '')
    if not m:
        return None
    return parse_time_token(m.group('t'))

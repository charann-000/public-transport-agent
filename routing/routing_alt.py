from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from pathlib import Path
import csv

@dataclass
class Connection:
    dep_stop: str
    arr_stop: str
    dep_time: int  # minutes since midnight
    arr_time: int
    trip_id: str
    route_id: str

@dataclass
class TimetableRoute:
    route_id: str
    stops: list[str]

@dataclass
class Timetable:
    connections: list[Connection] = field(default_factory=list)
    routes: list[TimetableRoute] = field(default_factory=list)

def parse_time(s: str) -> int:
    h,m,sec = s.split(':')
    return int(h)*60 + int(m)

def load_gtfs(path: str) -> Timetable:
    tt = Timetable()
    p = Path(path)
    # load
    trips = {}
    if (p/'trips.txt').exists():
        with open(p/'trips.txt',encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                trips[r['trip_id']] = r['route_id']
    # stop_times
    if (p/'stop_times.txt').exists():
        with open(p/'stop_times.txt',encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
            rows.sort(key=lambda x: (x['trip_id'], int(x.get('stop_sequence','0'))))
            for i in range(len(rows)-1):
                a = rows[i]; b = rows[i+1]
                if a['trip_id'] == b['trip_id']:
                    tid = a['trip_id']
                    rid = trips.get(tid,'')
                    tt.connections.append(Connection(a['stop_id'], b['stop_id'], parse_time(a['departure_time']), parse_time(b['arrival_time']), tid, rid))
    return tt

from __future__ import annotations

from pathlib import Path
from typing import Optional

def load_gtfs_dir(path: str | Path | None = None) -> dict:
    p = Path(path) if path else Path('data/gtfs')
    if not p.exists():
        return {'stops': [], 'routes': [], 'trips': [], 'stop_times': []}
    # Load simple CSVs if present
    import csv
    res = {'stops': [], 'routes': [], 'trips': [], 'stop_times': []}
    for name, key in [('stops.txt','stops'), ('routes.txt','routes'), ('trips.txt','trips'), ('stop_times.txt','stop_times')]:
        f = p / name
        if f.exists():
            with open(f,encoding='utf-8-sig') as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    res[key].append(row)
    return res

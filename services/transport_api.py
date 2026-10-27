from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
GTFS_DIR = DATA_DIR / "gtfs"
NETWORK_FILE = DATA_DIR / "network.json"


class StopSpec(BaseModel):
    id: str
    name: str
    lat: float
    lon: float


class ServiceStopSpec(BaseModel):
    stop_id: str
    arrival_min: float = 0.0
    departure_min: float = 0.0

    @classmethod
    def from_obj(cls, obj: Any) -> "ServiceStopSpec":
        if isinstance(obj, dict):
            return cls.model_validate(obj)
        if isinstance(obj, str):
            return cls(stop_id=obj)
        if isinstance(obj, (list, tuple)) and obj:
            sid = str(obj[0])
            arr = float(obj[1]) if len(obj) > 1 else 0.0
            dep = float(obj[2]) if len(obj) > 2 else arr
            return cls(stop_id=sid, arrival_min=arr, departure_min=dep)
        raise TypeError(obj)


class ServiceSpec(BaseModel):
    id: str
    name: str
    mode: str
    route: List[str] = []
    stops: List[ServiceStopSpec] = []
    frequency_min: Optional[float] = None
    operator: Optional[str] = None
    reliability: float = 0.9


class NetworkSpec(BaseModel):
    stops: List[StopSpec]
    services: List[ServiceSpec]
    walk_links: List[Dict[str, Any]] = []


def _load_json(path: Path) -> Any:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def load_network_spec() -> dict:
    if NETWORK_FILE.exists():
        data = _load_json(NETWORK_FILE)
        services = data.get("services", []) or []
        for s in services:
            stops = s.get("stops", []) or []
            s["stops"] = [ServiceStopSpec.from_obj(x).model_dump() for x in stops]
        data["services"] = services
        return data
    return {"stops": [], "services": [], "walk_links": []}


def load_gtfs_dir(gtfs_dir: Path | None = None) -> NetworkSpec:
    base = Path(gtfs_dir) if gtfs_dir else GTFS_DIR
    if not base.exists():
        return load_network_spec()
    return load_network_spec()

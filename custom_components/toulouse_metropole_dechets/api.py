"""Public IGN address lookup and Toulouse OpenData collection routes."""

from __future__ import annotations

import hashlib
import json
import math
from itertools import pairwise
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import DATASETS

BASE_URL = "https://data.toulouse-metropole.fr/api/explore/v2.1/catalog/datasets"
GEOCODE_URL = "https://data.geopf.fr/geocodage/search"


class ApiError(Exception):
    """An upstream service could not supply valid data."""


def record_key(record: dict) -> str:
    """Identify a street segment independently of its collection rule."""
    shape = record.get("geo_shape") or {}
    raw = json.dumps(
        [record.get("libelle_voie"), shape.get("geometry")], sort_keys=True
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _coordinate(value: Any, limit: float) -> bool:
    """Check JSON coordinates before arithmetic or constructing a query."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and -limit <= value <= limit
    )


def distance_to_shape(record: dict, lat: float, lon: float) -> float:
    """Point-to-segment distance in metres, using a local tangent plane."""
    shape = record.get("geo_shape")
    if not isinstance(shape, dict) or not isinstance(shape.get("geometry"), dict):
        return float("inf")
    geometry = shape["geometry"]
    lines = geometry.get("coordinates", [])
    if geometry.get("type") == "LineString":
        lines = [lines]
    elif geometry.get("type") != "MultiLineString":
        return float("inf")
    scale_x = 111_320 * math.cos(math.radians(lat))
    scale_y = 111_320
    best = float("inf")
    if not isinstance(lines, list):
        return best
    for line in lines:
        if not isinstance(line, list) or len(line) < 2:
            return float("inf")
        if any(
            not isinstance(point, list)
            or len(point) < 2
            or not _coordinate(point[0], 180)
            or not _coordinate(point[1], 90)
            for point in line
        ):
            return float("inf")
        for a, b in pairwise(line):
            ax, ay = (a[0] - lon) * scale_x, (a[1] - lat) * scale_y
            bx, by = (b[0] - lon) * scale_x, (b[1] - lat) * scale_y
            dx, dy = bx - ax, by - ay
            norm = dx * dx + dy * dy
            t = max(0, min(1, -(ax * dx + ay * dy) / norm)) if norm else 0
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


class ToulouseApi:
    """Asynchronous client with an injected Home Assistant HTTP session."""

    def __init__(self, session: ClientSession) -> None:
        self.session = session

    async def _get(self, url: str, params: dict) -> dict[str, Any]:
        try:
            async with self.session.get(
                url, params=params, timeout=ClientTimeout(total=25)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            if not isinstance(data, dict) or data.get("error_code"):
                raise ApiError("Réponse inattendue du service public")
            return data
        except (TimeoutError, ClientError, ValueError) as err:
            raise ApiError("Service public indisponible") from err

    async def addresses(self, query: str) -> list[dict]:
        data = await self._get(GEOCODE_URL, {"q": query, "limit": 5})
        addresses = []
        features = data.get("features")
        if not isinstance(features, list):
            raise ApiError("Schéma de géocodage modifié")
        for feature in features:
            if not isinstance(feature, dict):
                raise ApiError("Schéma de géocodage modifié")
            props = feature.get("properties")
            geometry = feature.get("geometry")
            if not isinstance(props, dict) or not isinstance(geometry, dict):
                raise ApiError("Schéma de géocodage modifié")
            if props.get("type") not in {"housenumber", "street"}:
                continue
            coordinates = geometry.get("coordinates")
            if (
                geometry.get("type") != "Point"
                or not isinstance(coordinates, list)
                or len(coordinates) != 2
                or not _coordinate(coordinates[0], 180)
                or not _coordinate(coordinates[1], 90)
                or not isinstance(props.get("label"), str)
                or not props["label"]
                or not isinstance(props.get("id"), str)
                or not props["id"]
            ):
                raise ApiError("Schéma de géocodage modifié")
            addresses.append(
                {
                    "label": props["label"],
                    "id": props["id"],
                    "citycode": props.get("citycode", ""),
                    "latitude": coordinates[1],
                    "longitude": coordinates[0],
                }
            )
        return addresses

    async def routes(self, stream: str, lat: float, lon: float) -> list[dict]:
        if not _coordinate(lat, 90) or not _coordinate(lon, 180):
            raise ApiError("Coordonnées invalides")
        url = f"{BASE_URL}/{DATASETS[stream]}/records"
        rows = []
        for offset in range(0, 1000, 100):
            data = await self._get(
                url,
                {
                    "where": f"within_distance(geo_shape, geom'POINT({lon} {lat})', 150m)",
                    "limit": 100,
                    "offset": offset,
                },
            )
            total_count = data.get("total_count")
            if (
                not isinstance(data.get("results"), list)
                or not isinstance(total_count, int)
                or isinstance(total_count, bool)
                or total_count < 0
            ):
                raise ApiError("Schéma de données modifié")
            rows.extend(data["results"])
            if len(rows) >= total_count:
                break
            if not data["results"]:
                raise ApiError("Page de données incomplète")
        else:
            raise ApiError("Trop de tronçons : préciser l’adresse")
        result = []
        for row in rows:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("libelle_voie"), str)
                or not row["libelle_voie"]
                or not isinstance(row.get("infobulle_pdi"), str)
            ):
                raise ApiError("Schéma de données modifié")
            distance = distance_to_shape(row, lat, lon)
            if not math.isfinite(distance):
                raise ApiError("Géométrie de collecte invalide")
            result.append(
                {
                    "key": record_key(row),
                    "street": row["libelle_voie"],
                    "rule": row["infobulle_pdi"],
                    "distance": round(distance),
                    "source_url": f"https://data.toulouse-metropole.fr/explore/dataset/{DATASETS[stream]}/",
                }
            )
        return sorted(result, key=lambda route: route["distance"])

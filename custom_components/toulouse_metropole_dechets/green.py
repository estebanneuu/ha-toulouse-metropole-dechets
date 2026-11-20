"""Official Toulouse Métropole garden-waste sectors and dated collections.

The public map returns exact seasonal dates and a fortnightly paid rule. Paid
rules also depend on the annual exceptions PDF; never extrapolate that PDF to a
new year. The 2026 PDF was checked on 20 November 2026, including its map legend.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import aiohttp

MAP_URL = "https://carto.toulouse.fr/PDI/?context=Gqmf"
API_URL = "https://carto.toulouse.fr/PDI/services/aas/v1"
APPLICATION_ID = "724214d6-b9f5-11e9-943b-f9610daa8d23"
DEFAULT_SEARCH_ID = "7e7a3ad9-1620-11f1-92ed-5d0ff281562c"
PAID_CALENDAR_URL = (
    "https://metropole.toulouse.fr/sites/toulouse-fr/files/2026-02/"
    "telecharger_le_calendrier_des_collectes_pour_les_abonnes_forfait_payant_"
    "05.02.2026_1.pdf"
)
PAID_VALID_UNTIL = date(2026, 12, 31)
WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi")


class GreenError(Exception):
    """Garden-waste data could not be obtained or interpreted safely."""


class GreenAmbiguousArea(GreenError):
    """A location intersects several different collection schedules."""


class GreenSchemaError(GreenError):
    """The public map no longer exposes the expected schema."""


@dataclass(frozen=True)
class GreenSchedule:
    """A sector's published schedule, with strictly bounded annual validity."""

    sector_id: str
    raw: str
    seasonal_dates: tuple[date, ...]
    paid_weekday: int
    paid_parity: int

    def valid_until(self, plan: str) -> date:
        """Last date covered by the published annual calendar."""
        if plan == "seasonal":
            return date(max(day.year for day in self.seasonal_dates), 12, 31)
        if plan == "paid":
            return min(PAID_VALID_UNTIL, self.valid_until("seasonal"))
        raise ValueError(f"Unsupported garden-waste plan: {plan}")

    def dates(self, plan: str, start: date, end: date) -> tuple[date, ...]:
        """Return collections in [start, end), without inventing future dates.

        Paid subscribers also receive the six seasonal collections. For 2026,
        the paid calendar starts on 5 January. There is no paid collection from
        10 through 21 August or from 21 December through 1 January 2027; the
        1 May collection is moved to 2 May. These exceptions are year-specific.
        """
        valid_until = self.valid_until(plan)
        stop = min(end, valid_until + timedelta(days=1))
        if start >= stop:
            return ()
        days = {day for day in self.seasonal_dates if start <= day < stop}
        if plan == "seasonal":
            return tuple(sorted(days))

        # The rule belongs to the year in the current map's seasonal dates.
        # If the map switches to 2027, do not apply it to the 2026 PDF either.
        if 2026 not in {day.year for day in self.seasonal_dates}:
            return ()
        cursor = max(start - timedelta(days=1), date(2026, 1, 5))
        while cursor < stop:
            if (
                cursor.weekday() == self.paid_weekday
                and cursor.isocalendar().week % 2 == self.paid_parity
                and not date(2026, 8, 10) <= cursor <= date(2026, 8, 21)
                and cursor < date(2026, 12, 21)
            ):
                collection = date(2026, 5, 2) if cursor == date(2026, 5, 1) else cursor
                if start <= collection < stop:
                    days.add(collection)
            cursor += timedelta(days=1)
        return tuple(sorted(days))


def parse_schedule(feature: dict[str, Any]) -> GreenSchedule:
    """Parse only the map's explicit known format; reject unexpected text."""
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise GreenSchemaError("Missing garden-waste feature properties")
    raw = properties.get("infobulle")
    if not isinstance(raw, str):
        raise GreenSchemaError("Missing garden-waste schedule text")
    lines = [line.strip() for line in raw.replace("\r", "").split("\n") if line.strip()]
    paid = [line for line in lines if line.casefold().startswith("forfait payant")]
    seasonal = [line for line in lines if line.casefold().startswith("forfait gratuit")]
    if len(paid) != 1 or len(seasonal) != 1:
        raise GreenSchemaError("Expected one paid and one seasonal schedule")
    match = re.fullmatch(
        r"Forfait payant\s*:\s*(lundi|mardi|mercredi|jeudi|vendredi)\s+"
        r"semaine\s+(impaire|paire)",
        paid[0],
        re.IGNORECASE,
    )
    if match is None:
        raise GreenSchemaError("Unsupported paid garden-waste rule")
    tokens = re.findall(r"\b(\d{2})/(\d{2})/(\d{4})\b", seasonal[0])
    try:
        dates = tuple(sorted({date(int(y), int(m), int(d)) for d, m, y in tokens}))
    except ValueError as err:
        raise GreenSchemaError("Invalid seasonal collection date") from err
    if not dates:
        raise GreenSchemaError("No explicit seasonal collection dates")
    return GreenSchedule(
        sector_id=str(properties.get("oid", feature.get("id", ""))),
        raw=raw,
        seasonal_dates=dates,
        paid_weekday=WEEKDAYS.index(match[1].casefold()),
        paid_parity=1 if match[2].casefold() == "impaire" else 0,
    )


class GreenClient:
    """Read the public map through the caller's shared aiohttp session."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._search_id = DEFAULT_SEARCH_ID

    async def async_schedule(
        self, latitude: float, longitude: float
    ) -> GreenSchedule | None:
        """Return the containing sector, None outside coverage, or an error.

        The map's point-in-polygon query is used directly; a nearby centroid
        must never be used as proof that an address belongs to a sector.
        """
        if not (
            math.isfinite(latitude)
            and math.isfinite(longitude)
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            raise ValueError("Invalid coordinates")
        try:
            try:
                payload = await self._query(latitude, longitude)
            except (GreenSchemaError, aiohttp.ClientResponseError) as err:
                if isinstance(err, aiohttp.ClientResponseError) and err.status not in (
                    400,
                    404,
                ):
                    raise
                await self._rediscover_search()
                payload = await self._query(latitude, longitude)
            features = payload["features"]
            if not features:
                return None
            schedules = [parse_schedule(feature) for feature in features]
            signatures = {
                (item.seasonal_dates, item.paid_weekday, item.paid_parity)
                for item in schedules
            }
            if len(signatures) != 1:
                raise GreenAmbiguousArea(
                    "Several garden-waste sectors match this location"
                )
            return schedules[0]
        except (
            TimeoutError,
            aiohttp.ClientError,
            ValueError,
            KeyError,
            TypeError,
        ) as err:
            raise GreenError("Cannot read the official garden-waste map") from err

    async def _query(self, latitude: float, longitude: float) -> dict[str, Any]:
        data = {
            "searchIds": self._search_id,
            "srid": "4326",
            "useExtent": "true",
            "limit": "100",
            "offset": "0",
            "centroid": "true",
            "simplifyGeometry": "false",
            "filters": "{}",
            "spatialFilter": json.dumps(
                {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                    "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
                }
            ),
        }
        async with self._session.post(
            f"{API_URL}/searches/execute",
            data=data,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            response.raise_for_status()
            payload = await response.json()
        if not isinstance(payload, dict) or not isinstance(
            payload.get("features"), list
        ):
            raise GreenSchemaError("Unexpected map response")
        if len(payload["features"]) >= 100:
            raise GreenSchemaError("Spatial query may have been truncated")
        return payload

    async def _rediscover_search(self) -> None:
        """Find the public search again if a map publication changes its ID."""
        async with self._session.get(
            f"{API_URL}/applications/getApplicationDescriptor",
            params={"id": APPLICATION_ID, "translationKey": "fr"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            response.raise_for_status()
            payload = await response.json()
        if not isinstance(payload, dict) or not isinstance(
            payload.get("results"), dict
        ):
            raise GreenSchemaError("Unexpected map descriptor")
        matches = []
        for resource in payload["results"].values():
            value = resource.get("value", {})
            if (
                value.get("@type") == "com.bg.functionality.search.Search"
                and value.get("name") == "Collecte déchets verts"
                and isinstance(value.get("id"), str)
            ):
                matches.append(value["id"])
        if len(matches) != 1:
            raise GreenSchemaError("Cannot identify the garden-waste search")
        self._search_id = matches[0]

"""Garden-waste calendar regression tests using a real public map response."""

import asyncio
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

_PATH = (
    Path(__file__).parents[1] / "custom_components/toulouse_metropole_dechets/green.py"
)
_SPEC = importlib.util.spec_from_file_location("toulouse_green_test", _PATH)
green = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = green
_SPEC.loader.exec_module(green)
FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/green_sectors_2026.json").read_text()
)


def test_all_public_sectors_parse_and_have_six_explicit_seasonal_dates():
    assert len(FIXTURE["features"]) == 46
    for feature in FIXTURE["features"]:
        schedule = green.parse_schedule(feature)
        assert len(schedule.seasonal_dates) == 6
        assert schedule.valid_until("seasonal") == date(2026, 12, 31)
        assert schedule.valid_until("paid") == date(2026, 12, 31)
        assert len(schedule.dates("paid", date(2026, 1, 1), date(2027, 1, 1))) == 30


def test_paid_year_boundaries_and_summer_pause():
    schedule = green.parse_schedule(FIXTURE["features"][5])  # Friday, odd weeks
    days = schedule.dates("paid", date(2025, 1, 1), date(2028, 1, 1))
    assert min(days) == date(2026, 1, 16)
    assert max(days) == date(2026, 12, 18)
    assert not any(date(2026, 8, 10) <= day <= date(2026, 8, 21) for day in days)
    assert not any(day.year != 2026 for day in days)
    assert schedule.dates("paid", date(2027, 1, 1), date(2028, 1, 1)) == ()


def test_labour_day_is_reported_and_preserved_when_window_starts_on_replacement():
    schedule = green.parse_schedule(FIXTURE["features"][17])  # Friday, even weeks
    assert schedule.dates("paid", date(2026, 5, 1), date(2026, 5, 3)) == (
        date(2026, 5, 2),
    )
    assert schedule.dates("paid", date(2026, 5, 2), date(2026, 5, 3)) == (
        date(2026, 5, 2),
    )
    assert schedule.dates("paid", date(2026, 5, 1), date(2026, 5, 2)) == ()


def test_seasonal_dates_keep_nonstandard_rescheduled_weekday():
    schedule = green.parse_schedule(FIXTURE["features"][25])
    assert schedule.dates("seasonal", date(2026, 4, 1), date(2026, 5, 1)) == (
        date(2026, 4, 29),
    )


def test_future_seasonal_dates_do_not_authorize_new_paid_recurrence():
    feature = json.loads(json.dumps(FIXTURE["features"][0]))
    feature["properties"]["infobulle"] = feature["properties"]["infobulle"].replace(
        "2026", "2027"
    )
    schedule = green.parse_schedule(feature)
    assert schedule.valid_until("seasonal") == date(2027, 12, 31)
    assert schedule.valid_until("paid") == date(2026, 12, 31)
    assert len(schedule.dates("seasonal", date(2027, 1, 1), date(2028, 1, 1))) == 6
    assert schedule.dates("paid", date(2026, 1, 1), date(2028, 1, 1)) == ()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Forfait payant : Lundi\nForfait gratuit : 05/03/2026",
        "Forfait payant : Lundi semaine PAIRE\nForfait gratuit : 31/02/2026",
        "Forfait payant : Lundi semaine PAIRE sauf fêtes\nForfait gratuit : 05/03/2026",
    ],
)
def test_unsupported_schedule_is_rejected(text):
    with pytest.raises(green.GreenSchemaError):
        green.parse_schedule({"properties": {"infobulle": text}})


class Response:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    async def json(self):
        return self.payload


class Session:
    def __init__(self, features):
        self.features = features
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response({"type": "FeatureCollection", "features": self.features})


def test_client_queries_actual_point_and_does_not_choose_nearest_centroid():
    session = Session([FIXTURE["features"][4]])
    result = asyncio.run(green.GreenClient(session).async_schedule(43.6045, 1.4442))
    assert result.sector_id == "5"
    query = session.calls[0][1]["data"]
    assert json.loads(query["spatialFilter"])["coordinates"] == [1.4442, 43.6045]
    assert json.loads(query["spatialFilter"])["type"] == "Point"
    assert query["useExtent"] == "true"


def test_outside_coverage_returns_none():
    assert (
        asyncio.run(green.GreenClient(Session([])).async_schedule(48.85, 2.35)) is None
    )


def test_ambiguous_sector_boundary_does_not_choose_first_result():
    session = Session(FIXTURE["features"][:2])
    with pytest.raises(green.GreenAmbiguousArea):
        asyncio.run(green.GreenClient(session).async_schedule(43.6, 1.4))


def test_network_failure_is_reported():
    class Offline(Session):
        def post(self, *args, **kwargs):
            raise green.aiohttp.ClientConnectionError("offline")

    with pytest.raises(green.GreenError):
        asyncio.run(green.GreenClient(Offline([])).async_schedule(43.6, 1.4))

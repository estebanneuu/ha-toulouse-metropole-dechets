"""Validate public API responses and selection by street geometry."""

import math
from copy import deepcopy
from types import SimpleNamespace

import aiohttp
import pytest
from aioresponses import aioresponses
from yarl import URL

from custom_components.toulouse_metropole_dechets.api import (
    BASE_URL,
    GEOCODE_URL,
    ApiConnectionError,
    ApiDataError,
    ApiError,
    ToulouseApi,
    distance_to_shape,
    record_key,
)
from custom_components.toulouse_metropole_dechets.const import DATASETS

LAT, LON = 43.6, 1.4


@pytest.fixture(autouse=True)
def mock_response_compatibility(monkeypatch):
    """Bridge aioresponses' constructor to HA's newer aiohttp response API."""

    class CompatibleResponse(aiohttp.ClientResponse):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("aioresponses.core.ClientResponse", CompatibleResponse)


def record(street="Rue test", *, latitude=LAT, rule="Lundi"):
    return {
        "libelle_voie": street,
        "infobulle_pdi": rule,
        "geo_shape": {
            "type": "Feature",
            "geometry": {
                "type": "MultiLineString",
                "coordinates": [[[LON, latitude], [LON + 0.01, latitude]]],
            },
            "properties": {},
        },
        "geo_point_2d": {"lon": LON + 0.005, "lat": latitude},
    }


def routes_url(offset=0):
    return str(
        URL(f"{BASE_URL}/{DATASETS['om']}/records").with_query(
            where=f"within_distance(geo_shape, geom'POINT({LON} {LAT})', 150m)",
            limit=100,
            offset=offset,
        )
    )


def address_feature():
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [LON, LAT]},
        "properties": {
            "type": "housenumber",
            "label": "1 Place du Capitole 31000 Toulouse",
            "id": "31555_1676_00001",
            "citycode": "31555",
        },
    }


def test_distance_uses_segment_not_its_centroid():
    row = record()
    assert distance_to_shape(row, LAT, LON) == pytest.approx(0)
    assert distance_to_shape(row, LAT + 0.0001, LON) == pytest.approx(11.132)
    row["geo_shape"]["geometry"] = {
        "type": "LineString",
        "coordinates": [[LON, LAT], [LON, LAT]],
    }
    assert distance_to_shape(row, LAT, LON) == 0


def test_record_key_survives_rule_centroid_and_feature_property_changes():
    original = record()
    changed = deepcopy(original)
    changed["infobulle_pdi"] = "Jeudi"
    changed["geo_point_2d"]["lat"] += 0.00001
    changed["geo_shape"]["properties"]["updated"] = "2026-11-20"
    assert record_key(original) == record_key(changed)
    changed["geo_shape"]["geometry"]["coordinates"][0][0][0] += 0.00001
    assert record_key(original) != record_key(changed)


@pytest.mark.parametrize(
    "shape",
    [
        None,
        {},
        {"geometry": None},
        {"geometry": {"type": "Point"}},
        {"geometry": {"type": "LineString", "coordinates": [["bad", LAT], [LON, LAT]]}},
    ],
)
def test_invalid_geometry_returns_non_finite_distance(shape):
    assert math.isinf(distance_to_shape({"geo_shape": shape}, LAT, LON))


@pytest.mark.asyncio
async def test_addresses_validate_structure_and_preserve_coordinates():
    url = str(URL(GEOCODE_URL).with_query(q="Capitole", limit=5))
    municipality = address_feature()
    municipality["properties"]["type"] = "municipality"
    with aioresponses() as responses:
        responses.get(url, payload={"features": [municipality, address_feature()]})
        async with aiohttp.ClientSession() as session:
            found = await ToulouseApi(session).addresses("Capitole")
    assert found == [
        {
            "label": "1 Place du Capitole 31000 Toulouse",
            "id": "31555_1676_00001",
            "citycode": "31555",
            "latitude": LAT,
            "longitude": LON,
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"features": None},
        {"features": [None]},
        {"features": [{"properties": None}]},
    ],
)
@pytest.mark.asyncio
async def test_geocoder_schema_failures_raise_api_error(payload):
    url = str(URL(GEOCODE_URL).with_query(q="Capitole", limit=5))
    with aioresponses() as responses:
        responses.get(url, payload=payload)
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ApiError):
                await ToulouseApi(session).addresses("Capitole")


@pytest.mark.parametrize("field", ["id", "label"])
@pytest.mark.asyncio
async def test_incomplete_geocoder_address_is_not_saved(field):
    feature = address_feature()
    feature["properties"].pop(field)
    url = str(URL(GEOCODE_URL).with_query(q="Capitole", limit=5))
    with aioresponses() as responses:
        responses.get(url, payload={"features": [feature]})
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ApiError):
                await ToulouseApi(session).addresses("Capitole")


@pytest.mark.asyncio
async def test_pagination_and_order_by_actual_distance():
    first_page = [record(f"Rue {i}", latitude=LAT + 0.0001) for i in range(100)]
    last_page = [record("Rue devant le domicile")]
    with aioresponses() as responses:
        responses.get(routes_url(), payload={"total_count": 101, "results": first_page})
        responses.get(
            routes_url(100), payload={"total_count": 101, "results": last_page}
        )
        async with aiohttp.ClientSession() as session:
            found = await ToulouseApi(session).routes("om", LAT, LON)
    assert len(found) == 101
    assert found[0]["street"] == "Rue devant le domicile"
    assert found[0]["distance"] == 0
    assert found[-1]["distance"] == 11


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"total_count": "1", "results": []},
        {"total_count": -1, "results": []},
        {"total_count": 1, "results": []},
        {"total_count": 1, "results": [None]},
        {
            "total_count": 1,
            "results": [{"libelle_voie": "Rue", "infobulle_pdi": "Lundi"}],
        },
    ],
)
@pytest.mark.asyncio
async def test_route_schema_and_incomplete_pages_raise_api_error(payload):
    with aioresponses() as responses:
        responses.get(routes_url(), payload=payload)
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ApiError):
                await ToulouseApi(session).routes("om", LAT, LON)


@pytest.mark.asyncio
async def test_empty_result_is_valid():
    with aioresponses() as responses:
        responses.get(routes_url(), payload={"total_count": 0, "results": []})
        async with aiohttp.ClientSession() as session:
            assert await ToulouseApi(session).routes("om", LAT, LON) == []


@pytest.mark.parametrize(
    "invalid_field", ["libelle_voie", "infobulle_pdi", "geo_shape"]
)
@pytest.mark.asyncio
async def test_partial_route_data_preserves_valid_neighbour(invalid_field):
    """An incomplete public record must not hide a usable nearby route."""
    valid = record("Rue test valide")
    incomplete = record("Rue test incomplète")
    incomplete[invalid_field] = None
    with aioresponses() as responses:
        responses.get(
            routes_url(),
            payload={"total_count": 2, "results": [incomplete, valid]},
        )
        async with aiohttp.ClientSession() as session:
            found = await ToulouseApi(session).routes("om", LAT, LON)
    assert len(found) == 1
    assert found[0]["key"] == record_key(valid)
    assert found[0]["street"] == "Rue test valide"
    assert found[0]["rule"] == "Lundi"


@pytest.mark.parametrize(
    "invalid_field", ["libelle_voie", "infobulle_pdi", "geo_shape"]
)
@pytest.mark.asyncio
async def test_all_incomplete_routes_are_data_error_not_empty_coverage(invalid_field):
    """Missing usable records must remain distinct from genuine zero coverage."""
    incomplete = record()
    incomplete[invalid_field] = None
    with aioresponses() as responses:
        responses.get(routes_url(), payload={"total_count": 1, "results": [incomplete]})
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ApiDataError):
                await ToulouseApi(session).routes("om", LAT, LON)


@pytest.mark.asyncio
async def test_pagination_limit_does_not_silently_truncate():
    with aioresponses() as responses:
        for offset in range(0, 1000, 100):
            responses.get(
                routes_url(offset),
                payload={"total_count": 1001, "results": [record()] * 100},
            )
        async with aiohttp.ClientSession() as session:
            with pytest.raises(ApiError, match="Trop de tronçons"):
                await ToulouseApi(session).routes("om", LAT, LON)


@pytest.mark.parametrize("failure", ["status", "timeout", "bad_json", "api_error"])
@pytest.mark.asyncio
async def test_transport_and_error_responses_raise_api_error(failure):
    with aioresponses() as responses:
        if failure == "status":
            responses.get(routes_url(), status=503)
        elif failure == "timeout":
            responses.get(routes_url(), timeout=True)
        elif failure == "bad_json":
            responses.get(routes_url(), body="not json")
        else:
            responses.get(routes_url(), payload={"error_code": "ODSQLError"})
        async with aiohttp.ClientSession() as session:
            expected = (
                ApiConnectionError if failure in {"status", "timeout"} else ApiDataError
            )
            with pytest.raises(expected):
                await ToulouseApi(session).routes("om", LAT, LON)

"""Test actual Home Assistant config and options flow objects."""

from copy import deepcopy
from types import MappingProxyType
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.toulouse_metropole_dechets.api import ApiError
from custom_components.toulouse_metropole_dechets.config_flow import (
    ToulouseConfigFlow,
    ToulouseOptionsFlow,
    initial_streams,
)
from custom_components.toulouse_metropole_dechets.const import DOMAIN

ADDRESS = {
    "label": "1 Place du Capitole 31000 Toulouse",
    "id": "31555_1676_00001",
    "latitude": 43.604,
    "longitude": 1.444,
    "citycode": "31555",
}
ROUTE = {
    "key": "segment-test",
    "street": "Place du Capitole",
    "rule": "Lundi",
    "distance": 12,
    "source_url": "https://data.toulouse-metropole.fr/",
}


@pytest_asyncio.fixture
async def flow(tmp_path, monkeypatch):
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    flow = ToulouseConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    flow.context = {"source": "user"}
    monkeypatch.setattr(
        "custom_components.toulouse_metropole_dechets.config_flow.async_get_clientsession",
        lambda hass: object(),
    )
    yield flow
    await hass.async_stop(force=True)


def fake_api(monkeypatch, *, addresses=None, routes=None):
    api = Mock()
    api.addresses = AsyncMock(
        return_value=addresses if addresses is not None else [ADDRESS]
    )
    api.routes = AsyncMock(return_value=routes if routes is not None else [ROUTE])
    monkeypatch.setattr(
        "custom_components.toulouse_metropole_dechets.config_flow.ToulouseApi",
        Mock(return_value=api),
    )
    return api


@pytest.mark.asyncio
async def test_initial_setup_can_skip_routes_without_inventing_dates(flow, monkeypatch):
    fake_api(monkeypatch)
    assert (await flow.async_step_user())["step_id"] == "user"
    result = await flow.async_step_user({"address": "Capitole Toulouse"})
    assert result["step_id"] == "address"
    # Exercise selectors through HA's actual schema validation too.
    result["data_schema"]({"address_choice": "0"})
    assert (await flow.async_step_address({"address_choice": "0"}))["step_id"] == "om"
    assert (await flow.async_step_om({"route": "skip"}))["step_id"] == "tri"
    assert (await flow.async_step_tri({"route": "skip"}))["step_id"] == "green"
    result = await flow.async_step_green({"green_plan": "none"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["address"] == ADDRESS
    assert result["data"]["streams"]["om"]["mode"] == "unavailable"
    assert result["data"]["streams"]["bulky"]["mode"] == "appointment"
    assert result["data"]["streams"]["glass"]["mode"] == "drop_off"


@pytest.mark.asyncio
async def test_ambiguous_route_stays_on_form_and_can_be_skipped(flow):
    ambiguous = dict(ROUTE, rule="Lundi d’un côté de la voie ; Mardi de l’autre")
    flow.address = ADDRESS
    flow.routes = {"om": [ambiguous], "tri": []}
    result = await flow.async_step_om({"route": ambiguous["key"]})
    assert result["step_id"] == "om"
    assert result["errors"] == {"base": "ambiguous_route"}
    assert flow.streams["om"]["mode"] == "unavailable"
    assert (await flow.async_step_om({"route": "skip"}))["step_id"] == "tri"


@pytest.mark.asyncio
async def test_confirmed_route_keeps_stable_key_for_updates(flow):
    flow.address = ADDRESS
    flow.routes = {"om": [ROUTE], "tri": []}
    result = await flow.async_step_om({"route": ROUTE["key"]})
    assert result["step_id"] == "tri"
    assert flow.streams["om"]["mode"] == "recurring"
    assert flow.streams["om"]["route_key"] == ROUTE["key"]
    assert flow.streams["om"]["rule"] == "Lundi"


@pytest.mark.asyncio
async def test_geocoder_error_and_no_results_keep_user_form(flow, monkeypatch):
    api = fake_api(monkeypatch, addresses=[])
    result = await flow.async_step_user({"address": "Unknown"})
    assert result["errors"] == {"base": "no_address"}
    api.addresses.side_effect = ApiError("network")
    result = await flow.async_step_user({"address": "Unknown"})
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_address_without_om_tri_routes_can_continue_to_green(flow, monkeypatch):
    fake_api(monkeypatch, routes=[])
    await flow.async_step_user({"address": "Capitole Toulouse"})
    assert (await flow.async_step_address({"address_choice": "0"}))["step_id"] == "om"
    assert (await flow.async_step_om({"route": "skip"}))["step_id"] == "tri"
    assert (await flow.async_step_tri({"route": "skip"}))["step_id"] == "green"


@pytest.mark.asyncio
async def test_address_outside_metropole_is_rejected_before_route_requests(
    flow, monkeypatch
):
    api = fake_api(monkeypatch, addresses=[dict(ADDRESS, citycode="75056")])
    await flow.async_step_user({"address": "Paris"})
    result = await flow.async_step_address({"address_choice": "0"})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "outside_metropole"
    api.routes.assert_not_called()


def options_flow(flow, monkeypatch, *, saved_options=None):
    streams = initial_streams()
    streams["om"].update(mode="recurring", rule="Lundi", route_key="om-key")
    streams["tri"].update(mode="recurring", rule="Mardi", route_key="tri-key")
    entry = config_entries.ConfigEntry(
        data={"address": ADDRESS, "streams": streams},
        discovery_keys=MappingProxyType({}),
        domain=DOMAIN,
        minor_version=1,
        options=saved_options or {},
        source="user",
        subentries_data=None,
        title=ADDRESS["label"],
        unique_id=ADDRESS["id"],
        version=1,
    )
    monkeypatch.setattr(
        flow.hass.config_entries, "async_get_known_entry", lambda entry_id: entry
    )
    options = ToulouseOptionsFlow()
    options.hass = flow.hass
    options.handler = entry.entry_id
    return options, entry


@pytest.mark.asyncio
async def test_options_preserve_all_other_streams_and_original_entry(flow, monkeypatch):
    options, entry = options_flow(flow, monkeypatch)
    original = deepcopy(dict(entry.data))
    assert (await options.async_step_init({"stream": "bulky"}))["step_id"] == "schedule"
    result = await options.async_step_schedule(
        {"mode": "manual", "dates": "2026-12-01"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    saved = result["data"]["streams"]
    assert saved["bulky"]["dates"] == "2026-12-01"
    assert saved["om"] == entry.data["streams"]["om"]
    assert saved["tri"] == entry.data["streams"]["tri"]
    assert dict(entry.data) == original


@pytest.mark.asyncio
async def test_options_preserve_prior_options_when_editing_another_stream(
    flow, monkeypatch
):
    previous = initial_streams()
    previous["bulky"].update(mode="manual", dates="2026-12-01")
    options, _ = options_flow(flow, monkeypatch, saved_options={"streams": previous})
    await options.async_step_init({"stream": "glass"})
    result = await options.async_step_schedule(
        {"mode": "manual", "dates": "2026-12-02"}
    )
    assert result["data"]["streams"]["bulky"] == previous["bulky"]


@pytest.mark.asyncio
async def test_custom_rule_disconnects_route_and_invalid_input_is_rejected(
    flow, monkeypatch
):
    options, entry = options_flow(flow, monkeypatch)
    await options.async_step_init({"stream": "om"})
    result = await options.async_step_schedule(
        {"mode": "manual", "dates": "2026-02-30"}
    )
    assert result["errors"] == {"base": "invalid_schedule"}
    assert entry.data["streams"]["om"]["route_key"] == "om-key"
    result = await options.async_step_schedule(
        {"mode": "recurring", "rule": "Vendredi"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert "route_key" not in result["data"]["streams"]["om"]
    assert result["data"]["streams"]["om"]["rule"] == "Vendredi"


@pytest.mark.asyncio
async def test_green_plan_does_not_require_unused_recurring_rule(flow, monkeypatch):
    options, _ = options_flow(flow, monkeypatch)
    await options.async_step_init({"stream": "green"})
    result = await options.async_step_schedule(
        {"mode": "recurring", "rule": "", "green_plan": "seasonal"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["streams"]["green"]["green_plan"] == "seasonal"
    assert result["data"]["streams"]["green"]["mode"] == "manual"

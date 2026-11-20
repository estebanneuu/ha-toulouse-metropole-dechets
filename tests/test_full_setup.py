"""Load actual HA platforms, registries, calendar services, and translations."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from homeassistant import bootstrap, loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.core_config import async_process_ha_core_config
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from custom_components.toulouse_metropole_dechets.config_flow import initial_streams
from custom_components.toulouse_metropole_dechets.const import DOMAIN
from custom_components.toulouse_metropole_dechets.green import (
    GreenClient,
    parse_schedule,
)


@pytest.mark.asyncio
async def test_actual_platform_setup_calendar_service_and_unload(tmp_path, monkeypatch):
    """Only external HTTP/socket boundaries are replaced; HA platforms are real."""
    (tmp_path / "custom_components").symlink_to(
        Path(__file__).parents[1] / "custom_components", target_is_directory=True
    )
    hass = HomeAssistant(str(tmp_path))
    hass.config.skip_pip = True
    loader.async_setup(hass)
    hass.config_entries = ConfigEntries(hass, {})
    previous_timezone = dt_util.DEFAULT_TIME_ZONE
    monkeypatch.setattr(
        "homeassistant.components.http.server.HomeAssistantHTTP.async_bind",
        AsyncMock(),
    )
    try:
        assert await bootstrap.async_load_base_functionality(hass)
        await async_process_ha_core_config(
            hass,
            {
                "time_zone": "Europe/Paris",
                "latitude": 43.6,
                "longitude": 1.44,
                "elevation": 150,
                "unit_system": "metric",
                "language": "fr",
            },
        )
        frozen_now = datetime(2026, 11, 20, 14, tzinfo=ZoneInfo("Europe/Paris"))
        monkeypatch.setattr(
            dt_util,
            "now",
            lambda tz=None: frozen_now.astimezone(tz or dt_util.DEFAULT_TIME_ZONE),
        )
        today = dt_util.now().date()
        streams = initial_streams()
        streams["om"].update(mode="manual", dates=today.isoformat())
        streams["green"].update(mode="manual", green_plan="paid")
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/green_sectors_2026.json").read_text()
        )
        green_fetch = AsyncMock(return_value=parse_schedule(fixture["features"][0]))
        monkeypatch.setattr(GreenClient, "async_schedule", green_fetch)
        entry = ConfigEntry(
            domain=DOMAIN,
            title="Adresse test",
            data={
                "address": {"latitude": 43.6, "longitude": 1.44},
                "streams": streams,
            },
            options={},
            version=1,
            minor_version=1,
            source="user",
            unique_id="full_setup_test",
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
        )
        async with aiohttp.ClientSession() as session:
            monkeypatch.setattr(
                "custom_components.toulouse_metropole_dechets.coordinator.async_get_clientsession",
                lambda hass: session,
            )
            await hass.config_entries.async_add(entry)
            await hass.async_block_till_done()
            assert entry.state == ConfigEntryState.LOADED
            entities = er.async_entries_for_config_entry(
                er.async_get(hass), entry.entry_id
            )
            assert len(entities) == 21
            assert sum(entity.domain == "calendar" for entity in entities) == 7
            assert all(
                hass.states.get(entity.entity_id) is not None for entity in entities
            )
            devices = dr.async_entries_for_config_entry(
                dr.async_get(hass), entry.entry_id
            )
            assert len(devices) == 1
            assert {entity.device_id for entity in entities} == {devices[0].id}

            calendar_id = next(
                entity.entity_id
                for entity in entities
                if entity.unique_id == f"{entry.entry_id}_om_calendar"
            )
            assert hass.states.get(calendar_id).state == "on"
            response = await hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": calendar_id,
                    "start_date_time": today.isoformat() + "T00:00:00",
                    "end_date_time": (today + timedelta(days=1)).isoformat()
                    + "T00:00:00",
                },
                blocking=True,
                return_response=True,
            )
            assert len(response[calendar_id]["events"]) == 1
            assert response[calendar_id]["events"][0]["start"] == today.isoformat()
            green_fetch.assert_awaited_once_with(43.6, 1.44)
            green_calendar_id = next(
                entity.entity_id
                for entity in entities
                if entity.unique_id == f"{entry.entry_id}_green_calendar"
            )
            green_status_id = next(
                entity.entity_id
                for entity in entities
                if entity.unique_id == f"{entry.entry_id}_green_status"
            )
            green_state = hass.states.get(green_calendar_id)
            assert green_state.attributes["valid_until"] == "2026-12-31"
            assert green_state.attributes["green_plan"] == "paid"
            assert green_state.attributes["source_url"].startswith("https://")
            green_response = await hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": green_calendar_id,
                    "start_date_time": "2026-01-01T00:00:00",
                    "end_date_time": "2027-01-01T00:00:00",
                },
                blocking=True,
                return_response=True,
            )
            assert len(green_response[green_calendar_id]["events"]) == 30
            assert hass.states.get(green_status_id).state == "manual"
            translations = await async_get_translations(hass, "fr", "entity", [DOMAIN])
            assert (
                translations[
                    f"component.{DOMAIN}.entity.sensor.collection_status.state.drop_off"
                ]
                == "Apport volontaire / compostage"
            )
            # A configured status cannot use HA's reserved unavailable value.
            status_id = next(
                entity.entity_id
                for entity in entities
                if entity.unique_id == f"{entry.entry_id}_tri_status"
            )
            assert hass.states.get(status_id).state == "not_configured"
            coordinator = entry.runtime_data
            frozen_now = datetime(2027, 1, 1, 0, tzinfo=ZoneInfo("Europe/Paris"))
            coordinator.async_update_listeners()
            assert hass.states.get(green_status_id).state == "expired"
            assert hass.states.get(green_calendar_id).state == "off"
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
            assert not coordinator._listeners
            assert all(
                (state := hass.states.get(entity.entity_id)) is None
                or state.state == "unavailable"
                for entity in entities
            )
    finally:
        await hass.async_stop(force=True)
        dt_util.set_default_time_zone(previous_timezone)

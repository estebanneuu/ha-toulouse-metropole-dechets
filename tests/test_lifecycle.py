"""Check setup, first refresh and unload against the real HA coordinator."""

from types import MappingProxyType
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.toulouse_metropole_dechets import (
    PLATFORMS,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.toulouse_metropole_dechets.api import ApiError, ToulouseApi
from custom_components.toulouse_metropole_dechets.const import DOMAIN, STREAMS


@pytest.mark.asyncio
@pytest.mark.parametrize("api_fails", [False, True])
async def test_entry_lifecycle_with_real_coordinator(tmp_path, monkeypatch, api_fails):
    """Forward platforms after the refresh and isolate an upstream stream error."""
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = Mock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "custom_components.toulouse_metropole_dechets.coordinator.async_get_clientsession",
        Mock(),
    )
    streams = {stream: {"mode": "unavailable"} for stream in STREAMS}
    streams["om"] = {
        "mode": "recurring",
        "route_key": "selected_road",
        "rule": "Le lundi",
    }
    streams["bulky"] = {"mode": "manual", "dates": "2026-11-25"}
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
        unique_id="address_test",
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
        state=ConfigEntryState.SETUP_IN_PROGRESS,
    )
    routes = AsyncMock(return_value=[{"key": "selected_road", "rule": "Le mardi"}])
    if api_fails:
        routes.side_effect = ApiError("Service momentanément indisponible")
    monkeypatch.setattr(ToulouseApi, "routes", routes)
    try:
        assert await async_setup_entry(hass, entry)
        hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
            entry, PLATFORMS
        )
        assert entry.runtime_data.last_update_success
        assert entry.runtime_data.data["bulky"]["dates"] == "2026-11-25"
        if api_fails:
            assert entry.runtime_data.data["om"]["mode"] == "unavailable"
            assert entry.runtime_data.data["om"]["error"]
        else:
            assert entry.runtime_data.data["om"]["rule"] == "Le mardi"
        # Runtime refresh must not mutate persisted setup data.
        assert entry.data["streams"]["om"]["rule"] == "Le lundi"
        assert await async_unload_entry(hass, entry)
        hass.config_entries.async_unload_platforms.assert_awaited_once_with(
            entry, PLATFORMS
        )
    finally:
        await hass.async_stop(force=True)

"""Exercise entities against the installed Home Assistant API."""

import logging
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from custom_components.toulouse_metropole_dechets.calendar import (
    CollectionCalendar,
)
from custom_components.toulouse_metropole_dechets.calendar import (
    async_setup_entry as setup_calendars,
)
from custom_components.toulouse_metropole_dechets.const import STREAMS
from custom_components.toulouse_metropole_dechets.sensor import (
    CollectionStatusSensor,
    NextCollectionSensor,
)
from custom_components.toulouse_metropole_dechets.sensor import (
    async_setup_entry as setup_sensors,
)

PARIS = ZoneInfo("Europe/Paris")


@pytest.fixture(autouse=True)
def local_timezone(monkeypatch):
    monkeypatch.setattr(dt_util, "DEFAULT_TIME_ZONE", PARIS)
    monkeypatch.setattr(
        dt_util,
        "now",
        lambda *args: datetime(2026, 11, 20, 14, tzinfo=PARIS),
    )


@pytest_asyncio.fixture
async def coordinator(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), config_entry=None, name="test"
    )
    coordinator.entry = SimpleNamespace(entry_id="test_address", title="Adresse test")
    coordinator.data = {
        stream: {"mode": "unavailable", "error": None} for stream in STREAMS
    }
    coordinator.data["om"] = {
        "mode": "recurring",
        "rule": "Le vendredi",
        "source_url": "https://data.toulouse-metropole.fr/",
        "description": "Collecte prévisionnelle",
        "error": None,
    }
    yield coordinator
    await hass.async_stop(force=True)


def test_today_is_retained_until_midnight(coordinator, monkeypatch):
    calendar = CollectionCalendar(coordinator, "om")
    sensor = NextCollectionSensor(coordinator, "om")
    event = calendar.event
    assert event.all_day
    assert event.start == date(2026, 11, 20)
    assert event.end == date(2026, 11, 21)
    assert sensor.native_value == date(2026, 11, 20)
    assert sensor.extra_state_attributes["days_until"] == 0
    assert sensor.extra_state_attributes["collection_today"] is True
    monkeypatch.setattr(
        dt_util, "now", lambda: datetime(2026, 11, 21, 0, 0, tzinfo=PARIS)
    )
    assert calendar.event.start == date(2026, 11, 27)
    assert sensor.extra_state_attributes["days_until"] == 6


@pytest.mark.asyncio
async def test_calendar_window_is_exclusive_and_uses_local_timezone(coordinator):
    coordinator.data["om"]["rule"] = "7 jours / 7"
    calendar = CollectionCalendar(coordinator, "om")
    events = await calendar.async_get_events(
        coordinator.hass,
        datetime(2026, 11, 19, 23, tzinfo=UTC),
        datetime(2026, 11, 20, 23, tzinfo=UTC),
    )
    assert [event.start for event in events] == [date(2026, 11, 20)]
    # A partial day intersects the all-day event too.
    events = await calendar.async_get_events(
        coordinator.hass,
        datetime(2026, 11, 20, 12, tzinfo=PARIS),
        datetime(2026, 11, 21, 12, tzinfo=PARIS),
    )
    assert [event.start for event in events] == [
        date(2026, 11, 20),
        date(2026, 11, 21),
    ]


@pytest.mark.asyncio
async def test_calendar_daylight_saving_day(coordinator):
    coordinator.data["om"]["rule"] = "7 jours / 7"
    calendar = CollectionCalendar(coordinator, "om")
    events = await calendar.async_get_events(
        coordinator.hass,
        datetime(2026, 10, 24, 22, tzinfo=UTC),
        datetime(2026, 10, 25, 23, tzinfo=UTC),
    )
    assert [event.start for event in events] == [date(2026, 10, 25)]


@pytest.mark.parametrize("mode", ["drop_off", "appointment", "unavailable"])
@pytest.mark.asyncio
async def test_unscheduled_stream_has_no_invented_date(coordinator, mode):
    coordinator.data["glass"] = {"mode": mode}
    calendar = CollectionCalendar(coordinator, "glass")
    sensor = NextCollectionSensor(coordinator, "glass")
    assert calendar.event is None
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["days_until"] is None
    expected = "not_configured" if mode == "unavailable" else mode
    assert CollectionStatusSensor(coordinator, "glass").native_value == expected
    assert (
        await calendar.async_get_events(
            coordinator.hass,
            datetime(2026, 11, 1, tzinfo=PARIS),
            datetime(2026, 12, 1, tzinfo=PARIS),
        )
        == []
    )


def test_manual_dates_are_sorted(coordinator):
    coordinator.data["bulky"] = {
        "mode": "manual",
        "dates": "2026-11-22,2026-11-21",
    }
    assert NextCollectionSensor(coordinator, "bulky").native_value == date(2026, 11, 21)


def test_source_error_is_visible_and_does_not_affect_other_streams(coordinator):
    coordinator.data["om"]["error"] = "Règle ambiguë"
    date_sensor = NextCollectionSensor(coordinator, "om")
    status = CollectionStatusSensor(coordinator, "om")
    assert not date_sensor.available
    assert date_sensor.native_value is None
    assert status.available
    assert status.native_value == "error"
    assert status.extra_state_attributes["error"] == "Règle ambiguë"
    assert NextCollectionSensor(coordinator, "tri").available
    coordinator.last_update_success = False
    assert not status.available
    assert not NextCollectionSensor(coordinator, "tri").available


def test_published_calendar_expiry_is_explicit(coordinator, monkeypatch):
    coordinator.data["green"] = {
        "mode": "manual",
        "dates": "2026-11-20",
        "valid_until": "2026-12-31",
        "green_plan": "seasonal",
        "coverage_note": "Calendrier officiel 2026 uniquement",
    }
    status = CollectionStatusSensor(coordinator, "green")
    assert status.native_value == "manual"
    assert status.extra_state_attributes["valid_until"] == "2026-12-31"
    assert status.extra_state_attributes["green_plan"] == "seasonal"
    assert status.extra_state_attributes["coverage_note"]
    monkeypatch.setattr(
        dt_util, "now", lambda: datetime(2027, 1, 1, 0, 0, tzinfo=PARIS)
    )
    assert status.native_value == "expired"
    assert NextCollectionSensor(coordinator, "green").native_value is None
    assert CollectionCalendar(coordinator, "green").event is None
    coordinator.data["green"]["error"] = "Source indisponible"
    assert status.native_value == "error"


@pytest.mark.asyncio
async def test_platforms_create_all_streams_with_stable_unique_ids(coordinator):
    entry = SimpleNamespace(runtime_data=coordinator)
    entities = []
    await setup_calendars(coordinator.hass, entry, entities.extend)
    await setup_sensors(coordinator.hass, entry, entities.extend)
    assert len(entities) == 3 * len(STREAMS)
    assert len({entity.unique_id for entity in entities}) == len(entities)
    assert all(entity.should_poll is False for entity in entities)
    assert (
        len({frozenset(entity.device_info["identifiers"]) for entity in entities}) == 1
    )


@pytest.mark.asyncio
async def test_midnight_callback_updates_state_without_network_and_unsubscribes(
    coordinator, monkeypatch
):
    sensor = NextCollectionSensor(coordinator, "om")
    sensor.hass = coordinator.hass
    sensor.entity_id = "sensor.test_collecte"
    unsubscribe = Mock()
    timer = Mock(return_value=unsubscribe)
    monkeypatch.setattr(
        "custom_components.toulouse_metropole_dechets.entity.async_track_time_change",
        timer,
    )
    sensor.async_write_ha_state = Mock()
    await sensor.async_added_to_hass()
    timer.assert_called_once_with(
        coordinator.hass, sensor._async_midnight, hour=0, minute=0, second=0
    )
    sensor._async_midnight(datetime(2026, 11, 21, tzinfo=PARIS))
    sensor.async_write_ha_state.assert_called_once()
    await sensor.async_remove(force_remove=True)
    unsubscribe.assert_called_once()

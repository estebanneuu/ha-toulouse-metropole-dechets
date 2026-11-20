"""Shared Home Assistant entity behavior for waste collections."""

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, ICONS, STREAMS
from .schedule import schedule_dates

LOOKAHEAD_DAYS = 730


class CollectionEntity(CoordinatorEntity):
    """Represent one collection stream at a configured address."""

    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({"description", "source_url", "rule"})

    def __init__(self, coordinator, stream: str, kind: str) -> None:
        super().__init__(coordinator, context=stream)
        self.stream = stream
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{stream}_{kind}"
        self._attr_icon = ICONS[stream]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer="Toulouse Métropole",
            model="Collectes des déchets",
        )

    @property
    def stream_config(self) -> dict[str, Any]:
        """Read refreshed data instead of keeping a stale copy."""
        return (self.coordinator.data or {}).get(self.stream, {})

    @property
    def available(self) -> bool:
        return super().available and not self.stream_config.get("error")

    @property
    def next_collection(self) -> date | None:
        """Keep today's all-day collection until local midnight."""
        if not self.available:
            return None
        today = dt_util.now().date()
        dates = schedule_dates(
            self.stream_config, today, today + timedelta(days=LOOKAHEAD_DAYS)
        )
        return dates[0] if dates else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        config = self.stream_config
        return {
            "collection_type": self.stream,
            "collection_label": STREAMS[self.stream],
            "mode": config.get("mode", "unavailable"),
            "description": config.get("description", ""),
            "source_url": config.get("source_url", ""),
            "rule": config.get("rule", ""),
            "error": config.get("error"),
            "valid_until": config.get("valid_until"),
            "green_plan": config.get("green_plan"),
            "coverage_note": config.get("coverage_note", ""),
            "exclude_public_shutdowns": config.get("exclude_public_shutdowns", False),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._async_midnight, hour=0, minute=0, second=0
            )
        )

    @callback
    def _async_midnight(self, now: datetime) -> None:
        """Refresh date-sensitive values locally, without an HTTP request."""
        self.async_write_ha_state()

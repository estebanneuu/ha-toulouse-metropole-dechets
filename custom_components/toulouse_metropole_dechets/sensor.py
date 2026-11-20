"""Next collection date and schedule status for every waste stream."""

from datetime import date
from typing import Any, ClassVar

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from .const import STREAMS
from .entity import CollectionEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities(
        entity
        for stream in STREAMS
        for entity in (
            NextCollectionSensor(entry.runtime_data, stream),
            CollectionStatusSensor(entry.runtime_data, stream),
        )
    )


class NextCollectionSensor(CollectionEntity, SensorEntity):
    """Expose a real date, suitable for dashboards and automations."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator, stream: str) -> None:
        super().__init__(coordinator, stream, "next_collection")
        self._attr_name = f"{STREAMS[stream]} prochaine collecte"

    @property
    def native_value(self) -> date | None:
        return self.next_collection

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = self.next_collection
        days_until = (day - dt_util.now().date()).days if day is not None else None
        return {
            **super().extra_state_attributes,
            "days_until": days_until,
            "collection_today": days_until == 0,
            "collection_tomorrow": days_until == 1,
        }


class CollectionStatusSensor(CollectionEntity, SensorEntity):
    """Explain missing dates instead of inventing a collection."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "collection_status"
    _attr_options: ClassVar[list[str]] = [
        "recurring",
        "manual",
        "drop_off",
        "appointment",
        "not_configured",
        "error",
        "expired",
    ]

    def __init__(self, coordinator, stream: str) -> None:
        super().__init__(coordinator, stream, "status")
        self._attr_name = f"{STREAMS[stream]} statut"

    @property
    def available(self) -> bool:
        """Keep source-specific errors visible while coordinator is healthy."""
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> str:
        if self.stream_config.get("error"):
            return "error"
        valid_until = self.stream_config.get("valid_until")
        if valid_until and dt_util.now().date() > date.fromisoformat(valid_until):
            return "expired"
        mode = self.stream_config.get("mode", "unavailable")
        return "not_configured" if mode == "unavailable" else mode

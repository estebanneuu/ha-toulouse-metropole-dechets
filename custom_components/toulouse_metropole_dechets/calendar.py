"""Read-only all-day collection calendars."""

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import STREAMS
from .entity import CollectionEntity
from .schedule import schedule_dates

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities(
        CollectionCalendar(entry.runtime_data, stream) for stream in STREAMS
    )


class CollectionCalendar(CollectionEntity, CalendarEntity):
    """Expose dates only when a schedule is available."""

    def __init__(self, coordinator, stream: str) -> None:
        super().__init__(coordinator, stream, "calendar")
        self._attr_name = STREAMS[stream]

    def _event_for(self, day: date) -> CalendarEvent:
        config = self.stream_config
        description = "\n".join(
            part
            for part in (config.get("description"), config.get("source_url"))
            if part
        )
        return CalendarEvent(
            start=day,
            end=day + timedelta(days=1),
            summary=STREAMS[self.stream],
            description=description or None,
            uid=f"{self.unique_id}_{day.isoformat()}",
        )

    @property
    def event(self) -> CalendarEvent | None:
        if (day := self.next_collection) is None:
            return None
        return self._event_for(day)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return sorted events overlapping the requested exclusive range."""
        if not self.available or end_date <= start_date:
            return []
        local_start = dt_util.as_local(start_date)
        local_end = dt_util.as_local(end_date)
        dates = schedule_dates(
            self.stream_config,
            local_start.date(),
            local_end.date() + timedelta(days=1),
        )
        events = [self._event_for(day) for day in dates]
        return [
            event
            for event in events
            if event.end_datetime_local > local_start
            and event.start_datetime_local < local_end
        ]

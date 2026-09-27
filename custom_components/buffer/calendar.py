"""Calendar of scheduled (and recently sent) Buffer posts."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import Post
from .const import CALENDAR_EVENT_MINUTES
from .coordinator import BufferConfigEntry, BufferCoordinator
from .entity import BufferOrgEntity, service_label

PARALLEL_UPDATES = 0


class BufferCalendar(BufferOrgEntity, CalendarEntity):
    """All posts for the organization as calendar events."""

    def __init__(self, coordinator: BufferCoordinator) -> None:
        super().__init__(coordinator, "content_calendar")

    def _to_event(self, post: Post) -> CalendarEvent | None:
        start = post.sent_at if post.status == "sent" and post.sent_at else post.due_at
        if start is None:
            return None
        channel = self.coordinator.data.channels.get(post.channel_id)
        service = service_label(channel.service if channel else post.channel_service or "")
        who = f"{service} · {channel.title}" if channel else service
        first_line = post.text.strip().splitlines()[0] if post.text.strip() else "(no text)"
        prefix = "✓ " if post.status == "sent" else ""
        return CalendarEvent(
            start=dt_util.as_utc(start),
            end=dt_util.as_utc(start) + timedelta(minutes=CALENDAR_EVENT_MINUTES),
            summary=f"{prefix}{who}: {first_line[:80]}",
            description=post.text,
            location=post.external_link,
            uid=post.id,
        )

    def _events(self) -> list[CalendarEvent]:
        data = self.coordinator.data
        events = [e for p in (*data.scheduled, *data.sent) if (e := self._to_event(p))]
        return sorted(events, key=lambda e: e.start)

    @property
    def event(self) -> CalendarEvent | None:
        """The current or next upcoming post."""
        now = dt_util.utcnow()
        return next((e for e in self._events() if e.end > now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [e for e in self._events() if e.end > start_date and e.start < end_date]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BufferConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([BufferCalendar(entry.runtime_data.coordinator)])

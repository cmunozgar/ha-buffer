"""Notify entities: `notify.send_message` adds a post to a channel's queue."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import BufferError
from .const import DOMAIN
from .coordinator import BufferConfigEntry
from .entity import BufferChannelEntity

PARALLEL_UPDATES = 1


class BufferQueueNotify(BufferChannelEntity, NotifyEntity):
    """Sending a message = adding it to the channel's Buffer queue."""

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        text = f"{title}\n\n{message}" if title else message
        try:
            await self.coordinator.client.create_post(self.channel_id, text)
        except BufferError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="create_post_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BufferConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def _add_new_channels() -> None:
        new = [c for cid, c in coordinator.data.channels.items() if cid not in known]
        if not new:
            return
        known.update(c.id for c in new)
        async_add_entities(BufferQueueNotify(coordinator, c, "add_to_queue") for c in new)

    _add_new_channels()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_channels))

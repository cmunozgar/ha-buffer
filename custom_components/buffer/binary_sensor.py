"""Binary sensors for Buffer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Channel, Overview
from .coordinator import BufferConfigEntry, BufferCoordinator
from .entity import BufferChannelEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ChannelBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[Overview, Channel], bool]


CHANNEL_BINARY_SENSORS: tuple[ChannelBinaryDescription, ...] = (
    ChannelBinaryDescription(
        key="disconnected",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda _d, c: c.is_disconnected,
    ),
    ChannelBinaryDescription(
        key="queue_paused",
        value_fn=lambda _d, c: c.is_queue_paused,
    ),
    ChannelBinaryDescription(
        key="queue_empty",
        value_fn=lambda d, c: not d.scheduled_for(c.id),
    ),
)


class BufferChannelBinarySensor(BufferChannelEntity, BinarySensorEntity):
    entity_description: ChannelBinaryDescription

    def __init__(
        self,
        coordinator: BufferCoordinator,
        channel: Channel,
        description: ChannelBinaryDescription,
    ) -> None:
        super().__init__(coordinator, channel, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if (channel := self.channel) is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data, channel)


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
        async_add_entities(
            BufferChannelBinarySensor(coordinator, c, d)
            for c in new
            for d in CHANNEL_BINARY_SENSORS
        )

    _add_new_channels()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_channels))

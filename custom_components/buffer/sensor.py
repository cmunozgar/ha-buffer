"""Sensors for Buffer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Channel, Overview, Post
from .coordinator import BufferConfigEntry, BufferCoordinator
from .entity import BufferChannelEntity, BufferOrgEntity

PARALLEL_UPDATES = 0


def _post_attrs(post: Post | None) -> dict[str, Any]:
    if post is None:
        return {}
    return {
        "post_id": post.id,
        "text": post.text[:255],
        "link": post.external_link,
    }


# ---------------------------------------------------------------- channel --- #


@dataclass(frozen=True, kw_only=True)
class ChannelSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Overview, str], int | datetime | None]
    attrs_fn: Callable[[Overview, str], dict[str, Any]] = lambda _d, _c: {}


def _next_post(data: Overview, cid: str) -> Post | None:
    posts = data.scheduled_for(cid)
    return posts[0] if posts else None


CHANNEL_SENSORS: tuple[ChannelSensorDescription, ...] = (
    ChannelSensorDescription(
        key="queue_size",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="posts",
        value_fn=lambda d, c: len(d.scheduled_for(c)),
    ),
    ChannelSensorDescription(
        key="next_post",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d, c: (p.due_at if (p := _next_post(d, c)) else None),
        attrs_fn=lambda d, c: _post_attrs(_next_post(d, c)),
    ),
    ChannelSensorDescription(
        key="last_sent",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d, c: (
            (p.sent_at or p.due_at) if (p := d.last_sent_for(c)) else None
        ),
        attrs_fn=lambda d, c: _post_attrs(d.last_sent_for(c)),
    ),
    ChannelSensorDescription(
        key="failed_posts",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="posts",
        value_fn=lambda d, c: len(d.failed_for(c)),
        attrs_fn=lambda d, c: (
            {"latest_error": f[0].error_message} if (f := d.failed_for(c)) else {}
        ),
    ),
)


class BufferChannelSensor(BufferChannelEntity, SensorEntity):
    entity_description: ChannelSensorDescription

    def __init__(
        self,
        coordinator: BufferCoordinator,
        channel: Channel,
        description: ChannelSensorDescription,
    ) -> None:
        super().__init__(coordinator, channel, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | datetime | None:
        return self.entity_description.value_fn(self.coordinator.data, self.channel_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs_fn(self.coordinator.data, self.channel_id)


# ------------------------------------------------------------ organization --- #


@dataclass(frozen=True, kw_only=True)
class OrgSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Overview], int | None]


ORG_SENSORS: tuple[OrgSensorDescription, ...] = (
    OrgSensorDescription(
        key="total_scheduled",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="posts",
        value_fn=lambda d: len(d.scheduled),
    ),
    OrgSensorDescription(
        key="total_failed",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="posts",
        value_fn=lambda d: len(d.failed),
    ),
    OrgSensorDescription(
        key="api_requests_remaining",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="requests",
        value_fn=lambda d: d.rate_limit_remaining,
    ),
)


class BufferOrgSensor(BufferOrgEntity, SensorEntity):
    entity_description: OrgSensorDescription

    def __init__(
        self, coordinator: BufferCoordinator, description: OrgSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | None:
        return self.entity_description.value_fn(self.coordinator.data)


# ------------------------------------------------------------------ setup --- #


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BufferConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(BufferOrgSensor(coordinator, d) for d in ORG_SENSORS)

    known: set[str] = set()

    @callback
    def _add_new_channels() -> None:
        new = [c for cid, c in coordinator.data.channels.items() if cid not in known]
        if not new:
            return
        known.update(c.id for c in new)
        async_add_entities(
            BufferChannelSensor(coordinator, c, d) for c in new for d in CHANNEL_SENSORS
        )

    _add_new_channels()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_channels))

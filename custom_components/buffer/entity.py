"""Base entities for Buffer."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Channel
from .const import DOMAIN
from .coordinator import BufferCoordinator

SERVICE_NAMES = {
    "twitter": "X (Twitter)",
    "linkedin": "LinkedIn",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "googlebusiness": "Google Business Profile",
    "whatsapp": "WhatsApp",
}


def service_label(service: str) -> str:
    return SERVICE_NAMES.get(service.lower(), service.capitalize())


def org_device_identifier(org_id: str) -> tuple[str, str]:
    return (DOMAIN, f"org_{org_id}")


def channel_device_identifier(channel_id: str) -> tuple[str, str]:
    return (DOMAIN, f"channel_{channel_id}")


class BufferOrgEntity(CoordinatorEntity[BufferCoordinator]):
    """Entity attached to the Buffer organization device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BufferCoordinator, key: str) -> None:
        super().__init__(coordinator)
        org_id = coordinator.organization_id
        self._attr_unique_id = f"{org_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={org_device_identifier(org_id)},
            name=f"Buffer {coordinator.config_entry.title}",
            manufacturer="Buffer",
            model="Organization",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://publish.buffer.com",
        )


class BufferChannelEntity(CoordinatorEntity[BufferCoordinator]):
    """Entity attached to one Buffer channel (one device per channel)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BufferCoordinator, channel: Channel, key: str) -> None:
        super().__init__(coordinator)
        self.channel_id = channel.id
        self._attr_unique_id = f"{channel.id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={channel_device_identifier(channel.id)},
            name=f"{channel.title} ({service_label(channel.service)})",
            manufacturer="Buffer",
            model=service_label(channel.service),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=channel.external_link or "https://publish.buffer.com",
            via_device=org_device_identifier(coordinator.organization_id),
        )

    @property
    def channel(self) -> Channel | None:
        return self.coordinator.data.channels.get(self.channel_id)

    @property
    def available(self) -> bool:
        return super().available and self.channel is not None

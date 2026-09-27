"""Polling coordinator for Buffer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    BufferAuthError,
    BufferClient,
    BufferError,
    BufferRateLimitError,
    Overview,
)
from .const import (
    CONF_ORGANIZATION_ID,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class BufferRuntimeData:
    client: BufferClient
    coordinator: BufferCoordinator


type BufferConfigEntry = ConfigEntry[BufferRuntimeData]


class BufferCoordinator(DataUpdateCoordinator[Overview]):
    """Fetches the whole organization overview in a single request."""

    config_entry: BufferConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: BufferConfigEntry, client: BufferClient
    ) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(minutes=minutes),
        )
        self.client = client
        self.organization_id: str = entry.data[CONF_ORGANIZATION_ID]

    async def _async_update_data(self) -> Overview:
        try:
            return await self.client.get_overview(self.organization_id)
        except BufferAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BufferRateLimitError as err:
            raise UpdateFailed(
                f"Rate limited by Buffer (retry after {err.retry_after}s)"
            ) from err
        except BufferError as err:
            raise UpdateFailed(str(err)) from err

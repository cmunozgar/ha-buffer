"""The Buffer integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import BufferClient
from .const import DOMAIN
from .coordinator import BufferConfigEntry, BufferCoordinator, BufferRuntimeData
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.NOTIFY,
    Platform.SENSOR,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ICONS_URL = f"/{DOMAIN}_static/buffer-icons.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-wide actions and the `buffer:` icon set."""
    async_setup_services(hass)
    await _async_register_icons(hass)
    return True


async def _async_register_icons(hass: HomeAssistant) -> None:
    if hass.http is None or "frontend" not in hass.config.components:
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(ICONS_URL, str(Path(__file__).parent / "frontend" / "buffer-icons.js"), True)]
    )
    integration = await async_get_integration(hass, DOMAIN)
    # The version query busts the browser cache when the icon set changes.
    add_extra_js_url(hass, f"{ICONS_URL}?v={integration.version}")


async def async_setup_entry(hass: HomeAssistant, entry: BufferConfigEntry) -> bool:
    client = BufferClient(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    coordinator = BufferCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = BufferRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: BufferConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BufferConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

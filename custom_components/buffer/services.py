"""Actions (services) for Buffer: create_post and create_idea."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.util import dt as dt_util

from .api import BufferError
from .const import (
    ATTR_CHANNEL_ID,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DUE_AT,
    ATTR_IMAGE_URLS,
    ATTR_MODE,
    ATTR_SAVE_TO_DRAFT,
    ATTR_TEXT,
    ATTR_TITLE,
    DOMAIN,
    SERVICE_CREATE_IDEA,
    SERVICE_CREATE_POST,
    SHARE_MODES,
)
from .coordinator import BufferConfigEntry

CREATE_POST_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional(ATTR_CHANNEL_ID): vol.All(cv.ensure_list, [cv.string]),
            vol.Required(ATTR_TEXT): cv.string,
            vol.Optional(ATTR_MODE, default="add_to_queue"): vol.In(list(SHARE_MODES)),
            vol.Optional(ATTR_DUE_AT): cv.datetime,
            vol.Optional(ATTR_IMAGE_URLS, default=[]): vol.All(cv.ensure_list, [cv.url]),
            vol.Optional(ATTR_SAVE_TO_DRAFT, default=False): cv.boolean,
        }
    ),
    cv.has_at_least_one_key(ATTR_DEVICE_ID, ATTR_CHANNEL_ID),
)

CREATE_IDEA_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
            vol.Optional(ATTR_TITLE): cv.string,
            vol.Optional(ATTR_TEXT): cv.string,
        }
    ),
    cv.has_at_least_one_key(ATTR_TITLE, ATTR_TEXT),
)


def _loaded_entries(hass: HomeAssistant) -> list[BufferConfigEntry]:
    return [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]


def _entry_for_channel(hass: HomeAssistant, channel_id: str) -> BufferConfigEntry:
    for entry in _loaded_entries(hass):
        if channel_id in entry.runtime_data.coordinator.data.channels:
            return entry
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="unknown_channel",
        translation_placeholders={"channel": channel_id},
    )


def _channels_from_devices(hass: HomeAssistant, device_ids: list[str]) -> list[str]:
    registry = dr.async_get(hass)
    channel_ids: list[str] = []
    for device_id in device_ids:
        device = registry.async_get(device_id)
        found = [
            ident[len("channel_"):]
            for domain, ident in (device.identifiers if device else set())
            if domain == DOMAIN and ident.startswith("channel_")
        ]
        if not found:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_a_channel_device",
                translation_placeholders={"device": device_id},
            )
        channel_ids += found
    return channel_ids


async def _create_post(call: ServiceCall) -> ServiceResponse:
    hass = call.hass
    data = call.data
    channel_ids = list(
        dict.fromkeys(
            _channels_from_devices(hass, data.get(ATTR_DEVICE_ID, []))
            + data.get(ATTR_CHANNEL_ID, [])
        )
    )

    mode = SHARE_MODES[data[ATTR_MODE]]
    due_at = data.get(ATTR_DUE_AT)
    if mode == "customScheduled" and due_at is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="due_at_required"
        )
    if due_at is not None:
        mode = "customScheduled"  # an explicit time always wins
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=dt_util.get_default_time_zone())
        due_at = dt_util.as_utc(due_at)

    # Resolve every channel first so we fail before posting anywhere.
    targets = [(cid, _entry_for_channel(hass, cid)) for cid in channel_ids]

    posts: list[dict[str, Any]] = []
    touched: set[str] = set()
    for channel_id, entry in targets:
        try:
            post = await entry.runtime_data.client.create_post(
                channel_id=channel_id,
                text=data[ATTR_TEXT],
                mode=mode,
                due_at=due_at,
                image_urls=data[ATTR_IMAGE_URLS],
                save_to_draft=data[ATTR_SAVE_TO_DRAFT],
            )
        except BufferError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="create_post_failed",
                translation_placeholders={"error": f"{channel_id}: {err}"},
            ) from err
        posts.append(post)
        touched.add(entry.entry_id)

    for entry in _loaded_entries(hass):
        if entry.entry_id in touched:
            await entry.runtime_data.coordinator.async_request_refresh()

    return {"posts": posts}


async def _create_idea(call: ServiceCall) -> ServiceResponse:
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = next((e for e in _loaded_entries(call.hass) if e.entry_id == entry_id), None)
    if entry is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="entry_not_loaded"
        )
    try:
        idea = await entry.runtime_data.client.create_idea(
            entry.runtime_data.coordinator.organization_id,
            text=call.data.get(ATTR_TEXT),
            title=call.data.get(ATTR_TITLE),
        )
    except BufferError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="create_idea_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    return {"idea": idea}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_POST,
        _create_post,
        schema=CREATE_POST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_IDEA,
        _create_idea,
        schema=CREATE_IDEA_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

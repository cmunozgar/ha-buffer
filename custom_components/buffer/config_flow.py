"""Config flow for Buffer."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import BufferAuthError, BufferClient, BufferError, Organization
from .const import (
    CONF_ORGANIZATION_ID,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

API_KEY_SCHEMA = vol.Schema(
    {vol.Required(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)


class BufferConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up Buffer with a personal API key."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._orgs: list[Organization] = []

    async def _fetch_orgs(self, api_key: str) -> tuple[list[Organization], dict[str, str]]:
        client = BufferClient(async_get_clientsession(self.hass), api_key)
        try:
            orgs = await client.get_organizations()
        except BufferAuthError:
            return [], {"base": "invalid_auth"}
        except BufferError:
            return [], {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error validating Buffer API key")
            return [], {"base": "unknown"}
        if not orgs:
            return [], {"base": "no_organizations"}
        return orgs, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._orgs, errors = await self._fetch_orgs(user_input[CONF_API_KEY])
            if not errors:
                self._api_key = user_input[CONF_API_KEY]
                if len(self._orgs) == 1:
                    return await self._create(self._orgs[0])
                return await self.async_step_organization()

        return self.async_show_form(
            step_id="user",
            data_schema=API_KEY_SCHEMA,
            errors=errors,
            description_placeholders={"api_url": "https://publish.buffer.com/settings/api"},
        )

    async def async_step_organization(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            org = next(o for o in self._orgs if o.id == user_input[CONF_ORGANIZATION_ID])
            return await self._create(org)

        options = [SelectOptionDict(value=o.id, label=o.name) for o in self._orgs]
        return self.async_show_form(
            step_id="organization",
            data_schema=vol.Schema(
                {vol.Required(CONF_ORGANIZATION_ID): SelectSelector(SelectSelectorConfig(options=options))}
            ),
        )

    async def _create(self, org: Organization) -> ConfigFlowResult:
        await self.async_set_unique_id(org.id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=org.name,
            data={CONF_API_KEY: self._api_key, CONF_ORGANIZATION_ID: org.id},
        )

    # -- Re-authentication ------------------------------------------------ #

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            orgs, errors = await self._fetch_orgs(user_input[CONF_API_KEY])
            if not errors and entry.data[CONF_ORGANIZATION_ID] not in {o.id for o in orgs}:
                errors = {"base": "wrong_account"}
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: user_input[CONF_API_KEY]}
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=API_KEY_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BufferOptionsFlow()


class BufferOptionsFlow(OptionsFlow):
    """Polling interval option."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL_MINUTES: int(user_input[CONF_SCAN_INTERVAL_MINUTES])}
            )
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL_MINUTES, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL_MINUTES,
                            max=MAX_SCAN_INTERVAL_MINUTES,
                            step=5,
                            unit_of_measurement="min",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )

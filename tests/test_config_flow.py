from unittest.mock import AsyncMock

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.buffer.api import BufferAuthError, Organization
from custom_components.buffer.const import DOMAIN

from .conftest import ORG_ID


async def test_single_org_creates_entry(hass, mock_client):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "k"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Carlos Org"
    assert result["data"] == {"api_key": "k", "organization_id": ORG_ID}


async def test_multi_org_asks(hass, mock_client):
    mock_client.get_organizations = AsyncMock(
        return_value=[Organization("a", "A"), Organization("b", "B")]
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "k"})
    assert result["step_id"] == "organization"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"organization_id": "b"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "B"


async def test_invalid_auth(hass, mock_client):
    mock_client.get_organizations = AsyncMock(side_effect=BufferAuthError("nope"))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "bad"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_duplicate_aborts(hass, mock_client, config_entry):
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "k"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options(hass, mock_client, config_entry):
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval_minutes": 30})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {"scan_interval_minutes": 30}

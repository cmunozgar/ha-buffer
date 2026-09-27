from datetime import timedelta

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from custom_components.buffer.api import BufferAuthError
from custom_components.buffer.const import DOMAIN


async def _setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities(hass, mock_client, config_entry):
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    states = {s.entity_id: s for s in hass.states.async_all()}
    print(sorted(states))

    q = hass.states.get("sensor.carlos_linkedin_linkedin_queue_size")
    assert q.state == "2"
    nxt = hass.states.get("sensor.carlos_linkedin_linkedin_next_post")
    assert nxt.attributes["post_id"] == "p1"
    assert hass.states.get("sensor.carlos_linkedin_linkedin_last_sent").attributes["post_id"] == "p0"
    assert hass.states.get("binary_sensor.carlos_ig_instagram_disconnected").state == "on"
    assert hass.states.get("binary_sensor.carlos_ig_instagram_queue_empty").state == "on"
    assert hass.states.get("binary_sensor.carlos_linkedin_linkedin_queue_empty").state == "off"
    failed = hass.states.get("sensor.carlos_ig_instagram_failed_posts")
    assert failed.state == "1" and failed.attributes["latest_error"] == "Token expired"
    assert hass.states.get("sensor.buffer_carlos_org_api_requests_remaining").state == "240"
    cal = hass.states.get("calendar.buffer_carlos_org_content_calendar")
    assert cal.attributes["message"].startswith("LinkedIn · Carlos LinkedIn: First LinkedIn post")


async def test_calendar_events(hass, mock_client, config_entry, hass_client):
    await _setup(hass, config_entry)
    client = await hass_client()
    start = (dt_util.utcnow() - timedelta(days=2)).isoformat()
    end = (dt_util.utcnow() + timedelta(days=2)).isoformat()
    resp = await client.get(
        "/api/calendars/calendar.buffer_carlos_org_content_calendar",
        params={"start": start, "end": end},
    )
    events = await resp.json()
    assert [e["uid"] for e in events] == ["p0", "p1", "p2"]
    assert events[0]["summary"].startswith("✓ ")


async def test_create_post_by_device(hass, mock_client, config_entry):
    await _setup(hass, config_entry)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "channel_ch_li")})
    resp = await hass.services.async_call(
        DOMAIN, "create_post",
        {"device_id": [device.id], "text": "Hello", "image_urls": ["https://e.com/a.jpg"]},
        blocking=True, return_response=True,
    )
    assert resp == {"posts": [{"id": "new1", "status": "scheduled"}]}
    kwargs = mock_client.create_post.call_args.kwargs
    assert kwargs["channel_id"] == "ch_li" and kwargs["mode"] == "addToQueue"
    assert kwargs["image_urls"] == ["https://e.com/a.jpg"]


async def test_create_post_scheduled(hass, mock_client, config_entry):
    await _setup(hass, config_entry)
    await hass.services.async_call(
        DOMAIN, "create_post",
        {"channel_id": "ch_li", "text": "Later", "due_at": "2030-01-01 10:00:00"},
        blocking=True,
    )
    kwargs = mock_client.create_post.call_args.kwargs
    assert kwargs["mode"] == "customScheduled"
    assert kwargs["due_at"].tzinfo is not None


async def test_create_post_validation(hass, mock_client, config_entry):
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "create_post", {"channel_id": "nope", "text": "x"}, blocking=True
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "create_post",
            {"channel_id": "ch_li", "text": "x", "mode": "custom_scheduled"}, blocking=True,
        )
    org_device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "org_org1")})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "create_post", {"device_id": org_device.id, "text": "x"}, blocking=True
        )
    mock_client.create_post.assert_not_called()


async def test_create_idea(hass, mock_client, config_entry):
    await _setup(hass, config_entry)
    resp = await hass.services.async_call(
        DOMAIN, "create_idea",
        {"config_entry_id": config_entry.entry_id, "title": "t", "text": "x"},
        blocking=True, return_response=True,
    )
    assert resp["idea"]["id"] == "idea1"
    mock_client.create_idea.assert_awaited_once_with("org1", text="x", title="t")


async def test_notify(hass, mock_client, config_entry):
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "notify", "send_message",
        {"entity_id": "notify.carlos_linkedin_linkedin_add_to_queue", "message": "Hi", "title": "T"},
        blocking=True,
    )
    mock_client.create_post.assert_awaited_once_with("ch_li", "T\n\nHi")


async def test_auth_failure_starts_reauth(hass, mock_client, config_entry):
    mock_client.get_overview.side_effect = BufferAuthError("bad")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)

"""Tests for the raw GraphQL client against mocked HTTP."""

import pytest

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.buffer.api import (
    API_URL,
    BufferAuthError,
    BufferClient,
    BufferMutationError,
    BufferRateLimitError,
)

OVERVIEW = {
    "data": {
        "channels": [
            {"id": "c1", "name": "n", "displayName": "D", "service": "linkedin",
             "isDisconnected": False, "isQueuePaused": False, "isLocked": False}
        ],
        "scheduled": {"edges": [
            {"node": {"id": "b", "text": "B", "status": "scheduled", "channelId": "c1", "dueAt": "2030-01-02T00:00:00.000Z"}},
            {"node": {"id": "a", "text": "A", "status": "scheduled", "channelId": "c1", "dueAt": "2030-01-01T00:00:00.000Z"}},
        ]},
        "sent": {"edges": []},
        "failed": {"edges": [{"node": {"id": "f", "status": "error", "channelId": "c1", "error": {"message": "boom"}}}]},
    }
}


async def test_overview(hass, aioclient_mock):
    aioclient_mock.post(API_URL, json=OVERVIEW, headers={"RateLimit": "r=99, t=100"})
    client = BufferClient(async_get_clientsession(hass), "k")
    ov = await client.get_overview("org")
    assert [p.id for p in ov.scheduled] == ["a", "b"]
    assert ov.failed[0].error_message == "boom"
    assert ov.channels["c1"].title == "D"
    assert ov.rate_limit_remaining == 99
    body = aioclient_mock.mock_calls[0][2]
    assert body["variables"] == {"org": "org"}
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "Bearer k"


async def test_rate_limit(hass, aioclient_mock):
    aioclient_mock.post(API_URL, status=429, headers={"Retry-After": "42"}, json={})
    client = BufferClient(async_get_clientsession(hass), "k")
    with pytest.raises(BufferRateLimitError) as err:
        await client.get_organizations()
    assert err.value.retry_after == 42


async def test_graphql_auth_error(hass, aioclient_mock):
    aioclient_mock.post(API_URL, json={"errors": [{"message": "no", "extensions": {"code": "UNAUTHORIZED"}}]})
    client = BufferClient(async_get_clientsession(hass), "k")
    with pytest.raises(BufferAuthError):
        await client.get_organizations()


async def test_mutation_error(hass, aioclient_mock):
    aioclient_mock.post(API_URL, json={"data": {"createPost": {"message": "Text too long"}}})
    client = BufferClient(async_get_clientsession(hass), "k")
    with pytest.raises(BufferMutationError, match="Text too long"):
        await client.create_post("c1", "x" * 5000)


async def test_create_post_payload(hass, aioclient_mock):
    aioclient_mock.post(API_URL, json={"data": {"createPost": {"post": {"id": "p"}}}})
    client = BufferClient(async_get_clientsession(hass), "k")
    await client.create_post("c1", "hi", image_urls=["https://e.com/a.jpg"])
    sent = aioclient_mock.mock_calls[0][2]["variables"]["input"]
    assert sent == {
        "channelId": "c1", "text": "hi", "schedulingType": "automatic",
        "mode": "addToQueue", "assets": [{"image": {"url": "https://e.com/a.jpg"}}],
    }

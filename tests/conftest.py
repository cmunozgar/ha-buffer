"""Fixtures for Buffer tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.util import dt as dt_util

from custom_components.buffer.api import Channel, Organization, Overview, Post
from custom_components.buffer.const import CONF_ORGANIZATION_ID, DOMAIN

ORG_ID = "org1"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def make_overview() -> Overview:
    now = dt_util.utcnow()
    li = Channel("ch_li", "carlos", "Carlos LinkedIn", "linkedin", None, "Europe/Madrid",
                 None, False, False, False)
    ig = Channel("ch_ig", "carlos.ig", None, "instagram", None, "Europe/Madrid",
                 None, True, True, False)
    return Overview(
        channels={li.id: li, ig.id: ig},
        scheduled=[
            Post("p1", "First LinkedIn post\nmore", "scheduled", "ch_li", "linkedin",
                 now + timedelta(hours=2), None, None, None),
            Post("p2", "Second LinkedIn post", "scheduled", "ch_li", "linkedin",
                 now + timedelta(days=1), None, None, None),
        ],
        sent=[
            Post("p0", "Yesterday", "sent", "ch_li", "linkedin",
                 now - timedelta(days=1), now - timedelta(days=1), "https://x/p0", None),
        ],
        failed=[
            Post("pf", "Broken", "error", "ch_ig", "instagram",
                 now - timedelta(hours=3), None, None, "Token expired"),
        ],
        rate_limit_remaining=240,
    )


@pytest.fixture
def mock_client():
    with (
        patch("custom_components.buffer.BufferClient", autospec=True) as cls,
        patch("custom_components.buffer.config_flow.BufferClient", new=cls),
    ):
        client = cls.return_value
        client.get_organizations = AsyncMock(return_value=[Organization(ORG_ID, "Carlos Org")])
        client.get_overview = AsyncMock(side_effect=lambda _org: make_overview())
        client.create_post = AsyncMock(return_value={"id": "new1", "status": "scheduled"})
        client.create_idea = AsyncMock(return_value={"id": "idea1", "content": {"title": "t", "text": "x"}})
        yield client


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Carlos Org",
        unique_id=ORG_ID,
        data={"api_key": "secret", CONF_ORGANIZATION_ID: ORG_ID},
    )

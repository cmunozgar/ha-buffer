"""Constants for the Buffer integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "buffer"
API_URL: Final = "https://api.buffer.com"

CONF_ORGANIZATION_ID: Final = "organization_id"
CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"

# Buffer's smallest daily quota is 250 requests / 24h per API key.
# One poll = one HTTP request (all data is fetched in a single batched query),
# so 15 minutes = 96 requests/day, leaving plenty of room for actions.
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 15
MIN_SCAN_INTERVAL_MINUTES: Final = 10
MAX_SCAN_INTERVAL_MINUTES: Final = 240
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES)

# How many posts to pull per bucket in each poll.
SCHEDULED_PAGE_SIZE: Final = 100
SENT_PAGE_SIZE: Final = 50
ERROR_PAGE_SIZE: Final = 50

# Default duration used to render a post as a calendar event.
CALENDAR_EVENT_MINUTES: Final = 15

SERVICE_CREATE_POST: Final = "create_post"
SERVICE_CREATE_IDEA: Final = "create_idea"

ATTR_CHANNEL_ID: Final = "channel_id"
ATTR_TEXT: Final = "text"
ATTR_TITLE: Final = "title"
ATTR_MODE: Final = "mode"
ATTR_DUE_AT: Final = "due_at"
ATTR_IMAGE_URLS: Final = "image_urls"
ATTR_SAVE_TO_DRAFT: Final = "save_to_draft"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"

# HA-friendly snake_case -> Buffer ShareMode enum.
SHARE_MODES: Final = {
    "add_to_queue": "addToQueue",
    "share_next": "shareNext",
    "share_now": "shareNow",
    "custom_scheduled": "customScheduled",
}

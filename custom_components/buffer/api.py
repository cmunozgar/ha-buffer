"""Minimal async client for Buffer's public GraphQL API.

Kept dependency-free (just aiohttp, which Home Assistant already ships) so the
integration can be installed via HACS without extra requirements. If this is
ever submitted to HA core, this module should move to its own PyPI package.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import re
from typing import Any

import aiohttp

from .const import API_URL, ERROR_PAGE_SIZE, SCHEDULED_PAGE_SIZE, SENT_PAGE_SIZE

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

AUTH_ERROR_CODES = {"UNAUTHORIZED", "UNAUTHENTICATED", "FORBIDDEN"}
_MIN_DT = datetime.min.replace(tzinfo=UTC)
_MAX_DT = datetime.max.replace(tzinfo=UTC)


class BufferError(Exception):
    """Base error for the Buffer client."""


class BufferConnectionError(BufferError):
    """Network problem or unexpected server response."""


class BufferAuthError(BufferError):
    """The API key is invalid or lacks access."""


class BufferRateLimitError(BufferError):
    """A rate-limit window is exhausted."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class BufferMutationError(BufferError):
    """A mutation returned a typed MutationError (validation etc.)."""


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(slots=True)
class Organization:
    id: str
    name: str


@dataclass(slots=True)
class Channel:
    id: str
    name: str
    display_name: str | None
    service: str
    avatar: str | None
    timezone: str | None
    external_link: str | None
    is_disconnected: bool
    is_queue_paused: bool
    is_locked: bool

    @property
    def title(self) -> str:
        return self.display_name or self.name

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Channel:
        return cls(
            id=raw["id"],
            name=raw.get("name") or raw["id"],
            display_name=raw.get("displayName"),
            service=raw.get("service") or "unknown",
            avatar=raw.get("avatar"),
            timezone=raw.get("timezone"),
            external_link=raw.get("externalLink"),
            is_disconnected=bool(raw.get("isDisconnected")),
            is_queue_paused=bool(raw.get("isQueuePaused")),
            is_locked=bool(raw.get("isLocked")),
        )


@dataclass(slots=True)
class Post:
    id: str
    text: str
    status: str
    channel_id: str
    channel_service: str | None
    due_at: datetime | None
    sent_at: datetime | None
    external_link: str | None
    error_message: str | None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Post:
        return cls(
            id=raw["id"],
            text=raw.get("text") or "",
            status=raw.get("status") or "unknown",
            channel_id=raw.get("channelId") or "",
            channel_service=raw.get("channelService"),
            due_at=_dt(raw.get("dueAt")),
            sent_at=_dt(raw.get("sentAt")),
            external_link=raw.get("externalLink"),
            error_message=(raw.get("error") or {}).get("message"),
        )


@dataclass(slots=True)
class Overview:
    """Everything the coordinator needs, fetched in ONE request."""

    channels: dict[str, Channel]
    scheduled: list[Post]
    sent: list[Post]
    failed: list[Post]
    rate_limit_remaining: int | None = None

    def scheduled_for(self, channel_id: str) -> list[Post]:
        return [p for p in self.scheduled if p.channel_id == channel_id]

    def failed_for(self, channel_id: str) -> list[Post]:
        return [p for p in self.failed if p.channel_id == channel_id]

    def last_sent_for(self, channel_id: str) -> Post | None:
        posts = [p for p in self.sent if p.channel_id == channel_id]
        return max(posts, key=lambda p: p.sent_at or p.due_at or _MIN_DT, default=None)


# --------------------------------------------------------------------------- #
# GraphQL documents
# --------------------------------------------------------------------------- #

ORGANIZATIONS_QUERY = """
query Organizations {
  account {
    organizations { id name }
  }
}
"""

_POST_FIELDS = """
fragment HaPost on Post {
  id
  text
  status
  dueAt
  sentAt
  channelId
  channelService
  externalLink
  error { message }
}
"""

# Batched + aliased per Buffer's "Efficient API usage" guide: one HTTP request
# (= one unit of rate-limit quota) per poll, regardless of channel count.
OVERVIEW_QUERY = (
    """
query HaOverview($org: OrganizationId!) {
  channels(input: { organizationId: $org }) {
    id
    name
    displayName
    service
    avatar
    timezone
    externalLink
    isDisconnected
    isQueuePaused
    isLocked
  }
  scheduled: posts(
    first: %(scheduled)d
    input: {
      organizationId: $org
      filter: { status: [scheduled] }
      sort: { field: dueAt, direction: asc }
    }
  ) { edges { node { ...HaPost } } }
  sent: posts(
    first: %(sent)d
    input: {
      organizationId: $org
      filter: { status: [sent] }
      sort: { field: dueAt, direction: desc }
    }
  ) { edges { node { ...HaPost } } }
  failed: posts(
    first: %(failed)d
    input: {
      organizationId: $org
      filter: { status: [error] }
      sort: { field: dueAt, direction: desc }
    }
  ) { edges { node { ...HaPost } } }
}
"""
    % {"scheduled": SCHEDULED_PAGE_SIZE, "sent": SENT_PAGE_SIZE, "failed": ERROR_PAGE_SIZE}
    + _POST_FIELDS
)

CREATE_POST_MUTATION = """
mutation HaCreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess {
      post { id text dueAt status channelId }
    }
    ... on MutationError { message }
  }
}
"""

CREATE_IDEA_MUTATION = """
mutation HaCreateIdea($org: OrganizationId!, $title: String, $text: String) {
  createIdea(input: { organizationId: $org, content: { title: $title, text: $text } }) {
    ... on Idea { id content { title text } }
    ... on MutationError { message }
  }
}
"""

_RATE_R = re.compile(r"\br=(\d+)")


def _parse_remaining(headers: Any) -> int | None:
    """Parse the lowest `r=` (requests remaining) across RateLimit headers."""
    values: list[int] = []
    for raw in headers.getall("RateLimit", []) if hasattr(headers, "getall") else []:
        values += [int(m) for m in _RATE_R.findall(raw)]
    return min(values) if values else None


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


class BufferClient:
    """Tiny GraphQL client bound to one API key."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key
        self.rate_limit_remaining: int | None = None

    async def _execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "HomeAssistant-Buffer/0.1",
        }
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            async with self._session.post(
                API_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT
            ) as resp:
                remaining = _parse_remaining(resp.headers)
                if remaining is not None:
                    self.rate_limit_remaining = remaining

                if resp.status == 429:
                    retry = resp.headers.get("Retry-After")
                    raise BufferRateLimitError(
                        "Buffer API rate limit exceeded",
                        int(retry) if retry and retry.isdigit() else None,
                    )
                if resp.status in (401, 403):
                    raise BufferAuthError(f"HTTP {resp.status}")
                if resp.status >= 400:
                    text = await resp.text()
                    raise BufferConnectionError(f"HTTP {resp.status}: {text[:200]}")
                body = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise BufferConnectionError(str(err)) from err

        errors = body.get("errors") or []
        if errors:
            codes = {(e.get("extensions") or {}).get("code") for e in errors}
            message = "; ".join(e.get("message", "unknown error") for e in errors)
            if codes & AUTH_ERROR_CODES:
                raise BufferAuthError(message)
            if "RATE_LIMIT_EXCEEDED" in codes:
                raise BufferRateLimitError(message)
            # Partial data may still be usable; only fail if there is none.
            if not body.get("data"):
                raise BufferConnectionError(message)
            _LOGGER.debug("Buffer returned partial errors: %s", message)

        return body.get("data") or {}

    # -- Queries ---------------------------------------------------------- #

    async def get_organizations(self) -> list[Organization]:
        data = await self._execute(ORGANIZATIONS_QUERY)
        orgs = ((data.get("account") or {}).get("organizations")) or []
        return [Organization(id=o["id"], name=o.get("name") or o["id"]) for o in orgs]

    async def get_overview(self, organization_id: str) -> Overview:
        data = await self._execute(OVERVIEW_QUERY, {"org": organization_id})

        def posts(alias: str) -> list[Post]:
            edges = ((data.get(alias) or {}).get("edges")) or []
            return [Post.from_api(e["node"]) for e in edges if e.get("node")]

        channels = {c["id"]: Channel.from_api(c) for c in data.get("channels") or []}
        scheduled = sorted(
            posts("scheduled"), key=lambda p: p.due_at or _MAX_DT
        )
        return Overview(
            channels=channels,
            scheduled=scheduled,
            sent=posts("sent"),
            failed=posts("failed"),
            rate_limit_remaining=self.rate_limit_remaining,
        )

    # -- Mutations -------------------------------------------------------- #

    async def create_post(
        self,
        channel_id: str,
        text: str,
        mode: str = "addToQueue",
        due_at: datetime | None = None,
        image_urls: list[str] | None = None,
        save_to_draft: bool = False,
    ) -> dict[str, Any]:
        post_input: dict[str, Any] = {
            "channelId": channel_id,
            "text": text,
            "schedulingType": "automatic",
            "mode": mode,
            "assets": [{"image": {"url": url}} for url in image_urls or []],
        }
        if due_at is not None:
            post_input["dueAt"] = due_at.isoformat()
        if save_to_draft:
            post_input["saveToDraft"] = True

        data = await self._execute(CREATE_POST_MUTATION, {"input": post_input})
        result = data.get("createPost") or {}
        if "post" not in result:
            raise BufferMutationError(result.get("message") or "createPost failed")
        return result["post"]

    async def create_idea(
        self, organization_id: str, text: str | None, title: str | None = None
    ) -> dict[str, Any]:
        data = await self._execute(
            CREATE_IDEA_MUTATION, {"org": organization_id, "title": title, "text": text}
        )
        result = data.get("createIdea") or {}
        if "id" not in result:
            raise BufferMutationError(result.get("message") or "createIdea failed")
        return result

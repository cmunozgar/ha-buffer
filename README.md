# Buffer for Home Assistant

A custom integration that connects Home Assistant to [Buffer](https://buffer.com) through Buffer's [public GraphQL API](https://developers.buffer.com). It works in two directions:

- **Buffer → Home Assistant:** entities for your queues, the next and last posts, failed posts and disconnected channels, plus a content calendar.
- **Home Assistant → Buffer:** actions that post to channels or save ideas from automations.

> Status: early (0.1.0). Only the stable parts of the API are used: channels, posts and ideas. The experimental content-item and tag APIs are not.

## What you get

Each Buffer channel shows up as a **device**, linked to a device for your organization.

| Entity | Per | What it shows |
|---|---|---|
| `sensor.*_queue_size` | channel | Number of scheduled posts |
| `sensor.*_next_post` | channel | Time of the next post (attributes: text, post ID) |
| `sensor.*_last_sent` | channel | Time the last post was sent (attributes: text, link) |
| `sensor.*_failed_posts` | channel | Failed posts (attribute: latest error) |
| `binary_sensor.*_disconnected` | channel | On when the channel needs reconnecting |
| `binary_sensor.*_queue_paused` | channel | On when the queue is paused |
| `binary_sensor.*_queue_empty` | channel | On when nothing is scheduled |
| `notify.*_add_to_queue` | channel | `notify.send_message` adds the message to the queue |
| `calendar.*_content_calendar` | org | Scheduled posts plus recently sent ones (✓) |
| `sensor.*_scheduled_posts` / `_failed_posts` | org | Totals |
| `sensor.*_api_requests_remaining` | org | Diagnostic: requests left in the tightest rate-limit window |

### Actions

**`buffer.create_post`** posts to one or more channels. You pick channel devices in the UI or pass raw `channel_id`s.
Modes: `add_to_queue` (default), `share_next`, `share_now`, `custom_scheduled`. Setting `due_at` implies `custom_scheduled`.
It returns the created posts as a response, so you can use `response_variable` in scripts.

**`buffer.create_idea`** saves an idea to Buffer's Ideas board so a person can review it before anything is published.

## Installation

1. HACS → ⋮ → Custom repositories → add `https://github.com/cmunozgar/ha-buffer`, category *Integration*, then download **Buffer**. Alternatively, copy `custom_components/buffer` into your `config/custom_components/`.
2. Restart Home Assistant.
3. Go to Settings → Devices & services → Add integration → **Buffer**.
4. Paste an API key from <https://publish.buffer.com/settings/api>.
   If your account has several organizations, you'll be asked to choose one. Add the integration again for each extra organization.

### Optional: check the API first

This runs read-only and uses 2 requests:

```bash
pip install aiohttp
BUFFER_API_KEY=... python scripts/smoke_test.py
```

## Rate limits

Buffer's limits apply **per API key**: 100 requests per 15 minutes, **250 per day** (500 on Team), and 3,000–15,000 per 30 days depending on plan.

Each poll fetches channels, scheduled posts, sent posts and failed posts in **one batched request**, however many channels you have. The default poll interval is 15 minutes, which is 96 requests a day. That leaves room for actions, each of which costs one request plus a refresh.

You can change the interval in the integration's **Configure** dialog (10–240 minutes). If you also use the API key elsewhere (scripts, MCP, other tools), use a longer interval.

## Examples

**Post a daily solar recap**

```yaml
automation:
  - alias: Solar recap to Buffer
    triggers:
      - trigger: time
        at: "20:30:00"
    actions:
      - action: buffer.create_post
        data:
          channel_id: YOUR_CHANNEL_ID
          text: >
            Today our roof produced {{ states('sensor.solar_energy_today') }} kWh ☀️
```

**Get told when a channel disconnects**

```yaml
automation:
  - alias: Buffer channel disconnected
    triggers:
      - trigger: state
        entity_id: binary_sensor.carlos_linkedin_linkedin_disconnected
        to: "on"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "Buffer: LinkedIn needs reconnecting"
```

**Refill the queue before it runs dry.** Save an idea as a prompt to write more posts:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.carlos_linkedin_linkedin_queue_empty
    to: "on"
actions:
  - action: buffer.create_idea
    data:
      config_entry_id: YOUR_ENTRY_ID
      title: "LinkedIn queue is empty"
      text: "Write 3 posts for next week."
```

## Images

Buffer has **no upload endpoint**. Images must be public, direct, stable HTTPS URLs, and Buffer fetches them *when the post publishes*, not when you create it.

Camera snapshots saved in `/config/www` are only reachable if your instance is exposed publicly, for example through Nabu Casa. Even then, avoid signed or expiring URLs for scheduled posts.

## Development

```bash
uv venv -p 3.13 && uv pip install pytest-homeassistant-custom-component
pytest
```

## Roadmap ideas

- Media hosting helper that uploads snapshots to S3 or R2 with stable URLs
- `buffer.delete_post` action, and turning a calendar event into a post
- Per-channel post metrics (`aggregatedPostMetrics`)
- Moving `api.py` into its own PyPI package (`aiobuffer`) to allow a submission to HA core

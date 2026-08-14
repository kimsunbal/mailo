# docs/channels/discord — Discord webhooks

> **What these are**: summaries of the official documentation. The originals are
> authoritative and these are copies, so where they disagree, follow the original.
> Each file carries its source URL and the date it was checked.
> Checked: **2026-08-13**

| File | Contents |
|---|---|
| [01-webhook-api.md](01-webhook-api.md) | The Execute Webhook endpoint, parameters, and what a webhook URL is |
| [02-embeds.md](02-embeds.md) | The embed object, length limits, per-event colours |
| [03-rate-limits.md](03-rate-limits.md) | Rate limits, handling 429, the invalid-request ban |

## Primary sources

| Source | URL |
|---|---|
| Execute Webhook | <https://docs.discord.com/developers/resources/webhook> |
| Message (embed limits) | <https://docs.discord.com/developers/resources/message> |
| Rate Limits | <https://docs.discord.com/developers/topics/rate-limits> |
| Intro to webhooks (support) | <https://support.discord.com/hc/en-us/articles/228383668> |

## What this means for mailo

### 1. Use embeds — per-event colour is Discord's real advantage

Discord offers one thing no other channel here does: a **coloured bar down the
left side**. `failed` (red) and `done` (green) are distinguishable from the
message list without opening anything. That is the reason for using an embed
rather than plain `content`. → [02-embeds.md](02-embeds.md) §3

### 2. Truncation is measured in **characters**

Discord allows 2,000 characters of `content`, 4,096 in an embed `description`, and
6,000 across the whole message. **All of them count characters, so no byte
arithmetic is needed** — `len()` works as is regardless of script.

Mail has no practical limit, so **truncating once in shared code would waste
information in mail.** The common message carries the full original and each
adapter cuts its own. → [02-embeds.md](02-embeds.md) §2

### 3. The webhook URL is a secret, but **write-only**

The URL by itself is the credential; there is no separate auth header. Anyone who
knows it can post to that channel. But they **cannot read** — it grants no access
to channel history.

That bounds the damage of a leak to spam: notifications already sent cannot be
read back retroactively. It is still a credential, so mode 600 and log masking
apply. → [01-webhook-api.md](01-webhook-api.md) §4

### 4. Discord has to carry `blocked` — a known weakness

With only Discord and mail, **`blocked`, which needs immediacy, rides on Discord
alone.** Mail cannot supply immediacy, so there is no alternative.

And Discord is a chat app. Mobile push does arrive, but it is subject to
per-channel mute and notification settings, and the user is likely already numb to
notifications from dozens of channels. **The deliverability of `blocked` therefore
depends on user settings.**

The only mitigation is guidance, which the README and `mailo init` have to state:

- **Create a dedicated channel** for mailo, not mixed in with conversations
- Set that channel's notifications to **"All Messages"**
- Turn on mobile push for that server and channel

None of it is enforceable by us. Recorded in DESIGN.md §6.4.

### 5. No daily cap needed

Unlike Gmail, webhooks have no documented daily sending limit. Rate limiting works
in per-second buckets, and mailo's cooldown (60s) is far slower than that.
`daily_limit` exists on the SMTP channel only.
→ [03-rate-limits.md](03-rate-limits.md) §3

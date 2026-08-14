# 01 — the Execute Webhook endpoint

> Source: <https://docs.discord.com/developers/resources/webhook>
> Checked: 2026-08-13 · the original is authoritative

## 1. Request shape

```
POST /webhooks/{webhook.id}/{webhook.token}
```

The webhook URL looks like:

```
https://discord.com/api/webhooks/{id}/{token}
```

When a user creates a webhook in Discord, that whole URL is what gets copied.
mailo **takes the URL as-is into the config** and posts to it rather than taking it
apart. Asking for `id` and `token` separately would make the user assemble it and
add another place to get it wrong.

## 2. JSON body parameters

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `content` | string | one of four | **2,000 characters max** |
| `embeds` | array | one of four | **up to 10** embed objects |
| `files[n]` | file | one of four | file upload |
| `poll` | object | one of four | a poll |
| `username` | string | | override the webhook's display name |
| `avatar_url` | string | | override the webhook's avatar |
| `tts` | boolean | | text to speech |
| `allowed_mentions` | object | | control mention behaviour |
| `flags` | integer | | only `SUPPRESS_EMBEDS`, `SUPPRESS_NOTIFICATIONS`, `IS_COMPONENTS_V2` |
| `thread_name` | string | | create a thread in a forum or media channel |
| `applied_tags` | array | | tags for a forum or media thread |
| `components` | array | | app-owned, or needs `with_components` |

**At least one of `content`, `embeds`, `files`, or `poll` must be present.**

### 2.1 `username`

`username` overrides the webhook's display name per request, so the machine
identifier could go there: several machines posting to one channel would then be
distinguishable by sender name alone, which is arguably more natural in Discord
than a `[workstation]` prefix in the title.

**mailo keeps the `[machine]` prefix in the title instead**, so that a Discord
notification and a mail notification read identically. Moving it to `username` is
a reasonable option, but presenting the same information two ways across channels
costs more than it gains.

### 2.2 `flags` — quiet notifications

With the `SUPPRESS_NOTIFICATIONS` flag, a message **lands in the channel without
raising a push notification.** That suits the `done` event: keep the record, do not
buzz the phone.

> `flags` is a bit field. The actual bit value of `SUPPRESS_NOTIFICATIONS` has to
> come from the Message Flags table — it is deliberately not transcribed here,
> because getting it wrong fails silently. Check the original when implementing.

## 3. Query parameters and responses

| Parameter | Default | Behaviour |
|---|---|---|
| `wait` | `false` | with `true`, *"waits for server confirmation of message send before response, and returns the created message body"* |
| `thread_id` | | send to a specific thread; an archived thread is automatically unarchived |
| `with_components` | `false` | let a non-owned webhook use non-interactive components |

Responses:

- `wait=true` → **200 OK** plus the message object
- `wait=false` → **204 No Content**

### 3.1 mailo sends with `wait=true`

The default is `false`, but mailo sends `true`.

With `false` all you learn is that Discord accepted the request; **whether the
message actually reached the channel is unknown.** Since delivery is the entire job
of a notification tool, being unable to distinguish "accepted" from "delivered" is
not acceptable. It costs a little latency, but the hook path runs `async: true`, so
it does not hold the session (DESIGN.md §5.1).

## 4. What a webhook URL is — a secret, but write-only

The URL by itself is the credential; there is no separate auth header. Which means:

- **anyone** who knows the URL can post to that channel
- but they **cannot read** it — there is no access to channel history

### 4.1 Blast radius of a leak

| | What a leak allows |
|---|---|
| Discord webhook URL | posting fake messages to that channel |
| | reading past or present notifications is **not possible** |

Being write-only is a real safety margin. Even if the credential leaks,
**notifications already sent cannot be read back** — including any working paths or
code that ended up in a body. Spam is still possible, so it stays treated as a
secret.

### 4.2 How mailo handles it

- **Mode 600 enforced** on the config file (DESIGN.md §6), same as every other secret
- Overridable with the `$MAILO_DISCORD_WEBHOOK_URL` environment variable
- **The URL is never written to the log.** The reflex of printing the request URL in
  an error log is itself the leak. Logging masks it as `.../webhooks/{id}/***`.

## 5. Creating a webhook (what the user does)

It is created in server channel settings: Channel Settings → Integrations →
Webhooks → New Webhook → copy the URL. **Only possible in a server channel; not in
a DM.** Creating one requires the Manage Webhooks permission on that channel.

> The Discord support page
> (<https://support.discord.com/hc/en-us/articles/228383668>) is authoritative for
> the UI steps. It returned 403 to automated access while these notes were written,
> so the original could not be checked — open it and confirm before transcribing
> the steps into a README.

`mailo init` accepts this URL as a paste. A human has to go through the web UI, so
**it cannot be automated, which is why this channel is optional** (→ `../README.md`).

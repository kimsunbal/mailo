# 7–8. Channels and message format

> Part of the [mailo design notes](README.md).

## 7. Channel implementation

All standard library. Each adapter exposes `send(...)` and raises on failure.

| Channel | Mechanism | Notes |
|---|---|---|
| `discord` | `POST {webhook_url}` with a JSON body (`embeds`) | carries immediacy |
| `smtp` | `smtplib.SMTP_SSL` (465) or `SMTP` + `starttls()` (587) | inherits the current `mailer.py` logic |

**These two are the whole set.** Discord is 20–30 lines of `urllib.request` and
SMTP is about the same with `smtplib`. **The case against apprise** got clearer as
the channel count shrank: there is no reason to pull in a library supporting
eighty-odd services for two adapters, and "drop one file into a container and it
works" is a real asset of this tool.

The cost of two channels is recorded in §6.4 — `blocked` immediacy rests on Discord.

### 7.1 The adapter contract, as settled by the reference reading

1. **Each adapter truncates on its own terms.** The common message carries the
   full original and adapters cut it. Discord allows 4,096 **characters** in an
   embed `description`, 2,000 in `content`, and 6,000 in total. SMTP has no
   practical limit. Truncating once in shared code would waste information in
   mail. Discord counts characters, so no byte arithmetic is needed.
2. **Discord is sent with `wait=true`.** The default, `false`, only reports that
   the request was accepted and says nothing about whether the message reached the
   channel. Delivery being the entire job of a notifier, failing to distinguish
   "accepted" from "delivered" is not acceptable.
3. **SMTP defaults to implicit TLS (465), with STARTTLS (587) as a configured
   alternative.** RFC 8314 recommends implicit TLS over STARTTLS. **There is no
   plaintext mode.** Meeting a server without STARTTLS is a failure, not a reason
   to fall back.
4. **The TLS context is always `ssl.create_default_context()`.** There is no
   option that turns verification off.
5. **Exceptions split into retryable and not.**
   - Pointless to retry (configuration errors): `SMTPAuthenticationError`,
     `SMTPRecipientsRefused`, `SMTPSenderRefused`, `SMTPNotSupportedError`,
     **HTTP 401/403/404** (webhook deleted or wrong URL) → give up immediately and
     log **how to fix it** (an app password is revoked automatically when the
     account password changes → say to re-issue it; a webhook URL needs
     re-issuing → say where).
   - Worth retrying: `SMTPServerDisconnected`, `SMTPConnectError`, `TimeoutError`,
     HTTP 429/5xx → one or two attempts with a short backoff. **429 honours the
     `retry_after` Discord returns, and gives up when it exceeds 60 seconds** — a
     `blocked` notification two minutes late is the same as one never sent.
   - `SMTPException` subclasses `OSError`, so **catch `SMTPException` first.**
     Catching `OSError` broadly would retry authentication failures.
   - **The retry ceiling is hard-coded, not exposed as a setting.** No user should
     be able to enter a large value and get their own IP caught by Discord's
     invalid-request ban.
6. **How an event looks is the adapter's decision** (see section 8).

Sends are attempted per channel independently, and one failing does not stop the
rest. Even if all of them fail, the hook path still exits 0 (§5.1).
→ [../channels/README.md](../channels/README.md)

## 8. Message format

```
subject:  [{machine}] {icon} {summary}
body:     event     blocked
          project   exp-042
          elapsed   2h 14m          (when applicable)
          exit      137             (when applicable)
          -----
          {optional context / log tail}
```

Icons: `blocked` ⏸ / `failed` ❌ / `done` ✅ / `custom` 🔔

### 8.1 Presentation differs per channel

The common message carries only the `event` value; **each adapter decides how to
present it.**

| Channel | Event shown as | Body structure |
|---|---|---|
| `discord` | the embed's **left colour bar** plus a title emoji | metadata as `fields` |
| `smtp` | an emoji in the subject line | the text block above, as is |

Discord embed colours (`color` is an **integer**, not a string):

| Event | Colour | Hex |
|---|---|---|
| `blocked` | orange | `0xE8A33D` |
| `failed` | red | `0xD64545` |
| `done` | green | `0x4CAF50` |
| `custom` | grey | `0x8A8A8A` |

The colour bar distinguishes state from the message list without opening anything,
which is a concrete benefit of using Discord. But **colour is never the only
signal** — the title emoji stays alongside it for colour-blind users.
→ [../channels/discord/02-embeds.md](../channels/discord/02-embeds.md) §3

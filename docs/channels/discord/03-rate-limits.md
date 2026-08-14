# 03 — rate limits and error handling

> Source: <https://docs.discord.com/developers/topics/rate-limits>
> Checked: 2026-08-13 · the original is authoritative

## 1. The global limit

The original: *"up to 50 requests per second to our API."* It applies across all
routes, separately from per-route limits. Bots that consistently exceed it can ask
Discord support for a raise.

mailo's sending frequency (a 60-second cooldown) is orders of magnitude below this,
so it is effectively irrelevant.

## 2. Per-route buckets

Each endpoint has its own bucket, and similar routes sometimes share one. The
**top-level resource** in the path (`channel_id`, `guild_id`, **`webhook_id`**) is
what distinguishes them, so requests to different webhooks are counted separately.

→ Several machines using **different webhooks** do not share a bucket. Copying one
webhook URL onto several machines makes them share one. The latter is more
convenient, but if volume is likely to grow, a webhook per channel is better.

## 3. There is no documented daily cap

Nothing like Gmail's daily sending limit is specified for webhooks. Control happens
through per-second buckets.

→ **The Discord channel gets no `daily_limit`.** Only SMTP has one
(→ [../mail/gmail/02-smtp-settings.md](../mail/gmail/02-smtp-settings.md) §2).
There is a temptation to keep config keys uniform across channels, but imitating a
constraint that does not exist teaches users to believe it is real.

## 4. Response headers

| Header | Contents |
|---|---|
| `X-RateLimit-Limit` | maximum requests allowed |
| `X-RateLimit-Remaining` | requests left in the current window |
| `X-RateLimit-Reset` | reset time (Unix epoch) |
| `X-RateLimit-Reset-After` | *"total time until the current bucket resets"* (seconds) |
| `X-RateLimit-Bucket` | bucket identifier |
| `X-RateLimit-Scope` | `user` / `global` / `shared` |
| `X-RateLimit-Global` | present only on a global 429 |

## 5. Handling 429

Hitting a rate limit returns **HTTP 429** with a JSON body:

```json
{
  "message": "...",
  "retry_after": 1.234,
  "global": false
}
```

`retry_after` is **the number of seconds to wait**.

### The rule mailo follows

**Always honour `retry_after`.** Never override it with your own backoff — retrying
sooner than the server asked contributes to the ban described in section 6.

```python
except urllib.error.HTTPError as e:
    if e.code == 429:
        body = json.loads(e.read() or b"{}")
        wait = float(body.get("retry_after", 5))
        # Cap it — a late notification is worthless
        if wait > 60:
            raise                      # give up, log only
        time.sleep(wait)
        # retry once
```

**Capping the wait is the point.** Immediacy is all a `blocked` notification has,
so waiting two minutes to send it is no different from not sending it. At that
point, give up and log.

`failed` also goes out by mail, so the record survives even when Discord gives up.
`blocked` rides on Discord alone, so giving up there means that notification is
gone — the weakness in DESIGN.md §6.4 shows up here too.

## 6. Invalid-request limit — the Cloudflare ban

> Around *"10,000 invalid requests (401, 403, 429) per 10 minutes"* per IP results
> in temporarily restricted API access.

Ten thousand is unreachable through normal mailo operation. But **a badly written
retry loop can get there** — code that receives 401/404 against a deleted webhook
and retries immediately in a loop can produce thousands per minute.

### Hence the explicit retry classification

| Response | Meaning | Action |
|---|---|---|
| **401 / 403 / 404** | the webhook was deleted or the URL is wrong | **permanent failure, never retry.** The config has to change, so log how to fix it |
| **429** | rate limited | wait `retry_after`, then **one** retry |
| **5xx** | server problem | short backoff, **one or two** retries |
| network error / timeout | transient | short backoff, **one or two** retries |

This is the "retryable or not" split in DESIGN.md §7.1.
**The retry ceiling is hard-coded** and not exposed as a setting; no user should be
able to enter a large value and get their own IP banned.

An example 401/404 message:

```
Discord rejected the request: 404 Not Found
  The webhook was deleted or the URL is wrong.
  Re-issue it under Channel Settings -> Integrations -> Webhooks, then run
    mailo config set discord.webhook_url
  (not retried)
```

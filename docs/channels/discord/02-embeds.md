# 02 — embeds and length limits

> Source: <https://docs.discord.com/developers/resources/message>
> Checked: 2026-08-13 · the original is authoritative

## 1. The embed object

| Field | Contents |
|---|---|
| `title` | title |
| `description` | body |
| `url` | link attached to the title |
| `timestamp` | ISO8601 time |
| `color` | **integer** — the decimal value of an RGB hex (red is `16711680`) |
| `footer` | `{ text, icon_url }` |
| `author` | `{ name, url, icon_url }` |
| `fields` | array of `{ name, value }` (max 25) |

Note that `color` is an **integer**, not a string: `16711680`, not `"#ff0000"`.
Build it with `int("ff0000", 16)` or `0xFF0000`.

## 2. Length limits — counted in characters

| Item | Maximum |
|---|---|
| `content` (without an embed) | **2,000 characters** |
| embed `title` | 256 |
| embed `description` | **4,096** |
| number of `fields` | 25 |
| field `name` | 256 |
| field `value` | 1,024 |
| `footer.text` | 2,048 |
| `author.name` | 256 |
| embeds per message | 10 |
| **combined total** | **6,000** (titles, descriptions, field names and values, footers, author names across all embeds) |

### 2.1 Characters, not bytes

Every limit counts **characters**, so `len()` works as is regardless of script. No
UTF-8 byte arithmetic, no multi-byte boundary handling.

```python
LIMIT = 3900                    # headroom under 4,096
if len(desc) > LIMIT:           # characters — do not encode
    desc = desc[:LIMIT] + "\n… (truncated)"
```

**Do not truncate in shared code when mail is also a target.** SMTP has no
practical length limit, so sending a Discord-sized body to mail as well cuts the
log tail short for no reason. The common message carries the full original and each
adapter truncates its own (DESIGN.md §7.1, rule 1).

## 3. Per-event colour — the real reason to use Discord

An embed draws a coloured bar down its left side. **State is distinguishable from
the message list without opening anything.** No other channel here offers that, and
it is the reason for using an embed rather than plain `content`.

| Event | Colour | Value |
|---|---|---|
| `blocked` | orange | `0xE8A33D` |
| `failed` | red | `0xD64545` |
| `done` | green | `0x4CAF50` |
| `custom` | grey | `0x8A8A8A` |

**Write hex literals only.** `0xE8A33D` is a Python `int` and `json.dumps`
serialises it to decimal, so there is no reason to carry a hand-converted decimal
alongside in code or in prose — converting by hand is how you get it wrong (two
values in this very table were wrong).

Make it overridable in config. And **never depend on colour alone**, for
colour-blind users — the title emoji (⏸ ❌ ✅ 🔔) stays alongside it.

## 4. mailo's payload

```python
import json, urllib.request

COLORS = {"blocked": 0xE8A33D, "failed": 0xD64545,
          "done": 0x4CAF50, "custom": 0x8A8A8A}
ICONS  = {"blocked": "⏸", "failed": "❌", "done": "✅", "custom": "🔔"}

def send(cfg, event, title, body, meta):
    desc = body[:3900] + ("\n… (truncated)" if len(body) > 3900 else "")
    payload = {
        "embeds": [{
            "title": f"{ICONS[event]} {title}"[:256],
            "description": desc,
            "color": COLORS[event],
            "fields": [
                {"name": k, "value": str(v)[:1024], "inline": True}
                for k, v in meta.items()
            ][:25],
        }],
    }
    url = cfg["webhook_url"] + "?wait=true"           # 01 §3.1
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=cfg.get("timeout", 15)) as r:
        r.read()
```

Putting metadata such as `project`, `elapsed`, and `exit` in `fields` gets Discord
to render it as a table. The body text block from DESIGN.md §8 becomes `fields`
here, which is the concrete case of §8.1, "presentation differs per channel".

> **Do not forget to clip `title` at 256.** Titles are usually short enough that
> testing never catches it, but `mailo send -s "$(...)"` with a long string returns
> 400. The combined 6,000 limit is also reachable with enough `fields`.

> Part of the [mailo design notes](README.md).

# 6. Configuration

`~/.config/mailo/config.toml`, overridable with `$MAILO_CONFIG`. **Mode 600 is
enforced**, carrying over the check from the current `mailer.py`, because every
secret — the SMTP password and the Discord webhook URL — lives here.

```toml
# Identifier for this machine, prefixed to every notification title.
# Omit it and socket.gethostname() is used, so this file can be copied verbatim
# to other machines (6.3.7).
machine = "workstation"

[routing]
blocked = ["discord"]            # immediacy is the point -> phone push; assumes the 6.4 setup
failed  = ["discord", "smtp"]    # two independent paths; one can die
done    = ["smtp"]               # a record is enough
custom  = ["smtp"]

[triggers]
cooldown_sec = 60                # suppress repeats of the same (session, event)
# blocked_delay_sec = 90         # opt-in: notify only if still blocked this long
include_message_text = false     # see 6.2
# stop_min_duration_sec = 300    # opt-in; absent means the Stop hook is not registered — 3.1

[channels.smtp]
host = "smtp.gmail.com"          # Gmail is an example, not an assumption
port = 465
security = "tls"                 # "tls" = implicit TLS (465) | "starttls" = STARTTLS (587)
username = "you@gmail.com"       # the full address, not the part before the @
password = ""                    # or $MAILO_SMTP_PASSWORD (an app password on Gmail)
to = "you@gmail.com"
daily_limit = 200                # 0 means unlimited — see 3.2

[channels.discord]
webhook_url = ""                 # or $MAILO_DISCORD_WEBHOOK_URL
# never logged — the URL itself is a credential
```

## 6.1 Format: TOML, Python ≥ 3.11 (settled)

TOML, because `tomllib` is in the standard library from 3.11 — nested structure
without breaking the zero-dependency rule. The current flat `KEY=VALUE` format
cannot express per-channel settings or per-event routing.

**`requires-python = ">=3.11"` is settled** (2026-08-13). The price is giving up
the default Python on Ubuntu 22.04 (3.10). Why this over falling back to JSON or
writing a TOML parser: the config is a file **humans edit by hand**, so comments
and readability matter, and JSON has no comments; writing a parser would be
trading zero dependencies for worse debt. Users on 3.10 can work around it with
`uv tool install --python 3.11 mailo-cli`.

Every secret can be overridden with a `$MAILO_<CHANNEL>_<KEY>` environment
variable. That is the path for containers and CI, where planting a config file is
awkward, and the chmod check is skipped on it.

## 6.2 Privacy — the most important item for a public release

Putting `notification_text` or `last_assistant_message` in a notification body
means **the code, paths, and conversation you are working on leave for a third
party's servers.** Every channel goes through an external service, so there is no
exception.

- `include_message_text` defaults to **false**, and truncates at 200 characters
  even when enabled.
- The default body is **metadata only**: machine, event, project directory *name*
  (not the full path), elapsed time, exit code.
- **Every credential in the config file is treated the same way** — the Discord
  webhook URL and the SMTP password alike. Mode 600 enforced, never logged. The
  webhook URL is a credential in itself, which makes the reflex of printing the
  request URL in an error log a leak; it is masked.

This is fixed as default behaviour rather than an option. A notifier that becomes
a leak is finished.

## 6.3 Getting configuration in

Moved to its own file — it is the largest part of the design.
→ **[05-onboarding.md](05-onboarding.md)**

## 6.4 Unresolved: Discord carries the immediacy of `blocked` alone

Cutting down to two channels means **the most valuable event in the design,
`blocked`, rides on Discord alone.** And Discord is a chat app — mobile push
arrives, but it is subject to per-channel mute settings, and the user is likely
already numb to notifications from dozens of channels. Mail cannot supply
immediacy, so it is not an alternative.

The only mitigation is guidance, which the README and `mailo init` have to state:

- **Create a dedicated channel** for mailo, not mixed in with conversations
- Set that channel's notifications to **"All Messages"**
- Turn on mobile push for that server and channel

None of this is enforceable by us; the user has to do it. **That the delivery of
`blocked` depends on user settings is the weakest point in the current design** —
leaving room to revisit a dedicated immediacy channel after v1.

# 02 — Gmail SMTP settings and sending limits

> Sources: <https://knowledge.workspace.google.com/admin/gmail/send-email-from-a-printer-scanner-or-app>
> · <https://support.google.com/mail/answer/22839>
> Checked: 2026-08-13 · the originals are authoritative

## 1. Server settings

| Item | Value |
|---|---|
| Server | **`smtp.gmail.com`** |
| SSL (implicit TLS) | **465** |
| TLS (STARTTLS) | **587** |
| Authentication | **the full email address** plus an **app password** |

Straight from the original: *"For SSL, enter 465"*, *"For TLS, enter 587"*.
Authentication needs *"your full Google Workspace email address (for example
your.name@example.com) and an app password."* The username is the **full address**,
not the part before the `@` — a common mistake.

Port 25 is also mentioned as a setting, but it is not for submission, so it is
ignored ([smtp/01-protocol.md](../smtp/01-protocol.md) §1).

→ mailo's default is **465 with implicit TLS**. The RFC 8314 recommendation and
Gmail's support agree.

## 2. Sending limits — the argument for the cooldown

| Account | Limit |
|---|---|
| Free Gmail | **500 messages a day**, or **500 recipients per message** |
| Workspace (this method) | **2,000 a day** |

Exceeding it raises *"You have reached a limit for sending mail"*, and per the
original, *"you should be able to send emails again within 1 to 24 hours."*

### 2.1 Why this matters for a notifier

Five hundred a day is plenty for normal notification use. The problem is the
**abnormal paths**:

- hooks firing more often than expected (the `Stop`-every-turn problem in
  DESIGN.md §3.1)
- a retry loop in a runner script notifying on every failure
- several machines sharing **one Gmail account** — precisely the situation the
  `machine` identifier in the config exists for

Any one of those reaches 500 in under a day. And exceeding the limit locks **the
user's own Gmail account**, not mailo, for up to 24 hours. A notifier cutting off
someone's email is an accident, which makes send suppression a **safety mechanism**
rather than a convenience.

The cooldown and duplicate suppression in DESIGN.md §3.2 went in because
notifications are noisy; this is the harder second reason.

### 2.2 Also needed: a daily cap

A cooldown (60 seconds per session and event) cannot stop **several separate
sessions each sending**. A per-channel daily cap goes alongside it:

```toml
[channels.smtp]
daily_limit = 200        # daily cap for this channel; 0 means unlimited
```

On hitting the cap, that channel is quietly skipped and it is logged. Other
channels carry on — Discord has no documented daily limit, so `blocked`
notifications still arrive when mail is blocked. The counter lives in the state
file from DESIGN.md §3.2, keyed by date.

> Why 200 and not 500: mailo should not consume **all** of an account's sending
> quota. Other things send from that account too — other scripts, actual email.

## 3. Example configuration

```toml
[channels.smtp]
host = "smtp.gmail.com"
port = 465
security = "tls"                    # implicit TLS
username = "you@gmail.com"          # the full address, not the part before the @
password = ""                       # or $MAILO_SMTP_PASSWORD (an app password on Gmail)
to = "you@gmail.com"
daily_limit = 200
```

For a non-Gmail server, only `host`, `port`, and `security` change.

The key is **`password`**, not `app_password`. `app_password` is too Gmail-coloured:
a user on a corporate SMTP server hits it and thinks "but I don't have an app
password." Gmail users are told to enter an app password **in the documentation and
in the error messages** instead.

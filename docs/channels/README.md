# docs/channels — notification channels

Reference notes for the channels mailo supports. **These two are the whole set.**

| Channel | Docs | Role | Transport |
|---|---|---|---|
| **discord** | [discord/](discord/) | immediacy — `blocked`, `failed` | HTTP POST (webhook + embed) |
| **mail (SMTP)** | [mail/](mail/) | record — `failed`, `done` | SMTP over implicit TLS |

Both are implemented with the standard library — `urllib.request` for Discord,
`smtplib` for mail. No external dependencies.

## The two channels do different jobs

**They complement rather than substitute.** This is not the same notification sent
twice; each does something the other cannot.

- **Discord** is immediacy. Events like `blocked` that you need to know about now.
  A phone push is the point.
- **SMTP** is the record. Events like `done` that can wait, plus searchable
  history. Mail is still there twelve hours later; it does not scroll away like a
  chat log.

`failed` goes to both, because it needs to be immediate *and* recorded — and
because **two independent paths mean one can die and the notification still
arrives.**

## `mailo init` treats Discord as the default path

Both channels require a manual issuance step by a human, so **there is no way to
finish onboarding with no input at all.** Of the two, the Discord webhook is the
lighter gate: copy one URL out of channel settings and you are done, with no
constraints by account type.

**Mail is not required.** Gmail app passwords **cannot be created at all** on
organisation (company or school) accounts, Advanced Protection accounts, or
accounts using security-key-only two-factor. Making mail mandatory leaves those
users with no way through the setup. This is a requirement, not a preference.
→ [mail/gmail/01-app-password.md](mail/gmail/01-app-password.md) §3

## The shared adapter contract

Collected from DESIGN.md §6.1, §7, and §7.1, from the perspective of channel
implementation.

1. **The interface is `send(cfg, event, title, body, meta) -> None`,** raising on
   failure. The only place exceptions are swallowed is the hook entry point
   (DESIGN.md §5.1).
2. **Channels are attempted independently.** One failing does not stop the others.
3. **Each adapter truncates on its own terms.** The common message carries the
   full original.

   | Channel | Limit | Unit |
   |---|---|---|
   | Discord embed `description` | 4,096 | characters |
   | Discord `content` (without an embed) | 2,000 | characters |
   | Discord message total | 6,000 | characters |
   | SMTP | no practical limit | — |

   Discord counts characters, so no byte arithmetic is needed.
   → [discord/02-embeds.md](discord/02-embeds.md) §2
4. **Exceptions split into retryable and not.**
   - Pointless to retry: authentication and configuration errors
     (`SMTPAuthenticationError`, HTTP 401/403/404). Give up immediately and log
     **how to fix it**.
   - Worth retrying: connection errors, timeouts, HTTP 429/5xx. One or two
     attempts with a short backoff. For 429, honour the `retry_after` Discord
     returns, but give up past 60 seconds — a `blocked` notification two minutes
     late is the same as one never sent.
   - **The retry ceiling is hard-coded, not exposed as a setting.**
5. **How an event looks is the adapter's decision.** A colour bar on Discord, a
   subject emoji in mail.
6. **Secrets can be overridden with `$MAILO_<CHANNEL>_<KEY>`,** the path for
   containers and CI where no config file is planted.

## Sending limits

| Channel | Daily limit | On exceeding it |
|---|---|---|
| Discord webhook | undocumented (per-second buckets only) | 429 — honour `retry_after` |
| Gmail (free) | **500** | **account blocked from sending for 1–24 hours** |
| Gmail (Workspace) | 2,000 | same |

**Gmail is the dangerous side.** Exceeding it locks **the user's real mail
account** for up to 24 hours, not mailo. A notification tool cutting off someone's
email is an accident worth engineering against, so on top of the cooldown there is
a **`daily_limit`** (200 by default for SMTP). Cooldown only covers one session and
cannot catch several separate sessions each sending.

Discord has no documented daily limit, so it gets no `daily_limit` — imitating a
constraint that does not exist teaches users to believe it is real.
→ [mail/gmail/02-smtp-settings.md](mail/gmail/02-smtp-settings.md) §2,
  [discord/03-rate-limits.md](discord/03-rate-limits.md) §3

## Known weakness

The immediacy of `blocked` rests on **Discord alone.** Discord is a chat app, so
mobile push is subject to per-channel mute settings, and mail cannot supply
immediacy as an alternative.

The only mitigation is guidance — make a dedicated channel for mailo, set its
notifications to "All Messages", and keep mobile push on. We cannot enforce any of
it; the user has to. Recorded in DESIGN.md §6.4.

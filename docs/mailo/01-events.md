> Part of the [mailo design notes](README.md).

# 3. The event model

Claude Code hooks and wrapped processes are normalised into **four meaningful
events**. Those four are all a user has to learn, and routing works in the same
units.

| Event | Meaning | Source |
|---|---|---|
| `blocked` | Stopped, waiting for human input | `Notification` (`permission_prompt`, `idle_prompt`, `agent_needs_input`) |
| `failed` | Terminated abnormally | `StopFailure` (rate limit, billing, …), a non-zero exit from `mailo run` |
| `done` | Finished normally | `Notification` (`agent_completed`), `SessionEnd`, exit 0 from `mailo run` |
| `custom` | Called directly by an agent or script | `mailo send` |

## 3.1 The central judgement: do not use the `Stop` hook

`Stop` fires **every time Claude finishes a response** — that is, every turn. Hang
a notification on it and you get one per exchange, and you will have muted the
tool within a day. **The only failure mode of a notifier is being noisy.**

Use `Notification`'s `agent_completed` and `idle_prompt` instead. Claude Code
fires those having already decided the user seems to be away, so **we do not
reinvent away-detection.** This is the most important judgement in v1.

`Stop` stays available as opt-in only (`triggers.stop_min_duration_sec = 300` —
turns longer than five minutes). **The default is off**, and with the key absent
the `Stop` hook is not registered at all.

## 3.2 Noise suppression

- **Cooldown**: the same (session_id, event) pair is not re-sent within 60s by default.
- **Per-channel daily cap**: `daily_limit` (200 by default for SMTP). Cooldown
  only covers one session, so it cannot stop **several separate sessions each
  sending**. This is a **safety mechanism, not a convenience** — free Gmail
  blocks sending on an account for **1 to 24 hours** past 500 messages a day, and
  a notifier that cuts off the user's real mail is an accident worth engineering
  against. Discord has no documented daily cap, so it has none.
  → [../channels/README.md](../channels/README.md), [../channels/mail/gmail/02-smtp-settings.md](../channels/mail/gmail/02-smtp-settings.md) §2
- **State file**: `$XDG_STATE_HOME/mailo/state.json` — last send time, per-day
  per-channel counters.
- **Delayed `blocked`**: if the approval prompt appears and the user presses the
  button three seconds later, the notification is pointless. `blocked_delay_sec`
  would send only when the session is still blocked after that long.
  → **Unresolved**: hook input carries no "resolved" signal. See Q3.

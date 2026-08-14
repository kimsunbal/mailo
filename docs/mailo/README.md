# mailo — design notes (v1)

> Status: **draft for review.** Not final. Open questions are in
> [07-open-questions.md](07-open-questions.md).

These are mailo's own design notes, as opposed to [../channels/](../channels/) and
[../pypi/](../pypi/), which summarise other people's documentation.

Section numbers are the ones the codebase cites (`DESIGN.md §5.1` and so on), so
they are kept unchanged across the split. [../../DESIGN.md](../../DESIGN.md) maps
each number to its file.

| File | Sections | Contents |
|---|---|---|
| this file | 1, 2, 9 | the problem, what mailo is, v1 scope |
| [01-events.md](01-events.md) | 3 | the four events, why the `Stop` hook is avoided, noise suppression |
| [02-cli.md](02-cli.md) | 4 | the command surface |
| [03-hooks.md](03-hooks.md) | 5 | settings.json wiring, the hook contract, what hook input lacks |
| [04-configuration.md](04-configuration.md) | 6, 6.1, 6.2, 6.4 | the config file, TOML choice, privacy, the Discord weakness |
| [05-onboarding.md](05-onboarding.md) | 6.3 | `init` and `config set` — discovery, one paste, verification, transfer |
| [06-channels.md](06-channels.md) | 7, 8 | channel implementation, the adapter contract, message format |
| [07-open-questions.md](07-open-questions.md) | 10 | what is settled and what is not |

**Start with [01-events.md](01-events.md)** if you want the single most important
judgement in the design; **[05-onboarding.md](05-onboarding.md)** is the largest
part and the one most exposed to users.

## 1. The problem

AI coding agents and long jobs run **while nobody is at the desk.** State changes
that a person needs to know about happen in that window, and there is no way to
find out.

Ordered by what it costs to miss them:

1. **blocked** — the agent has stopped, waiting for permission or input. Thirty
   seconds of attention would clear it; thirty minutes are lost instead. The work
   is not finished, it is *idling*, which makes the loss pure waste.
2. **failed** — a three-hour training run died of OOM and you find out in the
   morning; a session hit a rate limit and you notice hours later.
3. **done** — you just cannot queue up the next thing. Waiting costs nothing.

Why existing tools do not close the gap: `mail` and `apprise` solve **transport**,
but **when to send** is left for you to wire up. Case 1 in particular cannot be
covered at all without a layer that catches events from outside — the agent is
frozen, so it cannot announce itself.

## 2. What this is

**A single binary that pushes agent session state changes to a phone.**

- No daemon, no server, no dashboard
- One config file and one executable
- Zero dependencies (Python standard library only)

> **Starting point**: a personal script, `mailer.py` (74 lines, one SMTP channel,
> flat `KEY=VALUE` config). Wherever this document and `docs/` say "the current
> `mailer.py`", that is what they mean. What carries over is the SMTP sending
> logic and the config-file permission check; the rest — the event model, hooks,
> routing — is new.

### Out of scope

The line that keeps this from turning into an observability platform.

- **Receiving** webhooks, queues, a state server, a web UI
- Multi-user setups, team management, permissions
- Log collection, aggregation, search
- Two-way control (reply to a notification, drive the agent) — revisit after v2,
  explicitly excluded from v1

## 9. v1 scope

**Included**
- **Two channels: `discord` and `smtp`**
- `send` / `run` / `hook` / `install-hooks` / `uninstall-hooks` / `init` / `test`
- `config set|get|list|unset|edit|export` — per-key setting and machine transfer
- **Onboarding**: discover existing config → one order-free paste → verify before
  saving → one-line transfer (§6.3)
- Four events, routing, cooldown, SMTP daily cap
- Context enrichment via the `SessionStart` cache
- PyPI distribution as `mailo-cli` (`uv tool install mailo-cli`), Python ≥ 3.11

**Excluded (v2 and later)**
- **More channels** — the adapter interface stays extensible, but the count does
  not grow in v1
- Long-turn detection via the `Stop` hook (the setting exists, off by default)
- Two-way control (reply to a notification, drive the session)
- Desktop notifications (possible with `terminalSequence` OSC 9 — cheap enough
  that v1 inclusion is worth revisiting)
- Tools other than Claude Code (Cursor, aider, …)

Two channels makes v1 noticeably thinner. The price is §6.4 — the deliverability
of `blocked` depends on the user's Discord notification settings.

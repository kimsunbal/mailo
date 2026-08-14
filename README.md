# mailo

**Tells you when your AI agent gets stuck, dies, or finishes.**

Agents and long jobs run while nobody is watching. Things happen that you need to
know about and no way to find out — and the one case that matters most, **an agent
frozen waiting for approval**, cannot announce itself. mailo hooks into Claude
Code, catches that moment, and pushes it to your phone.

- No daemon, no server. One executable and one config file
- **Zero dependencies** (standard library only), Python ≥ 3.11
- Two channels: **Discord webhook** (immediacy) and **SMTP mail** (a record)

## Status

> **v0.1.0 — it works. Not published to PyPI yet.**
> The hook input fields follow the reference documentation and have not been
> measured against a live session yet ([docs/mailo/07-open-questions.md](docs/mailo/07-open-questions.md) Q5).

```bash
uv tool install mailo-cli    # or: pipx install mailo-cli
mailo init
```

The distribution is called **`mailo-cli`** because PyPI rejects `mailo` as too
similar to an existing project. Everything else — the command, the module, the
config paths — is `mailo`.

| | |
|---|---|
| Design | [docs/mailo/](docs/mailo/) — event model, hook wiring, config, onboarding, channels |
| Reference | [docs/channels/](docs/channels/), [docs/pypi/](docs/pypi/) — from the official docs |
| Open questions | [docs/mailo/07-open-questions.md](docs/mailo/07-open-questions.md) — delayed `blocked`, `SessionEnd`, hook measurement |
| Tests | `python -m unittest discover -s tests` (73 tests, no dependencies) |

## CLI

```
mailo init                          create the config (~/.config/mailo/config.toml)
mailo config set smtp.username ...  set one key, the way git config does
mailo config list / get / unset / edit
mailo config export                 move the config to another machine in one line
mailo test [-c CHANNEL]             verify the config and send a test
mailo send -e EVENT -s SUBJECT [-b BODY]
mailo run [--name NAME] -- CMD...   wrap a command — exit code, duration, log tail
mailo install-hooks / uninstall-hooks
```

There are three ways in. The first time, `init` takes **everything you collected in
one paste, in any order**. After that `config set` changes one key at a time. When
you add a machine, `config export` moves the whole thing in one line. Secrets are
never accepted as command-line arguments. ([docs/mailo/05-onboarding.md](docs/mailo/05-onboarding.md))

## Four events

| Event | When | Cost of missing it |
|---|---|---|
| `blocked` | Stopped, waiting for approval or input | **The highest.** Thirty seconds of attention would clear it; thirty minutes are lost instead |
| `failed` | Died (OOM, rate limit, non-zero exit) | High. You find out in the morning that a three-hour run died |
| `done` | Finished normally | Low. You just cannot queue the next thing |
| `custom` | Called directly from a script | — |

Routing is per event. `blocked` to Discord, `done` to mail, `failed` to both —
two independent paths, so one can die and the notification still arrives.

## Design principles

1. **The only failure mode of a notifier is being noisy.** That is why the `Stop`
   hook, which fires every turn, is not used, and why there is a cooldown and a
   daily cap. ([docs/mailo/01-events.md](docs/mailo/01-events.md) §3.1)
2. **The default leaks nothing.** Bodies carry metadata only — no conversation
   text, no full paths. `include_message_text` defaults to `false`. ([docs/mailo/04-configuration.md](docs/mailo/04-configuration.md) §6.2)
3. **The hook path never disturbs the session.** Always exit 0, always
   `async: true`. ([docs/mailo/03-hooks.md](docs/mailo/03-hooks.md) §5.1)
4. **No plaintext SMTP, and no way to disable TLS verification.** Not even as an
   option. ([docs/mailo/06-channels.md](docs/mailo/06-channels.md) §7.1)

## Known weakness

The immediacy of `blocked` rests on **Discord alone**. Mail cannot deliver
immediacy, so it is not an alternative. Discord is a chat app, which means push
delivery depends on the user's per-channel notification settings — something we
cannot enforce. The only mitigation is guidance: make a dedicated channel for
mailo, set it to "All Messages", and keep mobile push on. ([docs/mailo/04-configuration.md](docs/mailo/04-configuration.md) §6.4)

## Layout

```
src/mailo/
  cli.py         command parsing and implementations
  schema.py      the config key schema — one table shared by init, config set, and load
  config.py      reading and writing, mode 600 enforcement, machine-to-machine transfer
  tomlwrite.py   in-place TOML editing (stdlib has no writer, and comments must survive)
  onboard.py     discovery, order-free paste parsing, domain presets
  hooks.py       hook entry point (always exit 0) and settings.json merging
  notify.py      routing, cooldown, daily cap, retry classification
  runner.py      mailo run — command wrapping
  channels/      discord (urllib) and smtp (smtplib)
```

## Licence

[MIT](LICENSE).

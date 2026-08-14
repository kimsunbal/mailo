# mailo — design notes

The design notes live in **[docs/mailo/](docs/mailo/)**. This file is the map.

It was one document of ~750 lines, more than half of it section 6. Splitting it
made the parts findable; keeping the numbering made the split free, because the
codebase cites these sections by number (`DESIGN.md §5.1`, `§6.3.7`, and so on) and
none of those citations had to change.

| Section | Where it lives |
|---|---|
| 1. The problem | [docs/mailo/README.md](docs/mailo/README.md) |
| 2. What this is | [docs/mailo/README.md](docs/mailo/README.md) |
| 3. The event model | [docs/mailo/01-events.md](docs/mailo/01-events.md) |
| 3.1 Do not use the `Stop` hook | [docs/mailo/01-events.md](docs/mailo/01-events.md) |
| 3.2 Noise suppression | [docs/mailo/01-events.md](docs/mailo/01-events.md) |
| 4. CLI surface | [docs/mailo/02-cli.md](docs/mailo/02-cli.md) |
| 5. Hook wiring | [docs/mailo/03-hooks.md](docs/mailo/03-hooks.md) |
| 5.1 The hook contract | [docs/mailo/03-hooks.md](docs/mailo/03-hooks.md) |
| 5.2 What hook input lacks | [docs/mailo/03-hooks.md](docs/mailo/03-hooks.md) |
| 6. Configuration | [docs/mailo/04-configuration.md](docs/mailo/04-configuration.md) |
| 6.1 TOML, Python ≥ 3.11 | [docs/mailo/04-configuration.md](docs/mailo/04-configuration.md) |
| 6.2 Privacy | [docs/mailo/04-configuration.md](docs/mailo/04-configuration.md) |
| 6.3 Getting configuration in | [docs/mailo/05-onboarding.md](docs/mailo/05-onboarding.md) |
| 6.4 Discord carries `blocked` alone | [docs/mailo/04-configuration.md](docs/mailo/04-configuration.md) |
| 7. Channel implementation | [docs/mailo/06-channels.md](docs/mailo/06-channels.md) |
| 7.1 The adapter contract | [docs/mailo/06-channels.md](docs/mailo/06-channels.md) |
| 8. Message format | [docs/mailo/06-channels.md](docs/mailo/06-channels.md) |
| 9. v1 scope | [docs/mailo/README.md](docs/mailo/README.md) |
| 10. Open questions | [docs/mailo/07-open-questions.md](docs/mailo/07-open-questions.md) |

Adding a section means adding a row here. A citation that cannot be resolved from
this table is a bug in the table.

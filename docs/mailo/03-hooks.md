> Part of the [mailo design notes](README.md).

# 5. Hook wiring

`mailo install-hooks` merges into the `hooks` key of `~/.claude/settings.json`
(`.claude/settings.json` with `--project`). Existing hooks are preserved; only
mailo's entries are added or refreshed.

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "permission_prompt|idle_prompt|agent_needs_input|agent_completed",
        "hooks": [
          { "type": "command", "command": "mailo", "args": ["hook"],
            "async": true, "timeout": 30 }
        ]
      }
    ],
    "StopFailure": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "mailo", "args": ["hook"],
            "async": true, "timeout": 30 }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "mailo", "args": ["hook"],
            "async": true, "timeout": 30 }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "mailo", "args": ["hook"],
            "async": true, "timeout": 30 }
        ]
      }
    ]
  }
}
```

All four entries are **the same command**. `mailo hook` branches on
`hook_event_name` from the stdin JSON (section 4).

`SessionStart` **sends nothing.** It exists only to cache `session_id -> cwd` in
the state file (§5.2). It is easy to overlook that one hook maps to no event at
all, so the branch table in the `hook` entry point carries an explicit "sends
nothing" path. Even when `install-hooks --events` narrows the set,
**`SessionStart` is always registered** — without it, `blocked` notifications
lose the project name.

## 5.1 Non-negotiables of the hook contract

- **`async: true`** — notification delivery must never hold the session. A network
  POST can take seconds, and `SessionEnd` shares a **1.5 second budget** across
  all hooks (an explicit `timeout` raises it to at most 60s). That is why
  `timeout` is set explicitly too.
- **Always exit 0** — every failure on the hook path is swallowed. Exit 2 is the
  code that blocks a session, so a notifier must never emit it. Errors go to
  `$XDG_STATE_HOME/mailo/mailo.log` and nowhere else.
- **Exec form** (`command` plus `args`) — no shell tokenisation, so paths
  containing spaces are safe.

## 5.2 What hook input does not give you

The stdin JSON for a `Notification` hook has `session_id`, `hook_event_name`,
`notification_type`, and `notification_text` — **and that is all.** No `cwd`, no
`transcript_path`.

> This follows the **hook reference documentation** and has not been measured.
> Confirm which fields exist with the `tee` capture in Q5 before relying on them —
> code that reads a field which is not there quietly passes `None` along.

So a `blocked` notification **cannot get the project path from hook input.**
The options were:

1. Use the hook process's own `os.getcwd()`, assuming it inherits the session's
   cwd — **needs verification.**
2. Cache `session_id -> cwd` from the `SessionStart` hook (which does have `cwd`)
   in the state file, and look it up on `Notification`.

**Option 2 was chosen.** Option 1 rests on an assumption; option 2 writes once at
session start and can cache `transcript_path` and `model` at the same time. The
cost is one extra hook registration.

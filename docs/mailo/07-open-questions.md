> Part of the [mailo design notes](README.md).

# 10. Open questions

## Settled

- **Name: `mailo`** (2026-08-13). Confirmed unregistered on PyPI. To avoid being
  mistaken for a mail-only tool, the first line of the README and the package
  `description` lead with notification — *"Notify yourself when your AI agent gets
  stuck, fails, or finishes."* Mail is introduced as one of the channels.
- **Channels are `discord` plus `smtp`** (2026-08-13). Other candidates were
  dropped; the cost is recorded in §6.4.
- **Minimum Python 3.11** (2026-08-13), so the config can be TOML via `tomllib`.
  The cost — giving up the default Python on Ubuntu 22.04 — is accepted. → §6.1
- **Channel renamed `email` → `smtp`, Gmail dependence removed** (2026-08-13).
  Gmail is an example, not an assumption. Since some account types cannot issue
  app passwords, **the SMTP channel is optional** and `mailo init` treats Discord
  as the default path. → §6.3
- **Discord's webhook object has no channel *name*** (measured 2026-08-14). A
  `GET /webhooks/{id}/{token}` returns the webhook's own `name` and a
  `channel_id`, so the confirmation line is phrased around the webhook name:
  `webhook "Mailo" (channel 1537...)`. This closes one item that was under Q5.

## Open

**Q3. Detecting resolution for delayed `blocked`.** Implementing "notify if
blocked for more than 90 seconds" requires knowing when it is no longer blocked,
and hook input carries no such signal. Candidates:
(a) treat `PostToolUse` / `UserPromptSubmit` as the resolution signal and update
the state file → two more hooks, false positives possible;
(b) send immediately and suppress with the cooldown alone → simple, but a
three-second approval still gets a notification;
(c) (b) for v1, (a) for v2.
→ **(c) recommended.** Simplicity first, then judge from the real noise level.
v1 implements (b): `blocked_delay_sec` defaults to 0, and a non-zero value waits
for a *second* observation rather than trying to detect resolution.

**Q4. Should `SessionEnd` count as `done`?** Most session endings are the user's
own doing (`clear`, `logout`, `prompt_input_exit`), which means they are already
at the keyboard, so the notification is probably pointless. Narrowing the matcher
to `other`, or dropping it entirely, may be better.

**Q5. Things to measure.** Do not settle these from documented specs alone:
- How often the `Notification` hook actually fires, and what `notification_text`
  really contains
- What `async: true` hooks actually do — do they really not hold the session
- Conflicts with existing settings.json structures that `install-hooks` has to merge
- **§6.3.4**: host/port for naver and kakao, and whether they need app passwords.
  Unverified presets do not go in.
- **§6.3.2**: whether a Gmail app password is always 16 *lowercase letters*. If the
  character set varies, the classification regex has to widen, and anything
  ambiguous should be asked about rather than guessed.
→ Attaching a `tee` to the hooks and collecting real input for a few days before
  finishing v1 is the reliable way. The SMTP items can be checked independently.

> Part of the [mailo design notes](README.md).

# 6.3 Getting configuration in — `mailo init` and `mailo config`

Three ways in. **All three share one key schema** (6.3.3).

| Path | When |
|---|---|
| `mailo init` | First-time setup: discover, one paste, verify (6.3.1–6.3.2) |
| `mailo config set KEY VALUE` | Change or add one value, the way `git config` feels (6.3.3) |
| `mailo init --from -` | Transfer from another machine, one line (6.3.7) |

**There is no automatic issuance path.** The doors that are closed:

| Candidate | Why it does not work |
|---|---|
| Discord OAuth2 `webhook.incoming` | The flow really does exist — pick a server and channel, get a webhook URL back — but the token exchange needs a **client secret**, and a public PyPI package cannot carry one |
| Gmail OAuth2 (XOAUTH2) | `https://mail.google.com/` is a restricted scope: a registered app that has passed Google's security assessment, and again a secret |
| RFC 6186 SRV autodiscovery | The standard library has no SRV lookup (`socket` does A/AAAA only); it would break zero dependencies |

So the goal is restated. **Not "remove the paste" but "make one paste impossible
to get wrong, and remove even that from the second machine onwards."**

## 6.3.1 Look first, ask second

The first thing `init` does is not ask a question. It looks for a configuration
that already exists.

- `~/tools/mailer/config` — the flat `KEY=VALUE` config of the personal script
  this grew out of (`USERNAME`, `APP_PASSWORD`, `DEFAULT_TO`, `SUBJECT_PREFIX`,
  `SMTP_HOST`, `SMTP_PORT`). All of it maps one-to-one onto mailo keys
  (`SUBJECT_PREFIX` becomes `machine` once the brackets come off).
- `$MAILO_*` environment variables that are already set.

If something turns up, show it and ask whether to import it; an existing user then
only has to add a Discord webhook. If not, fall through to 6.3.2 — **finding
nothing costs nothing, so this is pure upside.**

## 6.3.2 Input is one paste, in any order

No question-and-answer flow. That format assumes **the user is in a position to
follow mailo's order** — but when it asks for the webhook URL they are on the
Gmail tab, and when it asks for the app password they have not created one yet.
Over SSH each round trip is latency on top.

Take whatever they collected **all at once, in any order and any format.**

```
$ mailo init
Paste your Discord webhook URL, email address, app password in any order:

https://discord.com/api/webhooks/1399.../aBcD-xY
you@gmail.com
abcd efgh ijkl mnop
^D

Recognised:
  discord.webhook_url   .../webhooks/1399582.../***
  smtp.username         you@gmail.com
  smtp.to               you@gmail.com   (same as username; changeable)
  smtp.host / port      smtp.gmail.com:465  (derived from the domain)
  smtp.password         **************** (16 chars)
Is this right? [Y/n]
```

Every value is **distinguishable by shape alone.** There is no ambiguity, which is
what makes order-free classification safe.

| Pattern | Maps to |
|---|---|
| `discord(?:app)?\.com/api/webhooks/(\d+)/([\w-]+)` | `channels.discord.webhook_url` |
| An email address | `smtp.username`, `smtp.to` (same value by default) |
| Sixteen lowercase letters, spaces allowed | `smtp.password` (spaces stripped) |
| An `smtp.*` hostname, `:465` / `:587` | `smtp.host`, `port`, `security` |

Normalisation is mandatory — every item below is something that actually breaks.

- **A Gmail app password is displayed as `abcd efgh ijkl mnop`.** Users paste the
  spaces along with it.
- Strip surrounding whitespace and quotes; copying from a shell brings them along.
- A `discord.com/channels/...` URL with no `/api/webhooks/` in it — **confusing the
  channel URL with the webhook URL is the single most common mistake.** Say so
  ("you need the URL from Channel Settings -> Integrations -> Webhooks") and ask
  again.

**Reading the result back is what makes this approach worth it** — a wrong value
catches the user's eye before it reaches the file. On the way back the password
shows only its length and the webhook URL is masked as `.../webhooks/{id}/***`
(§6.2). The pasted text itself is **never written to the log under any
circumstances.**

## 6.3.3 Per-key setting — `mailo config`

With only `init`, **changing one value means running the whole flow again or
opening an editor.** So there is a path for setting and clearing individual keys,
the way `git config user.email` works.

```
mailo config set machine box-a
mailo config set smtp.username you@gmail.com
mailo config set smtp.password                    # value omitted -> prompt, no echo
mailo config set discord.webhook_url --stdin      # read from a pipe
mailo config set routing.blocked discord,smtp     # commas -> array
mailo config get smtp.username
mailo config list                                 # everything, secrets masked
mailo config unset triggers.stop_min_duration_sec
mailo config edit                                 # $EDITOR — last resort
```

**Keys are short.** The real TOML path is `channels.smtp.username`, but the CLI
takes an `smtp.` or `discord.` prefix. Channel names never collide with the
top-level keys (`machine`, `routing`, `triggers`), so nothing is ambiguous and it
ends up as terse as `git config`.

| Short key | Type | Notes |
|---|---|---|
| `machine` | str | falls back to `socket.gethostname()` |
| `smtp.username`, `smtp.to` | str | email format checked |
| `smtp.password` | **secret** | |
| `smtp.host` | str | |
| `smtp.port` | int | |
| `smtp.security` | enum | `tls` \| `starttls` — anything else rejected (§7.1) |
| `smtp.daily_limit` | int | 0 = unlimited |
| `discord.webhook_url` | **secret** | `/api/webhooks/{id}/{token}` format checked |
| `routing.{blocked,failed,done,custom}` | list[str] | known channel names only |
| `triggers.cooldown_sec`, `blocked_delay_sec`, `stop_min_duration_sec` | int | |
| `triggers.include_message_text` | bool | |

Four rules are fixed.

1. **Secrets are not accepted as arguments.** `mailo config set smtp.password
   abc123` is **rejected** with instructions: omit the value to be prompted, or
   pipe it in with `--stdin`. This is the one place mailo departs from
   `git config`, and the reason is `ps` exposure (§6.3.6). The automation path is
   the `$MAILO_<CHANNEL>_<KEY>` environment variable.
2. **Unknown keys are rejected.** `git config` allows arbitrary keys, but here a
   typo becomes **silent inaction** — accept `smtp.usernme` and nobody finds out
   until a send fails. Reject it and offer the nearest match
   (`difflib.get_close_matches`).
3. **Types are enforced.** `cooldown_sec = "60s"` would otherwise explode at load
   time. The schema table above **feeds `init`, `config set`, and load-time
   validation alike** — one copy of it in the code. `init` amounts to calling
   `config set` several times.
4. **Anything checkable is checked immediately.** Setting `discord.webhook_url`
   runs the lookup from 6.3.5. `--no-verify` skips it.

### Writing it — `tomllib` is read-only

**The standard library has no TOML *writer*.** `tomllib` only parses. So
`config set` cannot serialise; it has to be **line-level editing in place**:

- Find the `[section]`, replace the value on its `key =` line. If the key is
  missing, append to the end of that section; if the section is missing too,
  append the whole section.
- **Comments and ordering are preserved.** Re-serialising the file would have the
  first `config set` erase the very thing §6.1 set out to protect — that this is a
  file humans edit by hand, where comments matter.
- Write atomically: temp file, **`chmod 600` first**, then `os.replace()`.
- Afterwards, **parse it again with `tomllib`** and roll back on failure. Line
  editing can go wrong on quoting and escapes, so the round trip is the safety net.

## 6.3.4 Domain presets — five SMTP fields down to two

SMTP has a lot of fields: host, port, security, username, password, to. Deriving
them from the email address reduces it to **an address and a password**.

| Domain | host | port |
|---|---|---|
| `gmail.com` | `smtp.gmail.com` | 465 |
| `naver.com` | `smtp.naver.com` | 465 |
| `kakao.com`, `daum.net` | `smtp.kakao.com` | 465 |
| anything else | ask | ask |

**Outlook/Hotmail is left out.** Microsoft is retiring SMTP basic auth for
personal accounts, so whether app passwords work is not certain. An unverified
preset produces the worst possible failure — settings that look correct but will
not authenticate — and the user starts doubting their own password. Presets should
contain only what has been confirmed; asking is better than guessing.

## 6.3.5 Verify before saving, and go back on failure

The split where `init` writes the file and `test` checks it goes away. **The
moment a wrong value settles into the file the user has to open an editor, and
that is where onboarding fails.**

- **Discord**: `GET /webhooks/{id}/{token}` reads the webhook object back. It
  needs only the token, no auth header, and **posts nothing to the channel.**
  Echoing the webhook's name back tells the user instantly if they pasted the
  wrong one. Then ask, and send one test message.
- **SMTP**: `SMTP_SSL` connect, `login()`, `quit()`. Authentication is confirmed
  without sending mail. Ask about a test message afterwards.

Errors are **translated into diagnoses.** There are few failure points and all of
them are predictable, which makes this the highest-return work in the whole flow.

```
SMTP authentication failed (smtp.gmail.com)
  Gmail rejects account passwords. You need an app password.
  Create one at https://myaccount.google.com/apppasswords
  Organisation, school, and Advanced Protection accounts cannot create them at all.
  In that case leave the mail channel empty and use Discord only — mail is optional.
```

The last line is the point. **Tell users who cannot get a credential about the way
out, on the screen where they got stuck.** A design that says "mail is optional"
is worthless if that fact never reaches the moment it matters.

## 6.3.6 How secrets get in

- Interactive input goes through `getpass.getpass()` — no echo, nothing in shell
  history.
- **There is no path that takes a password as a CLI flag.** It would show up in `ps`.
- For non-interactive use, the `$MAILO_<CHANNEL>_<KEY>` environment variable is
  enough on its own (§6.1).
- **No OS keyring.** `keyring` is a dependency and `secret-tool` / `security` is
  platform branching. Mode 600 plus environment variables is the right level for a
  tool this size.

## 6.3.7 One line from the second machine onwards

Credentials are **needed once per account but treated as once per machine.** Three
machines means going through issuance three times — and since running agents on a
remote box is the primary use case, this is the real bottleneck.

```
laptop$  mailo config export          # MAILO1:eyJtYWNoaW5lIjoi...  one line
box$     mailo init --from -          # read from stdin
```

`machine` defaults to `socket.gethostname()` and is excluded from the export, so
**the same line pasted onto N machines still distinguishes where notifications
came from.**

Two rules are fixed.

- **`--from` reads stdin only, never argv** — `ps` exposure again.
- **The string is base64, which is not encryption.** The first line of `export`
  output warns that it is plaintext credentials and must not be pasted into chat
  or an issue. Use `--no-secrets` to share only routing and triggers.

## 6.3.8 Mail is not a required gate

**Mail must not be a mandatory step in onboarding.** Gmail app passwords **cannot
be created at all** on organisation (company or school) accounts, Advanced
Protection accounts, or accounts using security-key-only two-factor. Making mail
mandatory leaves those users with no way through. This is a requirement, not a
preference.
→ [../channels/mail/gmail/01-app-password.md](../channels/mail/gmail/01-app-password.md) §3

The Discord webhook is the lighter gate — copy one URL out of channel settings and
you are done, with no constraints by account type. If the paste contains only a
webhook URL, **setup completes without mail.**

When mail is configured, **a dedicated account for mailo is recommended.** Three
problems disappear at once: organisation accounts that cannot issue app passwords,
the *real* mailbox being locked for up to 24 hours when the 500/day cap is
exceeded ([../channels/README.md](../channels/README.md), sending limits), and the blast radius of a
leaked credential. It is send-only, takes two minutes to create, and the recipient
address can stay whatever it already was.

## 6.3.9 Decided against

**A local web wizard** (`mailo init --web` — `http.server` plus `webbrowser` to put
up a form). It has real appeal, since the credentials are already in the browser,
and it is possible with the standard library alone (it is the shape `gh auth
login` uses). But it is **useless on a remote headless box**, and the single paste
in 6.3.2 solves the same problem with far less code. Deferred to v2.

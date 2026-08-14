# docs/channels/mail/gmail — Gmail vendor notes

> Checked: 2026-08-13 · the originals are authoritative

Gmail is **one of the servers** mailo's SMTP channel can talk to. It is neither the
default nor an assumption, which is why this directory is separate from `smtp/`.

That said, many real users will be on Gmail, so its setup and its **constraints**
have to be understood precisely.

| File | Contents |
|---|---|
| [01-app-password.md](01-app-password.md) | App passwords — the requirements, and **when they cannot be created** |
| [02-smtp-settings.md](02-smtp-settings.md) | Server and port settings, sending limits |

## Primary sources

| Source | URL |
|---|---|
| Sign in with app passwords | <https://support.google.com/accounts/answer/185833> |
| Send email from a printer, scanner, or app | <https://knowledge.workspace.google.com/admin/gmail/send-email-from-a-printer-scanner-or-app> |
| Gmail sending limits | <https://support.google.com/mail/answer/22839> |

## The two things that matter

**1. Some accounts cannot create app passwords.** Organisation (company, school)
accounts, Advanced Protection accounts, and accounts using security-key-only
two-factor. → **The SMTP channel must be optional.**

**2. There is a sending limit.** 500 a day on free Gmail; exceeding it blocks
sending for 1–24 hours. → **Without a cooldown, a notifier can lock the user out of
their own mail account.**

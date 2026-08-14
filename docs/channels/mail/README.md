# docs/channels/mail — sending mail

Reference notes for implementing mailo's `smtp` channel.

> **What these are**: summaries of the official documentation. The originals are
> authoritative and these are copies, so where they disagree, follow the original.
> Each file carries its source URL and the date it was checked.
> Checked: **2026-08-13**

## Layout

The notes are split into a **standards and implementation** layer and a **vendor**
layer. That split is itself a design judgement — mailo is a general SMTP client,
and Gmail is one case running on top of it.

| Directory | Layer | Contents |
|---|---|---|
| [smtp/](smtp/) | standards + implementation | RFC 5321, 8314, 6409; Python `smtplib` and `email` |
| [gmail/](gmail/) | vendor | app password constraints, `smtp.gmail.com` settings, sending limits |

## What this means for mailo

### 1. The channel is called `smtp` — Gmail dependence removed (settled)

This channel is a **general SMTP client**; Gmail is an example in the config, not
an assumption. The name `[channels.email]` and the Gmail defaults were inherited
from `mailer.py`, and that premise cannot survive a public release. The reason is
item 3.

### 2. Port 465 with implicit TLS stays — it is the standard recommendation

RFC 8314 **recommends implicit TLS (465) over STARTTLS (587)**. The current
`mailer.py` already does exactly that with
`SMTP_SSL(host, 465, context=ssl.create_default_context())`, so **there is no
reason to change it.** Some internal servers only open 587, so STARTTLS stays
available as a configured alternative.
→ [smtp/01-protocol.md](smtp/01-protocol.md)

### 3. The SMTP channel has to be **optional** — a requirement, not a preference

Per Google's own documentation, some accounts **cannot create app passwords at
all**: organisation accounts (company, school), Advanced Protection accounts, and
accounts whose two-factor is security-key-only. Plenty of developers use a
Workspace account.

→ `mailo init` treats **Discord as the default path**, and SMTP must be skippable.
Making mail a mandatory gate in onboarding means **some users cannot get through at
all.** → [gmail/01-app-password.md](gmail/01-app-password.md)

### 4. Sending limits are the second argument for the cooldown design

Free Gmail allows **500 messages a day**, and exceeding it **blocks sending for
1–24 hours**. The cooldown and duplicate suppression in DESIGN.md §3.2 went in
because notifications are noisy; now there is a harder reason as well —
**a runaway hook locks the account.** A notifier that locks the user out of their
own email is an accident worth engineering against.
→ [gmail/02-smtp-settings.md](gmail/02-smtp-settings.md)

### 5. Exceptions split into retryable and not

`smtplib`'s exception hierarchy is well separated and can be used as is.
Authentication failures are pointless to retry (a configuration problem);
disconnections and timeouts are worth retrying.
→ [smtp/02-python-smtplib.md](smtp/02-python-smtplib.md)

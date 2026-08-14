# 02 — Python `smtplib` and `email`

> Sources: <https://docs.python.org/3/library/smtplib.html>
> · <https://docs.python.org/3/library/email.message.html>
> Checked: 2026-08-13 · the originals are authoritative

## 1. Constructors

```python
smtplib.SMTP(host='', port=0, local_hostname=None, [timeout,] source_address=None)

smtplib.SMTP_SSL(host='', port=0, local_hostname=None, *,
                 [timeout,] context=None, source_address=None)
```

| Parameter | Description |
|---|---|
| `host` | server hostname |
| `port` | **`0` means the default** — 25 for `SMTP`, **465** for `SMTP_SSL` |
| `timeout` | seconds for blocking operations; raises `TimeoutError`. **0 is not allowed** (`ValueError` since 3.9) |
| `context` | an `ssl.SSLContext`; `SMTP_SSL` only |
| `local_hostname` | FQDN for HELO/EHLO; defaults to `socket.getfqdn()` |

`SMTP_SSL` is implicit TLS (465); `SMTP` plus `.starttls()` is STARTTLS (587).

> **The `keyfile` and `certfile` parameters were removed in 3.12.** They still
> appear in old examples. Use an `ssl.SSLContext` instead.

## 2. The TLS context

```python
context = ssl.create_default_context()
```

`create_default_context()` turns on certificate verification
(`verify_mode = CERT_REQUIRED`) and hostname checking (`check_hostname = True`)
**by default.** `SMTP_SSL` supports hostname checking and SNI.

Examples that disable verification with `check_hostname = False` or
`verify_mode = CERT_NONE` are common on the internet, and they leave the connection
**wide open to a man in the middle.** This connection carries credentials, so that
is never acceptable. For an internal server with a self-signed certificate, load the
CA (`context.load_verify_locations(...)`) rather than turning verification off.

## 3. The methods that matter

### `login(user, password, *, initial_response_ok=True)`

Raises:

| Exception | Meaning |
|---|---|
| `SMTPAuthenticationError` | username or password rejected |
| `SMTPHeloError` | the server did not reply properly to HELO |
| `SMTPNotSupportedError` | the server does not support AUTH |
| `SMTPException` | no usable authentication method was found |

### `send_message(msg, from_addr=None, to_addrs=None, ...)`

A convenience method that sends an `email.message.Message` directly. It **extracts
sender and recipients from the headers per RFC 5322**, so there is no need to pass
addresses separately.

- `SMTPNotSupportedError` — a non-ASCII address on a server without SMTPUTF8
- `ValueError` — more than one set of `Resent-*` headers

### `starttls(*, context=None)`

Upgrades to TLS. **`ehlo()` must be called again afterwards** — the server's
capability list changes.

- `SMTPNotSupportedError` — the server does not support STARTTLS
- `RuntimeError` — this Python has no SSL/TLS support

### Context manager

`with` is supported (3.3+), and **`QUIT` is issued automatically** on exit.

## 4. The exception hierarchy — used directly for the retry split

```
SMTPException (subclass of OSError)
├── SMTPServerDisconnected
└── SMTPResponseException
    ├── SMTPSenderRefused
    ├── SMTPRecipientsRefused
    ├── SMTPDataError
    ├── SMTPConnectError
    ├── SMTPHeloError
    ├── SMTPNotSupportedError
    └── SMTPAuthenticationError
```

mailo splits these **in two.** A notifier should fail quietly, but "a failure you
can fix" and "a failure that resolves itself" have to look different to the user.

| Class | Exceptions | What mailo does |
|---|---|---|
| **Configuration error — retrying is pointless** | `SMTPAuthenticationError`, `SMTPRecipientsRefused`, `SMTPSenderRefused`, `SMTPNotSupportedError` | give up immediately; log **how to fix it** (for example, how to re-issue an app password) |
| **Transient — worth retrying** | `SMTPServerDisconnected`, `SMTPConnectError`, `TimeoutError`, `OSError` | one or two retries with a short backoff |

Because `SMTPException` is a subclass of `OSError`, catching `OSError` broadly to
handle network errors also catches authentication failures and sends them into
pointless retries. **Catch `SMTPException` first, then `OSError`.**

## 5. Skeleton of mailo's SMTP channel

```python
import smtplib, ssl
from email.message import EmailMessage

def send(cfg, event, title, body, meta):     # the shared adapter signature
    msg = EmailMessage()
    msg["From"] = cfg["username"]
    msg["To"] = cfg["to"]
    msg["Subject"] = title
    msg.set_content(body)                    # SMTP does not truncate — no real limit

    context = ssl.create_default_context()
    timeout = cfg.get("timeout", 30)

    if cfg.get("security", "tls") == "starttls":
        with smtplib.SMTP(cfg["host"], cfg.get("port", 587), timeout=timeout) as smtp:
            smtp.starttls(context=context)
            smtp.ehlo()                       # mandatory after the upgrade
            smtp.login(cfg["username"], cfg["password"])
            smtp.send_message(msg)
    else:
        with smtplib.SMTP_SSL(cfg["host"], cfg.get("port", 465),
                              context=context, timeout=timeout) as smtp:
            smtp.login(cfg["username"], cfg["password"])
            smtp.send_message(msg)
```

`event` and `meta` are accepted and unused. In mail the event is expressed as a
**subject emoji**, and the metadata is already in the text block of `body`
(DESIGN.md §8.1). Accepting two unused arguments keeps the registry simpler than
giving each channel its own signature — Discord builds the embed colour and
`fields` out of those same two.

The caller (the delivery orchestrator) handles exceptions according to the split in
section 4. The channel function itself never swallows anything; the only place that
does is the hook entry point (DESIGN.md §5.1).

### Encoding

`EmailMessage.set_content()` handles headers and encoding on its own when the body
contains non-ASCII characters, and the same goes for the subject. Non-ASCII subjects
and bodies need no special handling — the current `mailer.py` already relies on this
and it works.

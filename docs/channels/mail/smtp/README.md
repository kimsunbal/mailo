# docs/channels/mail/smtp — the SMTP standards and the Python implementation

> Checked: 2026-08-13 · the originals are authoritative

| File | Contents |
|---|---|
| [01-protocol.md](01-protocol.md) | RFC 5321, 8314, 6409 — the protocol, submission ports, TLS modes |
| [02-python-smtplib.md](02-python-smtplib.md) | `smtplib` and `email` — API, exception hierarchy, implementation patterns |

## Primary sources

| Source | URL |
|---|---|
| RFC 5321 — Simple Mail Transfer Protocol | <https://www.rfc-editor.org/rfc/rfc5321.html> |
| RFC 6409 — Message Submission for Mail | <https://www.rfc-editor.org/rfc/rfc6409.html> |
| RFC 8314 — Cleartext Considered Obsolete | <https://www.rfc-editor.org/rfc/rfc8314.html> |
| Python `smtplib` | <https://docs.python.org/3/library/smtplib.html> |
| Python `email.message` | <https://docs.python.org/3/library/email.message.html> |

## Summary

- **465 (implicit TLS) by default, 587 (STARTTLS) as the alternative** — the
  direction RFC 8314 recommends.
- `smtplib.SMTP_SSL` is implicit TLS; `smtplib.SMTP` plus `.starttls()` is STARTTLS.
- The TLS context is always `ssl.create_default_context()`, which turns on
  certificate verification and hostname checking by default. Code that builds its
  own context to disable verification is common on the internet and must not be
  used.
- Exceptions are well separated under `SMTPException`, so they map directly onto the
  **retryable / not retryable** split.

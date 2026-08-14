# 01 — the SMTP protocol and submission ports

> Sources: <https://www.rfc-editor.org/rfc/rfc8314.html> (read directly)
> · RFC 5321 <https://www.rfc-editor.org/rfc/rfc5321.html>
> · RFC 6409 <https://www.rfc-editor.org/rfc/rfc6409.html>
> Checked: 2026-08-13 · the originals are authoritative

## 1. The relevant standards

| RFC | Title | Role |
|---|---|---|
| **5321** | Simple Mail Transfer Protocol | SMTP itself: commands, response codes, transfer rules |
| **6409** | Message Submission for Mail | separates **submission** from relay; port 587 |
| **8314** | Cleartext Considered Obsolete | prefers implicit TLS; port 465 |

**Submission and relay are different things.** Mail servers exchanging messages
with each other is relay (port 25); a client handing a message to its own server is
submission (587/465). What mailo does is **submission**, so port 25 was never a
concern.

## 2. RFC 8314 — prefer implicit TLS

This RFC directly determines mailo's port choice.

> Connections to mail submission and mail access servers should be made
> *"preferring 'Implicit TLS' … over connecting to a 'cleartext' port and
> negotiating TLS with the STARTTLS command."*

The reasoning given is that implicit TLS is *"inherently simpler to implement,
debug, and deploy."* STARTTLS starts in the clear and upgrades, which carries a
downgrade attack surface and invites the implementation mistake of quietly
proceeding in cleartext when negotiation fails.

The transitional guidance is explicit too:

> Clients and servers *"SHOULD implement **both** STARTTLS on port 587 and Implicit
> TLS on port 465 during the transition period"* — but advertise the implicit TLS
> server in preference to STARTTLS.

### Terminology

| Name | Port | Behaviour |
|---|---|---|
| **Implicit TLS** (`submissions`) | **465** | TLS handshake immediately on connect; no cleartext phase |
| **STARTTLS** (`submission`) | **587** | connect in cleartext → `STARTTLS` command → upgrade to TLS |
| Relay | 25 | server to server; not for client submission |

> Port 465 was once reclaimed by IANA and then formally restored as the
> `submissions` service by RFC 8314. The old advice that "465 is non-standard and
> deprecated" is still circulating, and **it is now the opposite of true.**

## 3. What this means for mailo

### 3.1 Default: 465 with implicit TLS

The current `mailer.py` already does this:

```python
with smtplib.SMTP_SSL(host, 465, context=ssl.create_default_context(), timeout=30) as smtp:
```

**It follows the standard's recommendation, so it does not change.**

### 3.2 587 / STARTTLS available through configuration

Some internal mail servers only open 587, and RFC 8314 says to implement both
during the transition. The mode is a config choice:

```toml
[channels.smtp]
host = "smtp.gmail.com"
port = 465
security = "tls"        # "tls" = implicit TLS (465) | "starttls" = STARTTLS (587)
```

`security` is an explicit enum rather than inferred, because deducing the mode from
the port number breaks on servers using non-standard ports. **There is no plaintext
mode** — a configuration that sends credentials in the clear is not offered even as
an option.

### 3.3 Implementation notes

- On the STARTTLS path, **`ehlo()` must be called again after the upgrade.** The
  server's capability list differs before and after TLS. (See file 02.)
- On meeting a server without STARTTLS support, **fail rather than falling back to
  cleartext.** Let `SMTPNotSupportedError` propagate.

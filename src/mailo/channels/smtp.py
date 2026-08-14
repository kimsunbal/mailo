"""SMTP mail channel — the one that keeps a record.

Built on `smtplib` and `email.message` alone.

**There is no plaintext SMTP mode and no way to disable TLS verification.** Not
even as an option. If the server does not offer STARTTLS this fails rather than
falling back — a notifier leaking its own credentials in the clear is worse than
a notification that does not arrive.

Implicit TLS (465, RFC 8314) is the default. STARTTLS (587) is used only when
asked for explicitly.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any, Final

from mailo.errors import PermanentError, TransientError
from mailo.events import Event

NAME: Final = "smtp"

TIMEOUT: Final = 20
DEFAULT_DAILY_LIMIT: Final = 200

#: Server settings derived from the email domain (DESIGN.md §6.3.4).
#:
#: **Only verified entries belong here.** Outlook/Hotmail is deliberately absent
#: because basic auth is being retired for personal accounts; an unverified preset
#: produces the worst failure mode — settings that look right but will not
#: authenticate — and the user ends up doubting their own password.
PRESETS: Final[dict[str, tuple[str, int, str]]] = {
    "gmail.com": ("smtp.gmail.com", 465, "tls"),
    "googlemail.com": ("smtp.gmail.com", 465, "tls"),
    "naver.com": ("smtp.naver.com", 465, "tls"),
    "kakao.com": ("smtp.kakao.com", 465, "tls"),
    "daum.net": ("smtp.kakao.com", 465, "tls"),
    "hanmail.net": ("smtp.kakao.com", 465, "tls"),
}

_REMEDY_AUTH: Final = (
    "Gmail rejects account passwords. You need an app password.\n"
    "  Create one at https://myaccount.google.com/apppasswords\n"
    "  Organisation, school, and Advanced Protection accounts cannot create them\n"
    "  at all. In that case leave the mail channel empty and use Discord only —\n"
    "  mail is optional."
)


def preset_for(address: str) -> tuple[str, int, str] | None:
    """Derive host/port/security from an email address, or `None` if unknown."""
    _, _, domain = address.partition("@")
    return PRESETS.get(domain.strip().lower())


def _remedy_auth(host: str) -> str:
    if "gmail" in host or "google" in host:
        return _REMEDY_AUTH
    return (
        "Check the username and password. If the account uses two-factor auth,\n"
        "  it likely needs an app password rather than the account password.\n"
        "  Re-enter it with: mailo config set smtp.password"
    )


def _require(cfg: dict[str, Any]) -> tuple[str, int, str, str, str, str]:
    missing = [k for k in ("host", "username", "to") if not cfg.get(k)]
    if missing:
        raise PermanentError(
            f"SMTP config is incomplete: {', '.join(missing)}",
            "Set them with `mailo config set smtp.username` / `smtp.to`, or run `mailo init`.",
        )
    host = str(cfg["host"])
    port = int(cfg.get("port") or 465)
    security = str(cfg.get("security") or ("tls" if port == 465 else "starttls"))
    username = str(cfg["username"])
    password = str(cfg.get("password") or "")
    to = str(cfg["to"])
    return host, port, security, username, password, to


def build_message(
    cfg: dict[str, Any],
    event: Event,
    title: str,
    body: str,
    meta: dict[str, str],
) -> EmailMessage:
    """Put the event emoji in the subject and the metadata below the body.

    **Nothing is truncated.** SMTP has no length limit worth honouring here.
    """
    _, _, _, username, _, to = _require(cfg)

    lines = [body.rstrip()] if body.strip() else []
    if meta:
        width = max(len(k) for k in meta)
        lines.append("")
        lines.extend(f"{k.ljust(width)}  {v}" for k, v in meta.items() if v)
    lines.append("")
    lines.append("-- mailo")

    msg = EmailMessage()
    msg["From"] = username
    msg["To"] = to
    msg["Subject"] = f"{event.emoji} {title}"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=username.partition("@")[2] or None)
    msg["X-Mailo-Event"] = str(event)
    msg.set_content("\n".join(lines))
    return msg


def send(
    cfg: dict[str, Any],
    event: Event,
    title: str,
    body: str,
    meta: dict[str, str],
) -> None:
    message = build_message(cfg, event, title, body, meta)
    with _connect(cfg) as server:
        server.send_message(message)


def verify(cfg: dict[str, Any]) -> str:
    """Connect and authenticate only — **no mail is sent.**"""
    host, port, security, username, _, to = _require(cfg)
    with _connect(cfg):
        pass
    return f"{username} @ {host}:{port} ({security}) -> {to}"


class _Session:
    """An SMTP connection as a context manager, translating errors to mailo's split."""

    __slots__ = ("_cfg", "_server")

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._cfg = cfg
        self._server: smtplib.SMTP | None = None

    def __enter__(self) -> smtplib.SMTP:
        host, port, security, username, password, _ = _require(self._cfg)
        context = ssl.create_default_context()  # there is no path that weakens this
        try:
            if security == "tls":
                server: smtplib.SMTP = smtplib.SMTP_SSL(
                    host, port, timeout=TIMEOUT, context=context
                )
            else:
                server = smtplib.SMTP(host, port, timeout=TIMEOUT)
                server.ehlo()
                server.starttls(context=context)  # unsupported -> raise, never downgrade
                server.ehlo()
            if password:
                server.login(username, password)
        except smtplib.SMTPAuthenticationError as exc:
            raise PermanentError(f"SMTP authentication failed ({host})",
                                 _remedy_auth(host)) from exc
        except smtplib.SMTPNotSupportedError as exc:
            raise PermanentError(
                f"{host}:{port} does not support STARTTLS",
                "Use implicit TLS instead: mailo config set smtp.port 465, "
                "smtp.security tls.\n"
                "There is deliberately no fallback to plaintext.",
            ) from exc
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as exc:
            raise TransientError(f"cannot reach {host}:{port}: {exc}") from exc
        except smtplib.SMTPException as exc:
            # SMTPException subclasses OSError, so it must be caught first.
            raise PermanentError(f"SMTP error ({host}): {exc}") from exc
        except ssl.SSLError as exc:
            raise PermanentError(
                f"TLS error ({host}:{port}): {exc}",
                "Check the port and security pairing — 465 is tls, 587 is starttls.",
            ) from exc
        except OSError as exc:
            raise TransientError(f"cannot reach {host}:{port}: {exc}") from exc

        self._server = server
        return server

    def __exit__(self, *exc_info: object) -> None:
        if self._server is None:
            return
        try:
            self._server.quit()
        except (smtplib.SMTPException, OSError):
            self._server.close()


def _connect(cfg: dict[str, Any]) -> _Session:
    return _Session(cfg)

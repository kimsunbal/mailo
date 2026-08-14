"""The CLI — argument parsing and command implementations.

There are three ways in, and **all three share one schema** (DESIGN.md §6.3):

- `mailo init` — first time. Discover, one paste, verify.
- `mailo config set KEY [VALUE]` — a single value, in the spirit of `git config`.
- `mailo init --from -` — a one-line transfer from another machine.

`init` amounts to calling `config set` several times.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

from mailo import __version__, channels, config, hooks, notify, onboard, ui
from mailo.config import Config
from mailo.errors import ChannelError, MailoError
from mailo.events import Event
from mailo.schema import SCHEMA, coerce, lookup, mask

# ── init ────────────────────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    if args.from_:
        return _init_from_line()

    ui.rule("mailo setup")

    collected: dict[str, Any] = {}

    # 1. Look first. Finding nothing costs nothing.
    found, source = onboard.discover()
    if found:
        ui.out()
        ui.info(f"Found an existing configuration: {ui.bold(source)}")
        ui.kv([(k, mask(k, v)) for k, v in sorted(found.items())])
        ui.out()
        if ui.confirm("Import these values?"):
            collected.update(found)

    # 2. One paste, no required order.
    missing = _missing(collected)
    if missing:
        ui.out()
        blob = ui.paste(_paste_prompt(missing))
        parsed = onboard.parse_blob(blob)
        for warning in parsed.warnings:
            ui.warn(warning.splitlines()[0])
            ui.hint("\n".join(warning.splitlines()[1:]))
        collected.update(parsed)

    clean, problems = onboard.validate(collected)
    for problem in problems:
        ui.warn(problem)

    if not clean:
        ui.out()
        ui.fail("Nothing recognisable to configure.")
        ui.hint(
            "A Discord webhook URL alone is enough to get started.\n"
            "Channel Settings -> Integrations -> Webhooks -> New Webhook -> Copy URL"
        )
        return 1

    ui.out()
    ui.out(ui.bold("Recognised:"))
    ui.kv([(k, mask(k, v)) for k, v in sorted(clean.items())])
    ui.out()
    if not ui.confirm("Is this right?"):
        ui.info("Cancelled. Nothing was saved.")
        return 1

    # 3. Verify before saving.
    config.apply_many(clean)
    cfg = config.load()

    # Point routing at channels that actually exist; otherwise a Discord-only
    # setup loses its done and custom notifications entirely.
    rerouted = config.adapt_routing(cfg)
    if rerouted:
        config.apply_many(rerouted)
        cfg = config.load()
        ui.info(f"Adjusted routing to the configured channels: {', '.join(sorted(rerouted))}")

    ui.out()
    verified = _verify_all(cfg, allow_retry=not args.no_verify, skip=args.no_verify)

    ui.out()
    ui.ok(f"Saved to {ui.bold(str(config.config_path()))}")
    _post_init(cfg, verified)
    return 0


def _init_from_line() -> int:
    """`mailo init --from -` — take a line produced on another machine via stdin."""
    line = ui.read_stdin().strip()
    if not line:
        raise MailoError(
            "the transfer string was empty",
            "On the other machine: mailo config export | ssh thishost 'mailo init --from -'",
        )
    values = config.import_line(line)
    if not values:
        raise MailoError("the transfer string contained nothing usable", "")

    config.apply_many(values)
    cfg = config.load()
    ui.ok(f"Imported {len(values)} keys into {config.config_path()}")
    ui.kv([(k, mask(k, v)) for k, v in sorted(values.items())])
    ui.out()
    ui.info(f"This machine identifies as {ui.bold(cfg.machine)} (hostname)")
    _verify_all(cfg, allow_retry=False)
    return 0


def _missing(collected: dict[str, Any]) -> list[str]:
    """What is still absent. Discord alone is enough to finish onboarding."""
    has_discord = "discord.webhook_url" in collected
    has_smtp = {"smtp.username", "smtp.password", "smtp.to"} <= set(collected)
    if has_discord and has_smtp:
        return []
    missing = []
    if not has_discord:
        missing.append("discord")
    if not has_smtp:
        missing.append("smtp")
    return missing


def _paste_prompt(missing: list[str]) -> str:
    wanted = []
    if "discord" in missing:
        wanted.append("Discord webhook URL")
    if "smtp" in missing:
        wanted.append("email address, app password")
    return (
        f"Paste your {ui.bold(', '.join(wanted))} in any order. "
        "Whatever you have is fine."
    )


def _verify_all(cfg: Config, *, allow_retry: bool, skip: bool = False) -> list[str]:
    """Check each configured channel — nothing is sent."""
    if skip:
        return []
    verified: list[str] = []
    for name in cfg.active_channels():
        try:
            detail = notify.verify(cfg, name)
            ui.ok(f"{name}: {detail}")
            verified.append(name)
        except ChannelError as exc:
            ui.fail(f"{name}: {exc.message}")
            if exc.remedy:
                ui.hint(exc.remedy)
            retry = allow_retry and ui.confirm(f"Re-enter the {name} settings?", default=True)
            if retry and _reprompt(name):
                return _verify_all(config.load(), allow_retry=False)
    return verified


def _reprompt(name: str) -> bool:
    """Ask again for the values of a channel that failed verification."""
    keys = [k for k in SCHEMA if k.startswith(f"{name}.")]
    changed = False
    for key in keys:
        spec = SCHEMA[key]
        current = config.load(require=False).get(key)
        if current is None and not spec.secret:
            continue
        value = ui.secret(f"{key}") if spec.secret else ui.ask(key, str(current or ""))
        if not value:
            continue
        try:
            config.set_key(key, coerce(key, value))
            changed = True
        except MailoError as exc:
            ui.fail(exc.message)
    return changed


def _post_init(cfg: Config, verified: list[str]) -> None:
    """What to say once setup is done — miss it here and the user never finds it."""
    if "discord" in verified and ui.confirm("\nSend a test notification to Discord?"):
        _send_test(cfg, "discord")

    if "smtp" not in cfg.active_channels():
        ui.out()
        ui.info("Mail is not configured — that is fine, it is optional.")
        ui.hint(
            "To add it later: mailo config set smtp.username you@gmail.com\n"
            "Consider a dedicated account for this. It sidesteps organisation\n"
            "accounts that cannot issue app passwords, and keeps a daily-cap\n"
            "lockout away from the mailbox you actually use."
        )

    # This has to be said even when verification was skipped: the whole
    # deliverability of `blocked` rests on the user's Discord settings (§6.4).
    if "discord" in cfg.active_channels():
        ui.out()
        ui.info("Check your Discord notification settings — the most important alerts land there.")
        ui.bullets(
            [
                "Make a dedicated channel for mailo, separate from conversations",
                'Set that channel to notify on "All Messages"',
                "Turn on mobile push for that server and channel",
            ]
        )

    ui.out()
    if ui.confirm("Register the Claude Code hooks now?"):
        path, installed = hooks.install("user")
        ui.ok(f"Registered {', '.join(installed)} in {path}")
    else:
        ui.hint("Later: mailo install-hooks")


# ── config ──────────────────────────────────────────────────────────────────


def cmd_config_set(args: argparse.Namespace) -> int:
    key = args.key
    spec = lookup(key)

    if args.value is not None and spec.secret:
        raise MailoError(
            f"{key} is not accepted on the command line",
            "It would be visible to other processes via ps and kept in shell history.\n"
            f"  Omit the value to be prompted:  mailo config set {key}\n"
            f"  Or pipe it in:                  ... | mailo config set {key} --stdin",
        )

    if args.stdin:
        raw = ui.read_stdin().strip()
    elif args.value is not None:
        raw = args.value
    elif spec.secret:
        raw = ui.secret(f"{key} ({spec.help})")
    else:
        current = config.load(require=False).get(key)
        raw = ui.ask(f"{key} ({spec.help})", str(current) if current is not None else "")

    if not raw:
        raise MailoError(f"no value given for {key}", spec.help)

    value = coerce(key, raw)
    config.set_key(key, value)
    ui.ok(f"{key} = {mask(key, value)}")

    if not args.no_verify:
        _verify_touched(key)
    return 0


def _verify_touched(key: str) -> None:
    """Check only the channel just edited; stay quiet for keys with nothing to check."""
    name = key.split(".")[0]
    if name not in channels.ALL:
        return
    cfg = config.load(require=False)
    if not cfg.configured(name):
        return
    try:
        ui.ok(f"{name}: {notify.verify(cfg, name)}")
    except ChannelError as exc:
        ui.fail(f"{name}: {exc.message}")
        if exc.remedy:
            ui.hint(exc.remedy)


def cmd_config_get(args: argparse.Namespace) -> int:
    cfg = config.load(require=False)
    value = cfg.get(args.key)
    if value is None:
        ui.fail(f"{args.key} is not set")
        return 1
    if args.reveal:
        print(value if not isinstance(value, list) else ",".join(map(str, value)))
    else:
        print(mask(args.key, value))
    return 0


def cmd_config_list(args: argparse.Namespace) -> int:
    cfg = config.load(require=False)
    ui.rule(str(config.config_path()))

    section = ""
    rows: list[tuple[str, str]] = []
    for key in SCHEMA:
        head = key.split(".")[0] if "." in key else "general"
        if head != section:
            _flush(rows)
            rows = []
            section = head
            ui.out()
            ui.out(ui.bold(f"[{section}]"))
        value = cfg.get(key)
        if value is None:
            rows.append((key, ui.dim("(unset)")))
        else:
            rows.append((key, value if args.reveal else mask(key, value)))
    _flush(rows)

    ui.out()
    active = cfg.active_channels()
    ui.info(f"Active channels: {', '.join(active) if active else 'none — run mailo init'}")
    ui.info(f"Machine identifier: {cfg.machine}")
    return 0


def _flush(rows: list[tuple[str, str]]) -> None:
    if rows:
        ui.kv([(k, str(v)) for k, v in rows])


def cmd_config_unset(args: argparse.Namespace) -> int:
    if config.unset_key(args.key):
        ui.ok(f"Removed {args.key}")
        return 0
    ui.warn(f"{args.key} was not set")
    return 1


def cmd_config_edit(args: argparse.Namespace) -> int:
    path = config.ensure_file()
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    subprocess.call([*editor.split(), str(path)])
    try:
        config.load()
    except MailoError as exc:
        ui.fail(exc.message)
        if exc.remedy:
            ui.hint(exc.remedy)
        return 1
    ui.ok("Configuration is valid")
    return 0


def cmd_config_export(args: argparse.Namespace) -> int:
    line = config.export(secrets=not args.no_secrets)
    if not args.no_secrets:
        ui.warn("The line below is plaintext credentials — do not paste it into chat or an issue.")
        ui.hint("Transfer with: mailo config export | ssh otherhost 'mailo init --from -'")
    print(line)
    return 0


# ── sending ─────────────────────────────────────────────────────────────────


def cmd_test(args: argparse.Namespace) -> int:
    cfg = config.load()
    targets = [args.channel] if args.channel else cfg.active_channels()
    if not targets:
        raise MailoError("no channels configured", "Run `mailo init`.")

    failed = False
    for name in targets:
        try:
            ui.ok(f"{name}: {notify.verify(cfg, name)}")
        except ChannelError as exc:
            failed = True
            ui.fail(f"{name}: {exc.message}")
            if exc.remedy:
                ui.hint(exc.remedy)
            continue
        _send_test(cfg, name)
    return 1 if failed else 0


def _send_test(cfg: Config, name: str) -> None:
    note = notify.Notification(
        event=Event.CUSTOM,
        title=f"[{cfg.machine}] mailo test",
        body="If you can see this, the setup works.",
        meta=notify.build_meta(cfg, cwd=os.getcwd()),
        session_id="test",
    )
    results = notify.dispatch(cfg, note, only=name, ignore_suppression=True)
    if notify.any_sent(results):
        ui.ok(f"{name}: test notification sent")
    else:
        ui.fail(f"{name}: {notify.describe(results)}")


def cmd_send(args: argparse.Namespace) -> int:
    cfg = config.load()
    if args.to:
        cfg.data.setdefault("channels", {}).setdefault("smtp", {})["to"] = args.to

    body = args.body
    if body is None and not sys.stdin.isatty():
        body = ui.read_stdin().strip()

    note = notify.Notification(
        event=Event(args.event),
        title=f"[{cfg.machine}] {args.subject}",
        body=body or "",
        meta=notify.build_meta(cfg, cwd=os.getcwd()),
        session_id="send",
    )
    results = notify.dispatch(cfg, note, only=args.channel, ignore_suppression=True)
    if notify.any_sent(results):
        ui.ok(notify.describe(results))
        return 0
    ui.fail(notify.describe(results))
    ui.hint(f"Details in {config.state_dir() / 'mailo.log'}")
    return 1


def cmd_run(args: argparse.Namespace) -> int:
    from mailo.runner import run

    command = [c for c in args.command if c != "--"] if args.command else []
    if not command:
        raise MailoError("no command to run", "mailo run --name train -- ./run-train.sh")
    return run(config.load(), command, name=args.name)


def cmd_hook(args: argparse.Namespace) -> int:
    return hooks.run()


# ── hook wiring ─────────────────────────────────────────────────────────────


def cmd_install_hooks(args: argparse.Namespace) -> int:
    events = [e.strip() for e in args.events.split(",")] if args.events else None
    if events:
        unknown = [e for e in events if e not in {v.value for v in Event}]
        if unknown:
            raise MailoError(
                f"unknown event: {', '.join(unknown)}",
                f"available: {', '.join(e.value for e in Event)}",
            )
    path, installed = hooks.install(args.scope, events)
    ui.ok(f"Hooks registered in {path}")
    ui.bullets(installed)
    if events:
        ui.hint("SessionStart is always registered regardless of --events; "
                "without it notifications lose the project name.")
    return 0


def cmd_uninstall_hooks(args: argparse.Namespace) -> int:
    path, removed = hooks.uninstall(args.scope)
    if removed:
        ui.ok(f"Removed {removed} mailo hook(s) from {path}")
    else:
        ui.warn(f"No mailo hooks to remove in {path}")
    return 0


# ── parser ──────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mailo",
        description="Tell me when my AI agent gets stuck, dies, or finishes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"mailo {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_init = sub.add_parser("init", help="create the configuration")
    p_init.add_argument(
        "--from", dest="from_", metavar="-", nargs="?", const="-",
        help="read a `mailo config export` line from stdin instead of prompting",
    )
    p_init.add_argument("--no-verify", action="store_true", help="skip verification before saving")
    p_init.set_defaults(func=cmd_init)

    p_config = sub.add_parser("config", help="set and inspect config keys")
    config_sub = p_config.add_subparsers(dest="action", metavar="<action>", required=True)

    p_set = config_sub.add_parser("set", help="set one key")
    p_set.add_argument("key")
    p_set.add_argument("value", nargs="?", help="omit to be prompted; required for secrets")
    p_set.add_argument("--stdin", action="store_true", help="read the value from stdin")
    p_set.add_argument("--no-verify", action="store_true")
    p_set.set_defaults(func=cmd_config_set)

    p_get = config_sub.add_parser("get", help="print one value")
    p_get.add_argument("key")
    p_get.add_argument("--reveal", action="store_true", help="print secrets unmasked")
    p_get.set_defaults(func=cmd_config_get)

    p_list = config_sub.add_parser("list", help="show the whole configuration")
    p_list.add_argument("--reveal", action="store_true")
    p_list.set_defaults(func=cmd_config_list)

    p_unset = config_sub.add_parser("unset", help="remove a key")
    p_unset.add_argument("key")
    p_unset.set_defaults(func=cmd_config_unset)

    config_sub.add_parser("edit", help="open it in $EDITOR").set_defaults(func=cmd_config_edit)

    p_export = config_sub.add_parser("export", help="print the configuration as one line")
    p_export.add_argument("--no-secrets", action="store_true", help="leave credentials out")
    p_export.set_defaults(func=cmd_config_export)

    p_test = sub.add_parser("test", help="verify the configuration and send a test")
    p_test.add_argument("-c", "--channel", choices=channels.ALL)
    p_test.set_defaults(func=cmd_test)

    p_send = sub.add_parser("send", help="send a notification directly")
    p_send.add_argument("-e", "--event", default=Event.CUSTOM.value,
                        choices=[e.value for e in Event])
    p_send.add_argument("-s", "--subject", required=True)
    p_send.add_argument("-b", "--body", help="omit to read from stdin")
    p_send.add_argument("-c", "--channel", choices=channels.ALL)
    p_send.add_argument("--to", help="override the recipient for this send only")
    p_send.set_defaults(func=cmd_send)

    p_run = sub.add_parser("run", help="wrap a command and notify when it ends")
    p_run.add_argument("--name", help="name used in the notification; defaults to the command")
    p_run.add_argument("command", nargs=argparse.REMAINDER)
    p_run.set_defaults(func=cmd_run)

    sub.add_parser("hook", help="hook entry point (reads JSON on stdin)").set_defaults(
        func=cmd_hook
    )

    p_install = sub.add_parser("install-hooks", help="register the Claude Code hooks")
    _scope(p_install)
    p_install.add_argument("--events", help="for example: blocked,failed")
    p_install.set_defaults(func=cmd_install_hooks)

    p_uninstall = sub.add_parser("uninstall-hooks", help="remove the Claude Code hooks")
    _scope(p_uninstall)
    p_uninstall.set_defaults(func=cmd_uninstall_hooks)

    return parser


def _scope(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--user", dest="scope", action="store_const", const="user",
                       help="~/.claude/settings.json (default)")
    group.add_argument("--project", dest="scope", action="store_const", const="project",
                       help="./.claude/settings.json")
    parser.set_defaults(scope="user")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "func", None):
        parser.print_help()
        return 1

    try:
        return int(args.func(args) or 0)
    except MailoError as exc:
        ui.fail(exc.message)
        if exc.remedy:
            ui.hint(exc.remedy)
        return 1
    except KeyboardInterrupt:
        ui.out()
        ui.warn("Interrupted")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

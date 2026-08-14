"""Routing fallback — notifications must never vanish silently."""

import pathlib
import unittest
from unittest import mock

from mailo import config, notify
from mailo.events import Event


def _cfg(data):
    return config.Config(data, pathlib.Path("/dev/null"))


DISCORD_ONLY = {
    "channels": {"discord": {"webhook_url": "https://discord.com/api/webhooks/1/aaa"}},
}


class RoutingFallback(unittest.TestCase):
    def test_done_reaches_discord_when_smtp_absent(self):
        # The default routing is done = ["smtp"]. Without mail it used to vanish.
        cfg = _cfg(DISCORD_ONLY)
        with mock.patch("mailo.channels.discord.send") as send:
            results = notify.dispatch(
                cfg, notify.Notification(Event.DONE, "t"), ignore_suppression=True
            )
        send.assert_called_once()
        self.assertTrue(notify.any_sent(results))

    def test_no_fallback_when_target_is_configured(self):
        cfg = _cfg(DISCORD_ONLY)
        with mock.patch("mailo.channels.discord.send") as send:
            notify.dispatch(
                cfg, notify.Notification(Event.BLOCKED, "t"), ignore_suppression=True
            )
        send.assert_called_once()

    def test_explicit_channel_is_never_rerouted(self):
        cfg = _cfg(DISCORD_ONLY)
        results = notify.dispatch(
            cfg, notify.Notification(Event.DONE, "t"), only="smtp", ignore_suppression=True
        )
        self.assertEqual([r.detail for r in results], ["not configured"])

    def test_nothing_configured_sends_nothing(self):
        results = notify.dispatch(
            _cfg({}), notify.Notification(Event.DONE, "t"), ignore_suppression=True
        )
        self.assertFalse(notify.any_sent(results))


class AdaptRouting(unittest.TestCase):
    def test_discord_only_config_gets_explicit_routing(self):
        changed = config.adapt_routing(_cfg(DISCORD_ONLY))
        self.assertEqual(changed["routing.done"], ["discord"])
        self.assertEqual(changed["routing.custom"], ["discord"])
        self.assertNotIn("routing.blocked", changed)  # already discord

    def test_both_channels_change_nothing(self):
        cfg = _cfg(
            {
                "channels": {
                    "discord": {"webhook_url": "https://discord.com/api/webhooks/1/aaa"},
                    "smtp": {"host": "h", "username": "a@b.c", "to": "a@b.c"},
                }
            }
        )
        self.assertEqual(config.adapt_routing(cfg), {})


class Metadata(unittest.TestCase):
    def test_only_the_directory_name_is_included(self):
        meta = notify.build_meta(_cfg({"machine": "box"}), cwd="/home/someone/work/secret")
        self.assertEqual(meta["project"], "secret")
        self.assertNotIn("/home/someone", str(meta))

    def test_duration_formatting(self):
        cfg = _cfg({})
        self.assertEqual(notify.build_meta(cfg, elapsed=45)["elapsed"], "45s")
        self.assertEqual(notify.build_meta(cfg, elapsed=125)["elapsed"], "2m 5s")
        self.assertEqual(notify.build_meta(cfg, elapsed=8040)["elapsed"], "2h 14m")


if __name__ == "__main__":
    unittest.main()

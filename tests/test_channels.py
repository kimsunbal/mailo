"""Channel adapters — payload shape, truncation, error classification, masking."""

import json
import unittest
import urllib.error
from typing import ClassVar

from mailo.channels import discord, smtp
from mailo.errors import PermanentError, TransientError
from mailo.events import Event

WEBHOOK = "https://discord.com/api/webhooks/1399582011/aBcD-xY_z"


class DiscordPayload(unittest.TestCase):
    def test_color_is_serialised_as_decimal_by_json(self):
        payload = discord.build_payload(Event.BLOCKED, "title", "body", {})
        self.assertEqual(payload["embeds"][0]["color"], 0xE8A33D)
        self.assertIn('"color": 15246141', json.dumps(payload))

    def test_description_is_clipped_by_characters(self):
        # Multi-byte input on purpose: Discord counts characters, not bytes.
        body = "é" * 5000
        embed = discord.build_payload(Event.DONE, "t", body, {})["embeds"][0]
        self.assertEqual(len(embed["description"]), discord.MAX_DESCRIPTION)

    def test_meta_becomes_fields(self):
        embed = discord.build_payload(Event.DONE, "t", "", {"machine": "box", "empty": ""})
        self.assertEqual([f["name"] for f in embed["embeds"][0]["fields"]], ["machine"])

    def test_no_description_when_body_empty(self):
        embed = discord.build_payload(Event.DONE, "t", "", {})["embeds"][0]
        self.assertNotIn("description", embed)


class DiscordErrors(unittest.TestCase):
    def _http(self, code, body=b"{}"):
        import io

        return urllib.error.HTTPError(WEBHOOK, code, "reason", {}, io.BytesIO(body))

    def test_404_is_permanent_with_remedy(self):
        err = discord._classify(self._http(404))
        self.assertIsInstance(err, PermanentError)
        self.assertIn("webhook", err.remedy.lower())

    def test_429_honours_retry_after(self):
        err = discord._classify(self._http(429, b'{"retry_after": 3.5}'))
        self.assertIsInstance(err, TransientError)
        self.assertEqual(err.retry_after, 3.5)

    def test_429_with_absurd_wait_gives_up(self):
        # A `blocked` notification two minutes late is one never sent.
        err = discord._classify(self._http(429, b'{"retry_after": 300}'))
        self.assertIsInstance(err, PermanentError)

    def test_5xx_is_transient(self):
        self.assertIsInstance(discord._classify(self._http(503)), TransientError)


class Masking(unittest.TestCase):
    def test_token_never_appears(self):
        masked = discord.mask(WEBHOOK)
        self.assertNotIn("aBcD-xY_z", masked)
        self.assertIn("1399582011", masked)

    def test_garbage_is_masked_too(self):
        self.assertNotIn("secret", discord.mask("https://evil/secret"))


class SmtpMessage(unittest.TestCase):
    CFG: ClassVar[dict] = {
        "host": "smtp.gmail.com",
        "port": 465,
        "username": "you@gmail.com",
        "to": "inbox@example.com",
    }

    def test_subject_carries_event_emoji(self):
        msg = smtp.build_message(self.CFG, Event.FAILED, "training failed", "body", {})
        self.assertTrue(msg["Subject"].startswith(Event.FAILED.emoji))
        self.assertEqual(msg["X-Mailo-Event"], "failed")

    def test_meta_is_appended_not_truncated(self):
        body = "x" * 10000
        msg = smtp.build_message(self.CFG, Event.DONE, "t", body, {"machine": "box"})
        payload = msg.get_content()
        self.assertIn("x" * 10000, payload)  # SMTP does not truncate
        self.assertIn("machine", payload)

    def test_missing_fields_are_permanent(self):
        with self.assertRaises(PermanentError):
            smtp.build_message({"host": "h"}, Event.DONE, "t", "", {})


class Presets(unittest.TestCase):
    def test_known_domains(self):
        self.assertEqual(smtp.preset_for("a@gmail.com"), ("smtp.gmail.com", 465, "tls"))
        self.assertEqual(smtp.preset_for("a@daum.net")[0], "smtp.kakao.com")

    def test_outlook_is_deliberately_absent(self):
        # Basic auth is being retired there; unverified presets fail the worst way.
        self.assertIsNone(smtp.preset_for("a@outlook.com"))

    def test_unknown_domain(self):
        self.assertIsNone(smtp.preset_for("a@example.org"))


if __name__ == "__main__":
    unittest.main()

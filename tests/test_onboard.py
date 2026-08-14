"""Paste parsing. Not demanding an order is the point of the exercise."""

import unittest

from mailo import onboard

WEBHOOK = "https://discord.com/api/webhooks/1399582011/aBcD-xY_z"


class ParseBlob(unittest.TestCase):
    def test_order_does_not_matter(self):
        first = onboard.parse_blob(f"{WEBHOOK}\nyou@gmail.com\nabcd efgh ijkl mnop\n")
        second = onboard.parse_blob(f"abcd efgh ijkl mnop\nyou@gmail.com\n{WEBHOOK}\n")
        self.assertEqual(dict(first), dict(second))

    def test_recognises_each_field(self):
        found = onboard.parse_blob(f"{WEBHOOK} you@gmail.com abcd efgh ijkl mnop")
        self.assertEqual(found["discord.webhook_url"], WEBHOOK)
        self.assertEqual(found["smtp.username"], "you@gmail.com")
        self.assertEqual(found["smtp.password"], "abcdefghijklmnop")

    def test_app_password_spaces_are_stripped(self):
        found = onboard.parse_blob("you@gmail.com\nabcd efgh ijkl mnop")
        self.assertEqual(found["smtp.password"], "abcdefghijklmnop")

    def test_email_is_not_mistaken_for_password(self):
        found = onboard.parse_blob("abcdefgh@gmail.com")
        self.assertNotIn("smtp.password", found)
        self.assertEqual(found["smtp.username"], "abcdefgh@gmail.com")

    def test_preset_fills_host_and_port(self):
        found = onboard.parse_blob("you@gmail.com")
        self.assertEqual(found["smtp.host"], "smtp.gmail.com")
        self.assertEqual(found["smtp.port"], 465)
        self.assertEqual(found["smtp.security"], "tls")

    def test_unknown_domain_has_no_preset(self):
        found = onboard.parse_blob("you@example.org")
        self.assertNotIn("smtp.host", found)

    def test_second_email_becomes_recipient(self):
        found = onboard.parse_blob("send@gmail.com\ninbox@example.com")
        self.assertEqual(found["smtp.username"], "send@gmail.com")
        self.assertEqual(found["smtp.to"], "inbox@example.com")

    def test_channel_url_is_rejected_with_guidance(self):
        found = onboard.parse_blob("https://discord.com/channels/123/456")
        self.assertNotIn("discord.webhook_url", found)
        self.assertTrue(found.warnings)
        self.assertIn("webhook", found.warnings[0].lower())

    def test_quotes_and_whitespace_are_stripped(self):
        found = onboard.parse_blob(f'  "{WEBHOOK}"  ')
        self.assertEqual(found["discord.webhook_url"], WEBHOOK)

    def test_legacy_config_pasted_whole(self):
        legacy = (
            "USERNAME=you@gmail.com\n"
            "APP_PASSWORD=abcdefghijklmnop\n"
            "DEFAULT_TO=inbox@example.com\n"
            "SUBJECT_PREFIX=[box-a]\n"
            "# SMTP_HOST=smtp.gmail.com\n"
        )
        found = onboard.parse_blob(legacy)
        self.assertEqual(found["smtp.username"], "you@gmail.com")
        self.assertEqual(found["smtp.password"], "abcdefghijklmnop")
        self.assertEqual(found["smtp.to"], "inbox@example.com")
        self.assertEqual(found["machine"], "box-a")

    def test_empty_input(self):
        self.assertEqual(dict(onboard.parse_blob("")), {})


class Validate(unittest.TestCase):
    def test_bad_webhook_is_reported_not_silently_dropped(self):
        clean, problems = onboard.validate({"discord.webhook_url": "https://example.com/x"})
        self.assertNotIn("discord.webhook_url", clean)
        self.assertTrue(problems)

    def test_good_values_pass(self):
        clean, problems = onboard.validate(
            {"smtp.username": "you@gmail.com", "smtp.port": 465}
        )
        self.assertEqual(problems, [])
        self.assertEqual(clean["smtp.port"], 465)


if __name__ == "__main__":
    unittest.main()

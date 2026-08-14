"""Config loading, writing, and transfer. Runs entirely inside a temp directory."""

import os
import stat
import tempfile
import unittest
from pathlib import Path

from mailo import config
from mailo.errors import ConfigError


class Sandbox(unittest.TestCase):
    """Point `$MAILO_CONFIG` at a temporary file for the duration of the test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = {k: os.environ.get(k) for k in ("MAILO_CONFIG", "XDG_STATE_HOME")}
        root = Path(self._tmp.name)
        os.environ["MAILO_CONFIG"] = str(root / "config.toml")
        os.environ["XDG_STATE_HOME"] = str(root / "state")

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()


class SetAndLoad(Sandbox):
    def test_set_creates_file_with_600(self):
        path = config.set_key("machine", "box-a")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(config.load().machine, "box-a")

    def test_template_comments_survive_a_set(self):
        config.ensure_file()
        config.set_key("triggers.cooldown_sec", 30)
        text = config.config_path().read_text(encoding="utf-8")
        self.assertIn("it holds credentials", text)
        self.assertIn("cooldown_sec = 30", text)

    def test_machine_defaults_to_hostname(self):
        config.ensure_file()
        self.assertTrue(config.load().machine)

    def test_loose_permissions_are_rejected(self):
        path = config.ensure_file()
        os.chmod(path, 0o644)
        with self.assertRaises(ConfigError) as ctx:
            config.load()
        self.assertIn("chmod 600", ctx.exception.remedy)

    def test_unknown_key_suggests_a_near_match(self):
        with self.assertRaises(ConfigError) as ctx:
            config.set_key("smtp.usernme", "x")
        self.assertIn("smtp.username", ctx.exception.remedy)

    def test_env_override_beats_file(self):
        config.set_key("discord.webhook_url", "https://discord.com/api/webhooks/1/aaa")
        os.environ["MAILO_DISCORD_WEBHOOK_URL"] = "https://discord.com/api/webhooks/2/bbb"
        try:
            self.assertIn("/2/bbb", config.load().channel("discord")["webhook_url"])
        finally:
            os.environ.pop("MAILO_DISCORD_WEBHOOK_URL")

    def test_unset(self):
        config.set_key("triggers.cooldown_sec", 30)
        self.assertTrue(config.unset_key("triggers.cooldown_sec"))
        self.assertIsNone(config.load().get("triggers.cooldown_sec"))

    def test_missing_config_explains_how_to_make_one(self):
        with self.assertRaises(ConfigError) as ctx:
            config.load()
        self.assertIn("mailo init", ctx.exception.remedy)


class ExportImport(Sandbox):
    def test_round_trip_without_machine(self):
        config.set_key("machine", "box-a")
        config.set_key("smtp.username", "you@gmail.com")
        config.set_key("smtp.host", "smtp.gmail.com")
        line = config.export()
        self.assertTrue(line.startswith(config.EXPORT_PREFIX))

        values = config.import_line(line)
        self.assertEqual(values["smtp.username"], "you@gmail.com")
        # `machine` is left out on purpose so the hostname fills it in per machine.
        self.assertNotIn("machine", values)

    def test_no_secrets_drops_credentials(self):
        config.set_key("smtp.username", "you@gmail.com")
        config.set_key("smtp.password", "abcdefghijklmnop")
        values = config.import_line(config.export(secrets=False))
        self.assertIn("smtp.username", values)
        self.assertNotIn("smtp.password", values)

    def test_garbage_is_rejected(self):
        with self.assertRaises(ConfigError):
            config.import_line("not-a-mailo-line")


if __name__ == "__main__":
    unittest.main()

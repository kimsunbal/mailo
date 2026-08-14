"""The in-place TOML editor. Preserving comments and ordering is the whole point."""

import tomllib
import unittest

from mailo import tomlwrite


class SetValue(unittest.TestCase):
    def test_replaces_existing_and_keeps_trailing_comment(self):
        src = "[channels.smtp]\nport = 465    # implicit TLS\n"
        out = tomlwrite.set_value(src, "channels.smtp", "port", 587)
        self.assertIn("port = 587", out)
        self.assertIn("# implicit TLS", out)
        self.assertEqual(tomllib.loads(out)["channels"]["smtp"]["port"], 587)

    def test_revives_commented_key_in_place(self):
        src = "[triggers]\ncooldown_sec = 60\n# stop_min_duration_sec = 300    # opt-in\n"
        out = tomlwrite.set_value(src, "triggers", "stop_min_duration_sec", 120)
        self.assertIn("stop_min_duration_sec = 120", out)
        self.assertNotIn("# stop_min_duration_sec", out)
        self.assertIn("# opt-in", out)  # the explanation survives
        # and it stays where it was documented, right after cooldown
        lines = [ln for ln in out.splitlines() if ln.strip()]
        self.assertEqual(lines.index("stop_min_duration_sec = 120  # opt-in"), 2)

    def test_appends_to_existing_section_before_blank_tail(self):
        src = '[channels.discord]\n# a comment\n\n[channels.smtp]\nhost = "a"\n'
        out = tomlwrite.set_value(src, "channels.discord", "webhook_url", "https://x")
        data = tomllib.loads(out)
        self.assertEqual(data["channels"]["discord"]["webhook_url"], "https://x")
        self.assertEqual(data["channels"]["smtp"]["host"], "a")

    def test_creates_missing_section(self):
        out = tomlwrite.set_value('machine = "box"\n', "channels.smtp", "port", 465)
        data = tomllib.loads(out)
        self.assertEqual(data["machine"], "box")
        self.assertEqual(data["channels"]["smtp"]["port"], 465)

    def test_root_key_on_empty_file(self):
        out = tomlwrite.set_value("", "", "machine", "box-a")
        self.assertEqual(tomllib.loads(out)["machine"], "box-a")

    def test_comment_preserved_across_whole_file(self):
        src = (
            "# header comment\n"
            'machine = "old"\n'
            "\n"
            "[triggers]\n"
            "# explanation\n"
            "cooldown_sec = 60\n"
        )
        out = tomlwrite.set_value(src, "", "machine", "new")
        self.assertIn("# header comment", out)
        self.assertIn("# explanation", out)
        self.assertIn('machine = "new"', out)

    def test_escapes_strings(self):
        out = tomlwrite.set_value("", "", "machine", 'a"b\\c')
        self.assertEqual(tomllib.loads(out)["machine"], 'a"b\\c')

    def test_list_value(self):
        out = tomlwrite.set_value("[routing]\n", "routing", "failed", ["discord", "smtp"])
        self.assertEqual(tomllib.loads(out)["routing"]["failed"], ["discord", "smtp"])


class SplitComment(unittest.TestCase):
    def test_hash_inside_string_is_not_a_comment(self):
        value, comment = tomlwrite.split_comment('"a#b"  # a real comment')
        self.assertEqual(value, '"a#b"')
        self.assertEqual(comment, "# a real comment")

    def test_no_comment(self):
        self.assertEqual(tomlwrite.split_comment("465"), ("465", ""))


class Unset(unittest.TestCase):
    def test_removes_active_key_only(self):
        src = "[triggers]\ncooldown_sec = 60\n# cooldown_sec = 999\n"
        out, removed = tomlwrite.unset(src, "triggers", "cooldown_sec")
        self.assertTrue(removed)
        self.assertNotIn("cooldown_sec = 60", out)
        self.assertIn("# cooldown_sec = 999", out)

    def test_missing_key_is_noop(self):
        _, removed = tomlwrite.unset("[triggers]\n", "triggers", "cooldown_sec")
        self.assertFalse(removed)


if __name__ == "__main__":
    unittest.main()

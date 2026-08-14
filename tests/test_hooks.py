"""Hook wiring and entry point.

Two properties matter more than the rest and are pinned here.

1. `SessionStart` is registered **always**, regardless of `--events`. Without it
   notifications lose the project name.
2. The entry point exits 0 **no matter what**. Exit 2 blocks the session.
"""

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mailo import hooks


class Wiring(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "settings.json"
        patcher = mock.patch.object(hooks, "settings_path", return_value=self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def _read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_session_start_always_registered(self):
        _, installed = hooks.install("user", events=["failed"])
        self.assertIn("SessionStart", installed)
        self.assertIn("StopFailure", installed)

    def test_uses_exec_form_and_async(self):
        hooks.install("user")
        entry = self._read()["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertEqual(entry["command"], "mailo")
        self.assertEqual(entry["args"], ["hook"])
        self.assertTrue(entry["async"])
        self.assertIn("timeout", entry)

    def test_foreign_hooks_are_preserved(self):
        self.path.write_text(
            json.dumps(
                {
                    "model": "opus",
                    "hooks": {
                        "SessionStart": [
                            {"matcher": "*", "hooks": [{"type": "command", "command": "other"}]}
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        hooks.install("user")
        data = self._read()
        self.assertEqual(data["model"], "opus")
        commands = [
            h["command"] for e in data["hooks"]["SessionStart"] for h in e["hooks"]
        ]
        self.assertIn("other", commands)
        self.assertIn("mailo", commands)

    def test_install_is_idempotent(self):
        hooks.install("user")
        hooks.install("user")
        self.assertEqual(len(self._read()["hooks"]["SessionStart"]), 1)

    def test_narrowing_events_removes_stale_mailo_hooks(self):
        hooks.install("user")                      # everything
        hooks.install("user", events=["blocked"])  # narrower, re-registered
        names = set(self._read()["hooks"])
        # StopFailure/SessionEnd from the earlier install must not keep firing.
        self.assertEqual(names, {"SessionStart", "Notification"})

    def test_uninstall_removes_only_mailo(self):
        self.path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionEnd": [
                            {"matcher": "*", "hooks": [{"type": "command", "command": "other"}]}
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        hooks.install("user")
        _, removed = hooks.uninstall("user")
        self.assertGreater(removed, 0)
        data = self._read()
        self.assertEqual(data["hooks"]["SessionEnd"][0]["hooks"][0]["command"], "other")


class Entrypoint(unittest.TestCase):
    """Whatever goes in, 0 comes out."""

    def _run(self, payload):
        with mock.patch("sys.stdin", io.StringIO(payload)):
            return hooks.run()

    def test_empty_input(self):
        self.assertEqual(self._run(""), 0)

    def test_malformed_json(self):
        self.assertEqual(self._run("{not json"), 0)

    def test_unknown_hook(self):
        self.assertEqual(self._run(json.dumps({"hook_event_name": "Whatever"})), 0)

    def test_exception_inside_is_swallowed(self):
        with mock.patch.object(hooks, "_handle", side_effect=RuntimeError("boom")):
            self.assertEqual(self._run(json.dumps({"hook_event_name": "SessionEnd"})), 0)

    def test_session_start_caches_cwd_and_sends_nothing(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.environ["XDG_STATE_HOME"] = tmp.name
        try:
            with mock.patch("mailo.notify.dispatch") as dispatch:
                code = self._run(
                    json.dumps(
                        {
                            "hook_event_name": "SessionStart",
                            "session_id": "s1",
                            "cwd": "/home/you/work/exp-042",
                        }
                    )
                )
            self.assertEqual(code, 0)
            dispatch.assert_not_called()

            from mailo import state

            self.assertEqual(state.recall_cwd("s1"), "/home/you/work/exp-042")
        finally:
            os.environ.pop("XDG_STATE_HOME", None)


class EventMapping(unittest.TestCase):
    def test_notification_types(self):
        from mailo.events import Event

        cases = {
            "permission_prompt": Event.BLOCKED,
            "agent_needs_input": Event.BLOCKED,
            "idle_prompt": Event.BLOCKED,
            "agent_completed": Event.DONE,
        }
        for kind, expected in cases.items():
            got = hooks._resolve_event("Notification", {"notification_type": kind})
            self.assertEqual(got, expected, kind)

    def test_session_start_maps_to_no_event(self):
        self.assertIsNone(hooks._HOOK_EVENTS["SessionStart"])


if __name__ == "__main__":
    unittest.main()

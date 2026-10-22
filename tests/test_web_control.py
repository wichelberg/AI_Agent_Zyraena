"""web_control: the video controls moved from the old shortcut extension into Zyraena Web Control,
and the checks that keep the extension from ever failing silently again (2026-10-20: Opera still
loaded the old video extension from a folder that had moved, so its shortcuts did nothing).

No browser: the extension's replies are fakes; Opera's Secure Preferences are written to a temp folder.
Run from the project folder: python -m unittest discover -s tests
"""
import base64
import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import web_control as wc  # noqa: E402


def extension_id(key_b64):
    """Chromium's ID for an unpacked extension with this manifest key: sha256 of the key, 32 hex
    digits written with the letters a-p."""
    digest = hashlib.sha256(base64.b64decode(key_b64)).hexdigest()[:32]
    return "".join(chr(ord("a") + int(c, 16)) for c in digest)


class TheRealExtensionTest(unittest.TestCase):
    """The extension project on this PC matches what Zyraena expects."""

    def setUp(self):
        if not (wc.EXTENSION_DIR / "manifest.json").is_file():
            self.fail(f"the extension's folder is missing: {wc.EXTENSION_DIR}")
        self.manifest = json.loads((wc.EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.background = (wc.EXTENSION_DIR / "background.js").read_text(encoding="utf-8")

    def test_its_key_gives_the_id_zyraena_accepts(self):
        self.assertEqual(extension_id(self.manifest["key"]), wc.EXTENSION_ID)

    def test_its_version_has_the_video_command(self):
        self.assertGreaterEqual(wc._version(self.manifest["version"]), wc.MIN_EXTENSION_VERSION)
        self.assertRegex(self.background, r"\n  video: async")
        self.assertIn('world: "MAIN"', self.background)

    def test_same_port(self):
        self.assertEqual(int(re.search(r"const PORT = (\d+)", self.background).group(1)), wc.PORT)

    def test_nothing_evaluates_code_from_the_socket(self):
        self.assertNotRegex(self.background, r"\beval\(|new Function\(")


class NoShortcutsLeftTest(unittest.TestCase):
    def test_the_old_video_extension_and_its_keys_are_gone(self):
        self.assertFalse((ROOT / "extensions" / "video-loop").exists())
        source = (ROOT / "browser_tools.py").read_text(encoding="utf-8")
        for old in ("VIDEO_KEYS", "VOLUME_KEYS", "LOOP_MARK", "set_video_volume", "control_browser", "Key.alt"):
            self.assertNotIn(old, source)

    def test_the_assistant_offers_control_video_only(self):
        source = (ROOT / "ai_assistant.py").read_text(encoding="utf-8")
        self.assertIn("web_control.TOOL_FUNCTIONS", source)
        self.assertIn("control_video", wc.TOOL_FUNCTIONS)
        names = [t["function"]["name"] for t in wc.TOOLS]
        self.assertIn("control_video", names)


class Folder(unittest.TestCase):
    """A stand-in extension folder and an empty link."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.ext = self.root / "Web_ControlExtention"
        self.ext.mkdir()
        (self.ext / "manifest.json").write_text("{}", encoding="utf-8")
        for patcher in (mock.patch.object(wc, "EXTENSION_DIR", self.ext),
                        mock.patch.dict(wc._link, {"ws": None, "version": None})):
            patcher.start()
            self.addCleanup(patcher.stop)


class ProblemTest(Folder):
    def problem(self, registered, **kwargs):
        return wc.problem("en", registered=registered, **kwargs)

    def test_all_well(self):
        self.assertIsNone(self.problem({wc.EXTENSION_ID: str(self.ext)}))

    def test_not_loaded_in_opera(self):
        self.assertIn("isn't loaded", self.problem({}))

    def test_loaded_from_a_folder_that_moved(self):  # what happened on 2026-10-20
        old = str(self.root / "Zyraena" / "extensions" / "Web_ControlExtention")
        text = self.problem({wc.EXTENSION_ID: old})
        self.assertIn(old, text)
        self.assertIn("doesn't exist any more", text)

    def test_loaded_from_another_copy(self):
        copy = self.root / "copy"
        copy.mkdir()
        self.assertIn("not from", self.problem({wc.EXTENSION_ID: str(copy)}))

    def test_our_folder_missing(self):
        (self.ext / "manifest.json").unlink()
        self.assertIn("is missing", self.problem({wc.EXTENSION_ID: str(self.ext)}))

    def test_old_copy_running(self):
        wc._link.update(ws=object(), version="1.1")
        self.assertIn("old copy", self.problem({wc.EXTENSION_ID: str(self.ext)}))
        wc._link["version"] = "1.2"
        self.assertIsNone(self.problem({wc.EXTENSION_ID: str(self.ext)}))

    def test_not_connecting_while_opera_runs(self):
        ok = {wc.EXTENSION_ID: str(self.ext)}
        self.assertIsNone(self.problem(ok, opera_running=True, waiting_seconds=60))
        self.assertIn("hasn't connected", self.problem(ok, opera_running=True,
                                                       waiting_seconds=wc.CONNECT_GRACE_SECONDS))
        self.assertIsNone(self.problem(ok, opera_running=False, waiting_seconds=600))

    def test_other_extensions_with_a_gone_folder(self):  # the old video extension left in Opera
        gone = str(self.root / "Zyraena" / "extensions" / "video-loop")
        text = self.problem({wc.EXTENSION_ID: str(self.ext), "nlmibifakakihhanelnjegcmcdjdkdel": gone})
        self.assertIn(gone, text)

    def test_unreadable_opera_profile_checks_the_rest(self):
        self.assertIsNone(self.problem(None))

    def test_in_turkish_for_the_owner(self):
        self.assertIn("yüklü değil", wc.problem("tr", registered={}))


class OperaPreferencesTest(unittest.TestCase):
    def test_reads_unpacked_extensions_from_opsettings(self):
        with tempfile.TemporaryDirectory() as folder:
            prefs = {"extensions": {"opsettings": {
                wc.EXTENSION_ID: {"location": 4, "path": r"C:\x\Web_ControlExtention"},
                "store": {"location": 1, "path": "abc"},
            }}}
            (Path(folder) / "Secure Preferences").write_text(json.dumps(prefs), encoding="utf-8")
            self.assertEqual(wc.opera_extensions(folder), {wc.EXTENSION_ID: r"C:\x\Web_ControlExtention"})

    def test_none_without_a_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(wc.opera_extensions(folder))


class WatchTest(Folder):
    def test_tells_once_per_problem_and_again_after_it_came_back(self):
        told, state = [], {"told": None, "waiting_since": None}

        def step(registered, now=100.0):
            wc._watch_step(state, False, now, told.append, "en", registered=registered)

        broken, fine = {}, {wc.EXTENSION_ID: str(self.ext)}
        step(broken)
        step(broken)
        self.assertEqual(len(told), 1)
        step(fine)
        step(broken)
        self.assertEqual(len(told), 2)

    def test_counts_the_wait_while_opera_runs(self):
        told, state = [], {"told": None, "waiting_since": None}
        fine = {wc.EXTENSION_ID: str(self.ext)}
        for now in (100.0, 160.0, 100.0 + wc.CONNECT_GRACE_SECONDS):
            wc._watch_step(state, True, now, told.append, "en", registered=fine)
        self.assertEqual(len(told), 1)
        self.assertIn("hasn't connected", told[0])


class ControlVideoTest(Folder):
    def setUp(self):
        super().setUp()
        wc._link.update(ws=object(), version="1.2")
        self.calls = []
        self.tabs = [
            {"id": 1, "title": "Docs", "url": "https://docs.example", "focused": True, "audible": False},
            {"id": 2, "title": "Lofi - YouTube", "url": "https://www.youtube.com/watch?v=x", "focused": False,
             "audible": True},
        ]
        self.videos = {2: {"found": True, "youtube": True, "loop": False, "volume": 50, "muted": False,
                           "paused": False}}

        def call(cmd, wait=wc.CALL_SECONDS, **args):
            self.calls.append((cmd, args))
            if cmd == "tabs":
                return self.tabs
            if cmd == "tab":
                return next(t for t in self.tabs if t["id"] == args["tab"])
            if cmd == "video":
                video = self.videos.get(args["tab"])
                if video is None:
                    return {"found": False}
                if args["action"] == "loop":
                    video["loop"] = (not video["loop"]) if args["on"] is None else args["on"]
                if args["action"] == "volume":
                    video["volume"] = args["volume"]
                return dict(video)
            raise AssertionError(cmd)

        for patcher in (mock.patch.object(wc, "_call", side_effect=call),
                        mock.patch.object(wc, "_ask", side_effect=AssertionError("video controls aren't asked"))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_loop_finds_the_tab_playing_sound_without_asking(self):
        answer = wc.control_video("loop")
        self.assertIn("loop ON", answer)
        self.assertIn("[2]", answer)
        self.assertEqual([c for c, _ in self.calls], ["tabs", "video", "video"])  # front tab had no video

    def test_loop_on_and_off_are_explicit(self):
        wc.control_video("loop_on")
        wc.control_video("loop_on")
        self.assertTrue(self.videos[2]["loop"])
        self.assertIn("loop off", wc.control_video("loop_off"))

    def test_volume_is_clamped_and_needs_a_number(self):
        self.assertIn("volume 100%", wc.control_video("volume", percent=180))
        self.assertIn("percent", wc.control_video("volume"))

    def test_a_given_tab(self):
        wc.control_video("state", tab_id=2)
        self.assertEqual(self.calls[0], ("tab", {"tab": 2}))

    def test_no_video_anywhere(self):
        self.videos.clear()
        self.assertIn("No video found", wc.control_video("mute"))

    def test_an_old_extension_is_named(self):
        wc._link["version"] = "1.1"
        with mock.patch.object(wc, "opera_extensions", return_value={wc.EXTENSION_ID: str(self.ext)}):
            self.assertIn("old copy", wc.control_video("loop"))
        self.assertEqual(self.calls, [])

    def test_unknown_action(self):
        self.assertIn("Unknown action", wc.control_video("rewind"))

    def test_fullscreen_is_youtubes_own_key(self):
        with mock.patch("browser_tools.press_fullscreen", return_value="pressed f") as press:
            self.assertEqual(wc.control_video("fullscreen"), "pressed f")
        press.assert_called_once()
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()

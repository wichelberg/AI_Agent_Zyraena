"""paths: what Zyraena drops from an environment inherited from VS Code, so the apps she
launches (VS Code above all) start normally.

Run from the project folder: python -m unittest discover -s tests
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import paths  # noqa: E402


class DropEditorEnvTest(unittest.TestCase):
    def test_drops_extension_host_vars_and_keeps_the_rest(self):
        inherited = {"ELECTRON_RUN_AS_NODE": "1", "VSCODE_PID": "26460", "VSCODE_IPC_HOOK": r"\\.\pipe\x",
                     "ZYRAENA_TTS_IDLE_MINUTES": "10", "PATH": os.environ.get("PATH", "")}
        with mock.patch.dict(os.environ, inherited, clear=True):
            paths.drop_editor_env()
            self.assertEqual(set(os.environ), {"ZYRAENA_TTS_IDLE_MINUTES", "PATH"})


if __name__ == "__main__":
    unittest.main()

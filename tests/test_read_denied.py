"""Unreadable inputs are controlled CLI errors when permissions are enforceable."""

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


class ReadDeniedTests(unittest.TestCase):
    @unittest.skipIf(os.name != "posix", "requires POSIX file permission bits")
    def test_denied_file_is_a_controlled_error(self):
        with tempfile.TemporaryDirectory() as directory:
            denied = Path(directory) / "unreadable.env"
            readable = Path(directory) / "readable.env"
            denied.write_text("PORT=8080\n", encoding="utf-8")
            readable.write_text("PORT=8080\n", encoding="utf-8")
            original_mode = stat.S_IMODE(denied.stat().st_mode)
            try:
                denied.chmod(0)
                # Root, capabilities and some filesystems bypass mode bits.
                try:
                    denied.read_bytes()
                except PermissionError:
                    pass
                else:
                    self.skipTest(
                        "this user/filesystem does not enforce read mode bits"
                    )
                for args in ((denied, readable), (readable, denied)):
                    with self.subTest(denied_argument=str(args.index(denied))):
                        proc = subprocess.run(
                            [
                                sys.executable,
                                str(APP),
                                "diff",
                                *map(str, args),
                                "--json",
                            ],
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            timeout=10,
                        )
                        self.assertEqual(proc.returncode, 2, proc.stderr)
                        self.assertEqual(proc.stdout, "")
                        self.assertTrue(proc.stderr.startswith("error:"), proc.stderr)
                        self.assertIn("unreadable.env", proc.stderr)
                        self.assertNotIn("Traceback", proc.stderr)
            finally:
                denied.chmod(original_mode)

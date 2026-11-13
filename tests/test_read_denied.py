"""Permission failure handling without relying on POSIX chmod semantics."""

import importlib.util
import os
import unittest
from unittest.mock import patch


class ReadDeniedTests(unittest.TestCase):
    def test_denied_file_is_a_controlled_error(self):
        source = os.path.join(os.path.dirname(__file__), "..", "src", "dotenv_manager.py")
        spec = importlib.util.spec_from_file_location("dotenv_read_denied", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch("builtins.open", side_effect=PermissionError(13, "access denied")):
            with self.assertRaises(module.DotenvError):
                module.parse_env_file("unreadable.env")

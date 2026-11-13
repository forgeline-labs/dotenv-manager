#!/usr/bin/env python3
"""Portable entry point for the stdlib dotenv CLI."""
import os
import sys

for stream in (sys.stdin, sys.stdout, sys.stderr):
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", newline="\n")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from dotenv_manager import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

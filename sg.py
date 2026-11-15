#!/usr/bin/env python3
"""Entry point:  python sg.py <command>   (see README.md)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from specgraph.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

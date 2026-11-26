#!/usr/bin/env python3
"""Deliver the committed front page for make.fun news-image-20261125.

The image itself lives in this repository as entry.png (drawn from the
sources named in SOURCES.md). This program does one thing: it copies that
file to /output/entry.png byte for byte, so the two grading runs produce
identical output. It needs no network, no fonts and no image library.
"""

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGE = HERE / "entry.png"


def pick_target() -> Path:
    """Prefer /output/entry.png; fall back to ./output/entry.png."""
    root = Path("/output")
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        root = Path.cwd() / "output"
        root.mkdir(parents=True, exist_ok=True)
    return root / "entry.png"


def main() -> None:
    shutil.copyfile(IMAGE, pick_target())


if __name__ == "__main__":
    main()

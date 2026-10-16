#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build PixelRPG.exe — runs the headless self-test first, then PyInstaller.

Usage:  python build_exe.py
Output: dist/PixelRPG.exe
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE / "game.py"
NAME = "PixelRPG"
MODULES = ("art", "sprites", "items", "skills", "sounds", "world", "render", "selftest")


def run_selftest() -> None:
    print("== self-test ==", flush=True)
    result = subprocess.run([sys.executable, str(GAME), "--selftest"],
                            cwd=HERE, capture_output=True, text=True)
    print(result.stdout.strip())
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        raise SystemExit("self-test failed — build aborted")


def build() -> None:
    print("\n== pyinstaller ==", flush=True)
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        raise SystemExit("PyInstaller is missing: pip install -r requirements.txt")

    args = [
        str(GAME),
        "--name", NAME,
        "--onefile",          # single portable .exe
        "--noconsole",        # game window, no terminal
        "--noconfirm",
        "--clean",
        "--distpath", str(HERE / "dist"),
        "--workpath", str(HERE / "build"),
        "--specpath", str(HERE),
    ]
    for module in MODULES:
        args += ["--hidden-import", module]
    pyi.run(args)
    exe = HERE / "dist" / f"{NAME}.exe"
    if not exe.exists():
        raise SystemExit("build finished but the .exe is missing")
    print(f"\nOK -> {exe}  ({exe.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    run_selftest()
    build()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build PixelPatch.exe — runs the headless self-test first, then PyInstaller.

Usage:  python build_exe.py
Output: dist/PixelPatch.exe
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE / "game.py"
NAME = "PixelPatch"
MODULES = ("art", "sprites", "items", "skills", "sounds", "music", "quests", "world",
           "render", "selftest", "packart", "ui")
ASSETS = HERE / "assets"        # Ninja Adventure sprite sheets (CC0)
FONTS = HERE / "assets" / "fonts"  # Pixelify Sans + Press Start 2P (OFL)
RES = HERE / "resources"        # иконка для .exe


def run_selftest() -> None:
    print("== self-test ==", flush=True)
    result = subprocess.run([sys.executable, str(GAME), "--selftest"],
                            cwd=HERE, capture_output=True, text=True)
    print(result.stdout.strip())
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        raise SystemExit("self-test failed — build aborted")


def verify_exe(exe: Path) -> None:
    """Прогнать selftest уже собранным .exe: шрифты, numpy и assets должны
    быть внутри. Иначе сборка «успешна», а игра падает на запуске."""
    print("\n== проверка собранного .exe ==", flush=True)
    marker = Path(os.environ.get("TEMP", ".")) / "pixelrpg_selftest_exit.txt"
    try:
        marker.unlink()
    except OSError:
        pass
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    proc = subprocess.run([str(exe), "--selftest"], cwd=HERE, env=env,
                          capture_output=True, timeout=600)
    report = Path(os.environ.get("TEMP", ".")) / "pixelrpg_selftest.txt"
    code = None
    try:
        code = int(marker.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pass
    text = report.read_text(encoding="utf-8") if report.exists() else ""
    tail = [ln for ln in text.strip().splitlines() if ln.startswith("SELFTEST") or ln.startswith("  -")]
    print("  exit:", code, "|", "; ".join(tail) or "(отчёт не найден)")
    if code != 0:
        print(proc.stdout[-2000:].decode("utf-8", "replace"))
        print(proc.stderr[-2000:].decode("utf-8", "replace"), file=sys.stderr)
        raise SystemExit("собранный .exe не проходит selftest")


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
    if ASSETS.is_dir():
        sep = ";" if os.name == "nt" else ":"
        args += ["--add-data", f"{ASSETS}{sep}assets"]
    if RES.is_dir():
        ico = RES / "icon.ico"
        if ico.exists():
            args += ["--icon", str(ico)]
        ver = RES / "version_info.txt"
        if ver.exists():
            args += ["--version-file", str(ver)]
    # numpy тянет за собой бинарные расширения — без явного сбора
    # PyInstaller кладёт только те подмодули, которые увидел в импортах
    args += ["--collect-submodules", "numpy", "--hidden-import", "numpy"]
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
    verify_exe(HERE / "dist" / f"{NAME}.exe")

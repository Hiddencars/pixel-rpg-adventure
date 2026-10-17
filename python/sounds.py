#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Procedural sound effects for Pixel patch (stdlib + pygame only).

Effects are synthesised at runtime as ``list[float]`` buffers in [-1, 1] at
``SAMPLE_RATE``, converted to 16-bit signed PCM and wrapped with
``pygame.mixer.Sound(buffer=...)``.  No numpy, no asset files.

If pygame is missing or ``pygame.mixer.init()`` fails (headless box, no audio
device, ``SDL_AUDIODRIVER=dummy``) every ``play()`` is a silent no-op and never
raises.  ``python sounds.py`` dumps each effect to %TEMP%/pixelrpg_sfx/*.wav
and prints a name / duration / peak table.
"""

from __future__ import annotations

import array
import math
import os
import random
import sys
import wave
from typing import Any, Callable

try:                                      # pragma: no cover - env dependent
    import pygame
except Exception:                         # pragma: no cover
    pygame = None

SAMPLE_RATE = 44100
TWO_PI = 2.0 * math.pi

REQUIRED_NAMES: tuple[str, ...] = (
    "swing", "hit", "hit_metal", "hit_magic", "enemy_die", "boss_die",
    "player_hurt", "player_die", "pickup", "coin", "potion", "eat",
    "level_up", "skill_learn", "quest_done", "menu_move", "menu_select",
    "dialog", "footstep", "sell", "buy", "error", "door", "spell", "arrow",
    "fire", "howl", "spider", "skeleton", "ghost", "troll", "stun", "dodge",
    "heal", "chest",
)
MIN_DUR, MAX_DUR = 0.05, 0.9
MIN_PEAK, MAX_PEAK = 0.4, 0.9

# ---------------------------------------------------------------------------
# Synth layer: oscillators, noise, envelopes, filters, mixing
# ---------------------------------------------------------------------------
def _n(dur: float) -> int:
    """Sample count for a duration in seconds (at least one sample)."""
    return max(1, int(dur * SAMPLE_RATE))

def _blank(dur: float) -> list[float]:
    return [0.0] * _n(dur)

def _osc(n: int, f0: float, f1: float | None = None, kind: str = "sine") -> list[float]:
    """Oscillator, linear sweep f0 -> f1; kind is sine/square/saw/tri."""
    f1 = f0 if f1 is None else f1
    out, ph, step = [0.0] * n, 0.0, 1.0 / max(1, n - 1)
    for i in range(n):
        ph += TWO_PI * (f0 + (f1 - f0) * i * step) / SAMPLE_RATE
        p = (ph / TWO_PI) % 1.0
        if kind == "sine":
            out[i] = math.sin(ph)
        elif kind == "square":
            out[i] = 1.0 if math.sin(ph) >= 0.0 else -1.0
        elif kind == "saw":
            out[i] = 2.0 * p - 1.0
        else:
            out[i] = 4.0 * abs(p - 0.5) - 1.0        # triangle
    return out

def _noise(n: int, rng: random.Random, lp: float = 0.0) -> list[float]:
    """White noise, optionally lowpassed."""
    out = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    return _lp(out, lp) if lp else out

def _decay(n: int, tau: float) -> list[float]:
    """Exponential decay envelope (tau in seconds)."""
    k = 1.0 / max(1e-4, tau * SAMPLE_RATE)
    return [math.exp(-i * k) for i in range(n)]

def _adsr(n: int, a: float = 0.005, d: float = 0.06, s: float = 0.5,
          r: float = 0.06) -> list[float]:
    """ADSR envelope rescaled to fit exactly n samples."""
    ea, ed, er = a * SAMPLE_RATE, d * SAMPLE_RATE, r * SAMPLE_RATE
    span = ea + ed + er
    if span > n:
        ea, ed, er = ea * n / span, ed * n / span, er * n / span
    out: list[float] = [j / ea for j in range(int(ea))]
    out += [1.0 - (1.0 - s) * (j / ed) for j in range(int(ed))]
    out += [s] * max(0, int(n - ea - ed - er))
    out += [s * (1.0 - j / er) for j in range(int(er))]
    return out + [0.0] * (n - len(out))

def _lp(buf: list[float], cutoff: float) -> list[float]:
    """One-pole lowpass."""
    if cutoff <= 0.0 or cutoff >= SAMPLE_RATE / 2.0:
        return list(buf)
    a, y, out = 1.0 - math.exp(-TWO_PI * cutoff / SAMPLE_RATE), 0.0, [0.0] * len(buf)
    for i, x in enumerate(buf):
        y += a * (x - y)
        out[i] = y
    return out

def _hp(buf: list[float], cutoff: float) -> list[float]:
    """Complementary one-pole highpass."""
    return [x - y for x, y in zip(buf, _lp(buf, cutoff))]

def _mul(buf: list[float], other: list[float]) -> list[float]:
    """Element-wise product, zero-padded to the longer of the two."""
    n = max(len(buf), len(other))
    return [(buf[i] if i < len(buf) else 0.0) * (other[i] if i < len(other) else 0.0)
            for i in range(n)]

def _mix(*bufs: list[float]) -> list[float]:
    out = [0.0] * max((len(b) for b in bufs), default=0)
    for b in bufs:
        for i, v in enumerate(b):
            out[i] += v
    return out

def _gain(buf: list[float], g: float) -> list[float]:
    return [v * g for v in buf]

def _cat(*bufs: list[float]) -> list[float]:
    out: list[float] = []
    for b in bufs:
        out += b
    return out

def _overlap(parts: list[list[float]], step: int, total: int | None = None) -> list[float]:
    """Sum parts, each starting `step` samples after the previous one."""
    total = (len(parts) - 1) * step + len(parts[-1]) if total is None else total
    out = [0.0] * total
    for k, p in enumerate(parts):
        for i, v in enumerate(p[:max(0, total - k * step)]):
            out[k * step + i] += v
    return out

def _norm(buf: list[float], peak: float = 0.65) -> list[float]:
    """Scale so the absolute peak equals `peak` (never clips)."""
    m = max((abs(v) for v in buf), default=0.0)
    return _gain(buf, peak / m) if m > 1e-9 else list(buf)

def _tone(dur: float, f0: float, f1: float | None = None, kind: str = "sine",
          attack: float = 0.005, tau: float = 0.08) -> list[float]:
    """One tone: short attack, exponential decay."""
    n, at = _n(dur), max(1, int(attack * SAMPLE_RATE))
    o, d = _osc(n, f0, f1, kind), _decay(n, tau)
    return [o[i] * d[i] * (i / at if i < at else 1.0) for i in range(n)]

def _bell(n: int, freqs: tuple[float, ...], amps: tuple[float, ...],
          tau: float, attack: float = 0.003) -> list[float]:
    """Additive partial stack; higher partials decay faster."""
    out, at = [0.0] * n, max(1, int(attack * SAMPLE_RATE))
    for f, a in zip(freqs, amps):
        o, d = _osc(n, f), _decay(n, tau * (900.0 / max(200.0, f)) ** 0.4)
        for i in range(n):
            out[i] += a * o[i] * d[i] * (i / at if i < at else 1.0)
    return out

def _resample(buf: list[float], src: int, dst: int) -> list[float]:
    """Linear resample, used when the live mixer rate differs from ours."""
    if src == dst or not buf:
        return list(buf)
    n, last, out = max(1, int(len(buf) * dst / src)), len(buf) - 1, []
    for i in range(n):
        p, i0 = i * src / dst, int(i * src / dst)
        if i0 >= last:
            out.append(buf[last])
        else:
            out.append(buf[i0] + (buf[i0 + 1] - buf[i0]) * (p - i0))
    return out

def _pcm(buf: list[float], channels: int = 1) -> bytes:
    """16-bit signed little-endian PCM, interleaved for `channels`."""
    a = array.array("h")
    for v in buf:
        s = int(v * 32767.0)
        s = 32767 if s > 32767 else (-32768 if s < -32768 else s)
        for _ in range(channels):
            a.append(s)
    if sys.byteorder == "big":                # pragma: no cover
        a.byteswap()
    return a.tobytes()

# ---------------------------------------------------------------------------
# One short function per effect
# ---------------------------------------------------------------------------
def _swing(r):
    n = _n(0.28)
    body = _hp(_mix(_gain(_noise(n, r, 5000), 0.9), _gain(_osc(n, 1200, 240, "saw"), 0.5)), 300)
    return _norm(_mul(body, _adsr(n, 0.010, 0.09, 0.30, 0.16)), 0.68)

def _hit(r):
    n = _n(0.18)
    thud = _mul(_osc(n, 150, 55, "sine"), _decay(n, 0.055))
    return _norm(_mix(thud, _gain(_mul(_noise(n, r, 2200), _decay(n, 0.030)), 0.55)), 0.72)

def _hit_metal(r):
    n = _n(0.34)
    metal = _bell(n, (523.0, 742.0, 1103.0, 1621.0, 2411.0), (1.0, 0.7, 0.55, 0.4, 0.22), 0.11)
    return _norm(_mix(metal, _gain(_mul(_noise(n, r, 8000), _decay(n, 0.008)), 0.35)), 0.70)

def _hit_magic(r):
    n = _n(0.40)
    chime = _bell(n, (680.0, 1020.0, 1530.0, 2040.0), (1.0, 0.6, 0.45, 0.25), 0.16)
    shimmer = _mul(_noise(n, r, 6000), _decay(n, 0.12))
    rise = _mul(_osc(n, 400, 1200, "sine"), _adsr(n, 0.01, 0.06, 0.4, 0.2))
    return _norm(_mix(chime, _gain(shimmer, 0.4), _gain(rise, 0.3)), 0.66)

def _enemy_die(r):
    n = _n(0.50)
    fall = _mul(_osc(n, 420, 110, "square"), _adsr(n, 0.008, 0.12, 0.35, 0.3))
    return _norm(_mix(_gain(fall, 0.6), _gain(_mul(_noise(n, r, 3500), _decay(n, 0.09)), 0.5)), 0.70)

def _boss_die(r):
    n, tail = _n(0.85), _n(0.30)
    low = _mul(_osc(n, 210, 42, "saw"), _adsr(n, 0.02, 0.30, 0.35, 0.40))
    rumble = _mul(_noise(n, r, 180), _decay(n, 0.5))
    boom = _cat(_blank(n / SAMPLE_RATE - 0.30), _mul(_osc(tail, 90, 40, "sine"), _decay(tail, 0.12)))
    return _norm(_mix(_gain(low, 0.8), _gain(rumble, 0.7), _gain(boom, 0.5)), 0.74)

def _player_hurt(r):
    n = _n(0.24)
    cry = _mul(_osc(n, 560, 190, "square"), _decay(n, 0.07))
    return _norm(_mix(_gain(cry, 0.7), _gain(_mul(_noise(n, r, 4000), _decay(n, 0.04)), 0.55)), 0.70)

def _player_die(r):
    n = _n(0.90)
    vib = [1.0 + 0.03 * math.sin(TWO_PI * 6.0 * i / SAMPLE_RATE) for i in range(n)]
    fall = _mul(_mul(_osc(n, 360, 70, "saw"), vib), _adsr(n, 0.03, 0.40, 0.40, 0.35))
    return _norm(_mix(_gain(fall, 0.75), _gain(_mul(_noise(n, r, 900), _decay(n, 0.45)), 0.45)), 0.72)

def _pickup(r):
    return _norm(_cat(_tone(0.07, 700, 880, "sine", 0.004, 0.06),
                      _tone(0.08, 1050, 1320, "sine", 0.004, 0.07)), 0.66)

def _coin(r):
    return _norm(_cat(_bell(_n(0.06), (1320.0, 2640.0), (1.0, 0.30), 0.045),
                      _bell(_n(0.09), (1980.0, 3960.0), (1.0, 0.30), 0.060)), 0.70)

def _potion(r):
    return _norm(_cat(*[_tone(d, f0, f1, "sine", 0.004, 0.07) for f0, f1, d in
                       ((420, 700, 0.07), (520, 880, 0.08), (640, 1080, 0.09))]), 0.64)

def _eat(r):
    a = _mul(_noise(_n(0.10), r, 1400), _decay(_n(0.10), 0.035))
    b = _mul(_noise(_n(0.12), r, 1100), _decay(_n(0.12), 0.045))
    return _norm(_cat(a, _blank(0.06), b), 0.60)

def _level_up(r):
    parts = [_bell(_n(0.30), (f, f * 2.0), (1.0, 0.28), 0.16)
             for f in (523.25, 659.25, 783.99, 1046.50)]
    return _norm(_overlap(parts, _n(0.14), _n(0.70)), 0.70)

def _skill_learn(r):
    body = _overlap([_bell(_n(0.26), (f, f * 2.0), (1.0, 0.25), 0.14)
                     for f in (659.25, 880.0, 1174.66)], _n(0.11))
    spark = _mul(_noise(len(body), r, 7000), _decay(len(body), 0.25))
    return _norm(_mix(body, _gain(spark, 0.25)), 0.66)

def _quest_done(r):
    lead = _overlap([_bell(_n(0.30), (f, f * 2.0), (1.0, 0.30), 0.16)
                     for f in (523.25, 659.25, 783.99)], _n(0.12))
    chord = _bell(_n(0.45), (1046.50, 1318.51, 1567.98), (1.0, 0.7, 0.5), 0.25)
    return _norm(_overlap([lead, chord], _n(0.36)), 0.72)

def _menu_move(r):
    n = _n(0.055)
    tick = _mul(_noise(n, r, 9000), _decay(n, 0.006))
    return _norm(_mix(_gain(tick, 0.7), _gain(_mul(_osc(n, 1400, 1100, "sine"), _decay(n, 0.010)), 0.8)), 0.60)

def _menu_select(r):
    return _norm(_cat(_bell(_n(0.06), (880.0, 1760.0), (1.0, 0.30), 0.045),
                      _bell(_n(0.09), (1174.66, 2349.32), (1.0, 0.30), 0.060)), 0.66)

def _dialog(r):
    return _norm(_bell(_n(0.07), (740.0, 1480.0), (1.0, 0.25), 0.030), 0.58)

def _footstep(r):
    n = _n(0.06)
    tick = _mul(_noise(n, r, 1100), _decay(n, 0.014))
    low = _gain(_mul(_osc(n, 120, 70, "sine"), _decay(n, 0.020)), 0.4)
    return _norm(_mix(tick, low), 0.55)

def _sell(r):
    return _norm(_cat(_bell(_n(0.07), (1567.98, 3135.96), (1.0, 0.28), 0.05),
                      _bell(_n(0.07), (1318.51, 2637.02), (1.0, 0.28), 0.05),
                      _bell(_n(0.10), (1046.50, 2093.0), (1.0, 0.30), 0.07)), 0.68)

def _buy(r):
    return _norm(_cat(_bell(_n(0.07), (880.0, 1760.0), (1.0, 0.28), 0.05),
                      _bell(_n(0.07), (1108.73, 2217.46), (1.0, 0.28), 0.05),
                      _bell(_n(0.10), (1318.51, 2637.02), (1.0, 0.30), 0.07)), 0.68)

def _error(r):
    n = _n(0.30)
    buzz = _mix(_osc(n, 112, 100, "square"), _gain(_osc(n, 78, 70, "square"), 0.7))
    trem = [0.55 + 0.45 * math.sin(TWO_PI * 22.0 * i / SAMPLE_RATE) for i in range(n)]
    return _norm(_lp(_mul(_mul(buzz, trem), _adsr(n, 0.006, 0.05, 0.8, 0.08)), 2200), 0.70)

def _door(r):
    n, tail, y = _n(0.85), _n(0.23), 0.0
    src, creak = _noise(n, r), [0.0] * n
    for i in range(n):
        cut = 400.0 + 1800.0 * math.sin(math.pi * min(1.0, i / n * 1.4))
        y += (1.0 - math.exp(-TWO_PI * cut / SAMPLE_RATE)) * (src[i] - y)
        creak[i] = y
    creak = _mul(_hp(creak, 400), _adsr(n, 0.05, 0.30, 0.40, 0.30))
    thump = _cat(_blank(n / SAMPLE_RATE - 0.23), _mul(_osc(tail, 110, 45, "sine"), _decay(tail, 0.08)))
    return _norm(_mix(_gain(creak, 0.6), _gain(thump, 0.9)), 0.70)

def _spell(r):
    n = _n(0.70)
    air = _mul(_lp(_noise(n, r, 0.0), 3000), _adsr(n, 0.18, 0.10, 0.55, 0.35))
    tone = _mul(_osc(n, 280, 1500, "sine"), _adsr(n, 0.25, 0.10, 0.60, 0.30))
    shimmer = _mul(_osc(n, 900, 2400, "sine"), _decay(n, 0.35))
    return _norm(_mix(_gain(air, 0.5), _gain(tone, 0.7), _gain(shimmer, 0.25)), 0.66)

def _arrow(r):
    n = _n(0.18)
    nz = _mul(_noise(n, r, 6000), _decay(n, 0.05))
    sweep = _mul(_osc(n, 2200, 700, "saw"), _decay(n, 0.06))
    return _norm(_mix(_gain(_hp(nz, 900), 0.6), _gain(sweep, 0.6)), 0.66)

def _fire(r):
    n, crack = _n(0.60), _n(0.02)
    body = list(_mul(_lp(_noise(n, r, 0.0), 900), _adsr(n, 0.12, 0.15, 0.6, 0.25)))
    for _ in range(14):
        i = r.randrange(0, max(1, n - crack))
        amp = r.uniform(0.25, 0.7) * r.choice((-1.0, 1.0))
        for j in range(crack):
            body[i + j] += amp * math.exp(-j / (0.004 * SAMPLE_RATE))
    return _norm(body, 0.64)

def _howl(r):
    n = _n(0.90)
    vib = [1.0 + 0.035 * math.sin(TWO_PI * 5.5 * i / SAMPLE_RATE) for i in range(n)]
    tone = _mix(_mul(_osc(n, 720, 380, "sine"), vib), _gain(_osc(n, 1440, 760, "sine"), 0.25))
    return _norm(_mul(tone, _adsr(n, 0.14, 0.20, 0.75, 0.35)), 0.62)

def _spider(r):
    n, tick = _n(0.25), _n(0.012)
    out = _gain(_mul(_hp(_noise(n, r, 0.0), 3000), _adsr(n, 0.01, 0.08, 0.4, 0.12)), 0.6)
    for k in range(6):
        i, sgn = _n(0.02) + k * _n(0.035), r.choice((-1.0, 1.0))
        for j in range(tick):
            if i + j < n:
                out[i + j] += 0.8 * math.exp(-j / (0.003 * SAMPLE_RATE)) * sgn
    return _norm(out, 0.60)

def _skeleton(r):
    n, click, out = _n(0.30), _n(0.05), [0.0] * _n(0.30)
    for k in range(7):
        i, f = int(k * _n(0.04)), r.choice((900.0, 1250.0, 1700.0, 2100.0))
        for j, v in enumerate(_mul(_osc(click, f, f * 0.85, "square"), _decay(click, 0.012))):
            if i + j < n:
                out[i + j] += 0.7 * v
    nz = _mul(_noise(n, r, 5000), _decay(n, 0.12))
    return _norm(_mix(out, _gain(nz, 0.25)), 0.64)

def _ghost(r):
    n = _n(0.80)
    air = _mul(_hp(_lp(_noise(n, r, 0.0), 2500), 600), _adsr(n, 0.30, 0.10, 0.70, 0.35))
    wail = _mul(_osc(n, 480, 300, "sine"), _adsr(n, 0.25, 0.15, 0.50, 0.35))
    return _norm(_mix(_gain(air, 0.7), _gain(wail, 0.4)), 0.60)

def _troll(r):
    n = _n(0.50)
    vib = [1.0 + 0.06 * math.sin(TWO_PI * 9.0 * i / SAMPLE_RATE) for i in range(n)]
    growl = _mul(_mul(_osc(n, 95, 70, "saw"), vib), _adsr(n, 0.04, 0.12, 0.60, 0.20))
    rumble = _mul(_lp(_noise(n, r, 0.0), 320), _adsr(n, 0.03, 0.10, 0.50, 0.20))
    return _norm(_mix(_gain(growl, 0.85), _gain(rumble, 0.6)), 0.72)

def _stun(r):
    n = _n(0.40)
    vib = [1.0 + 0.05 * math.sin(TWO_PI * 13.0 * i / SAMPLE_RATE) for i in range(n)]
    trem = [0.5 + 0.5 * math.sin(TWO_PI * 17.0 * i / SAMPLE_RATE) for i in range(n)]
    ring = _mul(_bell(n, (1000.0, 1500.0, 2100.0), (1.0, 0.5, 0.3), 0.20), vib)
    return _norm(_mul(ring, trem), 0.64)

def _dodge(r):
    n = _n(0.20)
    nz = _mul(_hp(_noise(n, r, 0.0), 800), _adsr(n, 0.03, 0.05, 0.40, 0.10))
    up = _mul(_osc(n, 420, 1500, "saw"), _adsr(n, 0.02, 0.05, 0.35, 0.12))
    return _norm(_mix(_gain(nz, 0.6), _gain(up, 0.6)), 0.64)

def _heal(r):
    body = _overlap([_bell(_n(0.34), (f, f * 2.0), (1.0, 0.20), 0.20)
                     for f in (523.25, 659.25, 880.0)], _n(0.13))
    air = _mul(_hp(_noise(len(body), r, 0.0), 1500), _adsr(len(body), 0.20, 0.10, 0.40, 0.30))
    return _norm(_mix(body, _gain(air, 0.15)), 0.60)

def _chest(r):
    n = _n(0.45)
    creak = _mul(_hp(_lp(_noise(n, r, 0.0), 1800), 500), _adsr(n, 0.02, 0.10, 0.35, 0.20))
    chimes = _cat(_blank(0.18), _bell(_n(0.10), (1046.50, 2093.0), (1.0, 0.30), 0.07),
                  _bell(_n(0.14), (1567.98, 3135.96), (1.0, 0.30), 0.09))
    return _norm(_mix(_gain(creak, 0.55), _gain(chimes, 0.9)), 0.70)

EFFECTS: dict[str, Callable[[random.Random], list[float]]] = {
    "swing": _swing, "hit": _hit, "hit_metal": _hit_metal, "hit_magic": _hit_magic,
    "enemy_die": _enemy_die, "boss_die": _boss_die, "player_hurt": _player_hurt,
    "player_die": _player_die, "pickup": _pickup, "coin": _coin, "potion": _potion,
    "eat": _eat, "level_up": _level_up, "skill_learn": _skill_learn,
    "quest_done": _quest_done, "menu_move": _menu_move, "menu_select": _menu_select,
    "dialog": _dialog, "footstep": _footstep, "sell": _sell, "buy": _buy,
    "error": _error, "door": _door, "spell": _spell, "arrow": _arrow, "fire": _fire,
    "howl": _howl, "spider": _spider, "skeleton": _skeleton, "ghost": _ghost,
    "troll": _troll, "stun": _stun, "dodge": _dodge, "heal": _heal, "chest": _chest,
}

def render(name: str, seed: int = 20261017) -> list[float]:
    """Float sample buffer for one effect ([] for an unknown name)."""
    fn = EFFECTS.get(name)
    return fn(random.Random(seed + (hash(name) & 0xFFFF))) if fn else []

def validate() -> list[str]:
    """Return problems found; an empty list means the bank is healthy."""
    problems: list[str] = []
    for name in REQUIRED_NAMES:
        if name not in EFFECTS:
            problems.append(f"missing effect: {name}")
            continue
        buf = render(name)
        if not buf:
            problems.append(f"{name}: empty buffer")
            continue
        dur, peak = len(buf) / SAMPLE_RATE, max(abs(v) for v in buf)
        if not (MIN_DUR <= dur <= MAX_DUR):
            problems.append(f"{name}: duration {dur:.3f}s outside {MIN_DUR}-{MAX_DUR}s")
        if not (MIN_PEAK <= peak <= MAX_PEAK):
            problems.append(f"{name}: peak {peak:.3f} outside {MIN_PEAK}-{MAX_PEAK}")
    problems += [f"unexpected extra effect: {n}" for n in EFFECTS if n not in REQUIRED_NAMES]
    return problems

def write_wav(name: str, path: str) -> str:
    """Dump one generated effect to a real mono 16-bit .wav file."""
    buf = render(name)
    if not buf:
        raise KeyError(f"unknown effect: {name}")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(_pcm(buf, 1))
    return str(path)

# ---------------------------------------------------------------------------
# Bank
# ---------------------------------------------------------------------------
def _init_mixer():
    """(freq, size, channels) of a usable 16-bit mixer, or None."""
    if pygame is None:
        return None
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=512)
        init = pygame.mixer.get_init()
        if init and init[1] == -16:
            return init
        pygame.mixer.quit()                     # unexpected format: retry once
        pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=512)
        init = pygame.mixer.get_init()
        return init if (init and init[1] == -16) else None
    except Exception:
        return None

class SoundBank:
    """Holds every synthesised effect; silently inert when audio is absent."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = bool(enabled)
        self._master = 0.8
        self._sounds: dict[str, Any] = {}
        self._ok = False
        init = _init_mixer() if self._enabled else None
        if init is None:
            return
        freq, _size, channels = init
        try:
            for i, name in enumerate(EFFECTS):
                buf = _resample(render(name, seed=1000 + i), SAMPLE_RATE, freq)
                self._sounds[name] = pygame.mixer.Sound(buffer=_pcm(buf, channels))
            self._ok = True
        except Exception:
            self._sounds, self._ok = {}, False

    @property
    def available(self) -> bool:
        return self._ok

    def names(self) -> list[str]:
        return sorted(EFFECTS)

    def play(self, name: str, volume: float = 1.0) -> None:
        snd = self._sounds.get(name)
        if snd is None:
            return
        try:
            v = self._master * float(volume)
            snd.set_volume(0.0 if v < 0.0 else (1.0 if v > 1.0 else v))
            snd.play()
        except Exception:
            pass

    def set_volume(self, master: float) -> None:
        try:
            self._master = max(0.0, min(1.0, float(master)))
        except (TypeError, ValueError):
            self._master = 0.0
        for snd in self._sounds.values():
            try:
                snd.set_volume(self._master)
            except Exception:
                pass

    def stop_all(self) -> None:
        for snd in self._sounds.values():
            try:
                snd.stop()
            except Exception:
                pass

def build_bank(enabled: bool = True) -> SoundBank:
    return SoundBank(enabled)

# ---------------------------------------------------------------------------
# Manual inspection: dump every effect into %TEMP%/pixelrpg_sfx
# ---------------------------------------------------------------------------
def main() -> int:
    out_dir = os.path.join(os.environ.get("TEMP") or os.environ.get("TMP") or os.getcwd(),
                           "pixelrpg_sfx")
    os.makedirs(out_dir, exist_ok=True)
    print(f"{'name':<12}{'dur (s)':>9}{'peak':>7}{'bytes':>8}")
    print("-" * 36)
    total = 0
    for name in REQUIRED_NAMES:
        path = write_wav(name, os.path.join(out_dir, name + ".wav"))
        buf, size = render(name), os.path.getsize(path)
        total += size
        print(f"{name:<12}{len(buf) / SAMPLE_RATE:>9.3f}{max(abs(v) for v in buf):>7.3f}{size:>8}")
    print("-" * 36)
    print(f"{len(REQUIRED_NAMES)} effects, {total} bytes -> {out_dir}")
    problems = validate()
    print("validate():", "OK - no problems" if not problems else problems)
    return 0 if not problems else 1

if __name__ == "__main__":
    raise SystemExit(main())

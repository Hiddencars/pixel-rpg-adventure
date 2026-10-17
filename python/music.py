#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Procedural background music for Pixel RPG Adventure (stdlib + pygame only).

Eight looping tracks ("title", "village", "forest", "swamp", "highlands",
"ruins", "graveyard", "battle") are synthesised at runtime as ``list[float]``
buffers in [-1, 1] at ``SAMPLE_RATE``, quantised to 16-bit signed mono PCM and
wrapped with ``pygame.mixer.Sound(buffer=...)``.  No numpy, no asset files.

Design notes
------------
* A track is described as note events (``_note``) plus percussion events
  (``_hit``) which are rendered additively into ONE mono buffer, so a 40 s
  track costs a single float buffer in memory instead of one per voice.
* The loop seam is a real crossfade: the arrangement is rendered ``XFADE``
  seconds past the loop end and that tail is mixed back over the first
  ``XFADE`` seconds with complementary fades, so ``play(loops=-1)`` never
  clicks.  Events that already ring into the tail are not duplicated.
* Final chain per track: gentle one-pole lowpass -> ``tanh`` soft clip ->
  normalise to ``TARGET_PEAK``.  Peaks stay inside 0.3-0.8 and never clip.
* If pygame is missing or ``pygame.mixer.init()`` fails (headless box, no audio
  device, ``SDL_AUDIODRIVER=dummy``) every call is a silent no-op and never
  raises.  ``python music.py`` dumps each track into %TEMP%/pixelrpg_music/ and
  prints a name / seconds / peak / bytes table plus ``validate()``.

Memory: 8 tracks x ~40 s x 22050 Hz x 2 bytes ~= 14 MB of PCM; the player keeps
one Sound per track it has played, so a fully loaded bank is ~28 MB.
"""

from __future__ import annotations

import array
import math
import os
import random
import sys
import wave
from typing import Any

try:                                      # pragma: no cover - env dependent
    import pygame
except Exception:                         # pragma: no cover
    pygame = None

SAMPLE_RATE = 22050
TWO_PI = 2.0 * math.pi
INV_TWO_PI = 1.0 / TWO_PI

XFADE = 0.40                              # seconds of loop crossfade
TARGET_PEAK = 0.60                        # final normalised peak
PRE_PEAK = 0.88                           # headroom before the soft clip
MIN_PEAK, MAX_PEAK = 0.30, 0.80
MIN_DUR, MAX_DUR = 25.0, 60.0
SILENCE_LIMIT = 2.0                       # seconds of silence = a problem
SEED = 20261017

TRACK_ORDER: tuple[str, ...] = (
    "title", "village", "forest", "swamp",
    "highlands", "ruins", "graveyard", "battle",
)

# ---------------------------------------------------------------------------
# Note table: names <-> MIDI <-> Hz, chord and scale spelling
# ---------------------------------------------------------------------------
_STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

_CHORDS: dict[str, tuple[int, ...]] = {
    "": (0, 4, 7), "m": (0, 3, 7), "5": (0, 7, 12), "sus4": (0, 5, 7),
    "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10),
    "6": (0, 4, 7, 9), "m6": (0, 3, 7, 9), "dim": (0, 3, 6),
    "m7b5": (0, 3, 6, 10), "add9": (0, 4, 7, 14), "madd9": (0, 3, 7, 14),
}

_MAJOR = (0, 2, 4, 5, 7, 9, 11)
_MINOR = (0, 2, 3, 5, 7, 8, 10)
_HARM_MINOR = (0, 2, 3, 5, 7, 8, 11)

_KINDS = {"sine": 0, "tri": 1, "saw": 2, "square": 3}


def note_to_midi(name: str) -> int:
    """``"C4"`` / ``"F#3"`` / ``"Bb2"`` -> MIDI note number (C4 == 60)."""
    s = name.strip()
    i = 1
    while i < len(s) and s[i] in "#b":
        i += 1
    letter, acc, octave = s[0].upper(), s[1:i], s[i:]
    n = _STEP[letter] + 12 * (int(octave) + 1)
    return n + acc.count("#") - acc.count("b")


def midi_to_freq(midi: float) -> float:
    """MIDI note number -> frequency in Hz (A4 == 440)."""
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


def _split_chord(name: str) -> tuple[int, str]:
    """``"F#m7b5"`` -> ``(root midi pitch class, quality)``."""
    s = name.strip()
    i = 1
    while i < len(s) and s[i] in "#b":
        i += 1
    root, quality = s[0].upper() + s[1:i], s[i:]
    pc = (_STEP[root[0]] + root.count("#") - root.count("b")) % 12
    return pc, quality


def chord_notes(name: str, octave: int = 3) -> list[int]:
    """``"Am7"`` -> ``[57, 60, 64, 67]`` (root placed at ``octave``)."""
    pc, quality = _split_chord(name)
    root = 12 * (octave + 1) + pc
    return [root + iv for iv in _CHORDS.get(quality, _CHORDS[""])]


def chord_pcs(name: str) -> set[int]:
    return {m % 12 for m in chord_notes(name, 4)}


# ---------------------------------------------------------------------------
# Synth layer: envelopes, oscillators, filters, mixing
# ---------------------------------------------------------------------------
def _n(dur: float) -> int:
    """Sample count for a duration in seconds (at least one sample)."""
    return max(1, int(dur * SAMPLE_RATE))


def _env(n: int, a: float = 0.01, d: float = 0.2, s: float = 0.6,
         r: float = 0.25) -> list[float]:
    """ADSR as a list of exactly ``n`` samples."""
    sr = float(SAMPLE_RATE)
    ea, ed, er = max(1, int(a * sr)), max(1, int(d * sr)), max(1, int(r * sr))
    if ea + ed + er > n:
        k = n / float(ea + ed + er)
        ea, ed, er = max(1, int(ea * k)), max(1, int(ed * k)), max(1, int(er * k))
    seg = [j / ea for j in range(ea)]
    seg += [1.0 - (1.0 - s) * (j / ed) for j in range(ed)]
    es = max(0, n - ea - ed - er)
    if es:
        seg += [s] * es
    seg += [s * (1.0 - j / er) for j in range(er)]
    if len(seg) < n:
        seg += [0.0] * (n - len(seg))
    return seg[:n]


def _decay(n: int, tau: float) -> list[float]:
    """Exponential decay envelope (``tau`` in seconds)."""
    k = 1.0 / max(1e-4, tau * SAMPLE_RATE)
    return [math.exp(-i * k) for i in range(n)]


def _voice(buf: list[float], start: int, dur: float, freq: float, kind: str = "sine",
           amp: float = 0.2, env: list[float] | None = None, cutoff: float = 0.0,
           vib: float = 0.0, vib_hz: float = 5.0) -> None:
    """Add one oscillator note into ``buf`` at ``start`` (clipped to the end)."""
    if start >= len(buf) or start < 0:
        return
    n = min(_n(dur), len(buf) - start)
    if n < 2:
        return
    e = env if env is not None else _env(n, 0.01, 0.2, 0.6, 0.3)
    if len(e) < n:
        e = list(e) + [0.0] * (n - len(e))
    step = TWO_PI * freq / SAMPLE_RATE
    code = _KINDS.get(kind, 0)
    a_lp = 0.0 if cutoff <= 0.0 else 1.0 - math.exp(-TWO_PI * cutoff / SAMPLE_RATE)
    vib_step = TWO_PI * vib_hz / SAMPLE_RATE
    ph = vib_ph = y = 0.0
    for i in range(n):
        if vib:
            vib_ph += vib_step
            ph += step * (1.0 + vib * math.sin(vib_ph))
        else:
            ph += step
        if code == 0:
            v = math.sin(ph)
        else:
            p = (ph * INV_TWO_PI) % 1.0
            if code == 1:
                v = 4.0 * abs(p - 0.5) - 1.0
            elif code == 2:
                v = 2.0 * p - 1.0
            else:
                v = 1.0 if p < 0.5 else -1.0
        if a_lp:
            y += a_lp * (v - y)
            v = y
        buf[start + i] += v * e[i] * amp


def _lp_ip(buf: list[float], cutoff: float) -> list[float]:
    """One-pole lowpass applied in place (no copy of the buffer)."""
    if cutoff <= 0.0 or cutoff >= SAMPLE_RATE * 0.5:
        return buf
    a, y = 1.0 - math.exp(-TWO_PI * cutoff / SAMPLE_RATE), 0.0
    for i in range(len(buf)):
        y += a * (buf[i] - y)
        buf[i] = y
    return buf


def _soft_ip(buf: list[float], drive: float = 1.0) -> list[float]:
    """tanh soft clip in place - keeps transients rounded instead of square."""
    for i, v in enumerate(buf):
        buf[i] = math.tanh(v * drive)
    return buf


def _norm_ip(buf: list[float], peak: float = TARGET_PEAK) -> list[float]:
    """Scale in place so the absolute peak equals ``peak`` (never clips)."""
    m = max((abs(v) for v in buf), default=0.0)
    if m > 1e-9:
        g = peak / m
        for i in range(len(buf)):
            buf[i] *= g
    return buf


def _resample(buf: list[float], src: int, dst: int) -> list[float]:
    """Linear resample, used only when the live mixer rate differs from ours."""
    if src == dst or not buf:
        return list(buf)
    n, last, out = max(1, int(len(buf) * dst / src)), len(buf) - 1, []
    for i in range(n):
        p, i0 = i * src / dst, int(i * src / dst)
        out.append(buf[last] if i0 >= last
                   else buf[i0] + (buf[i0 + 1] - buf[i0]) * (p - i0))
    return out


def _pcm(buf: list[float], channels: int = 1) -> bytes:
    """16-bit signed little-endian PCM, interleaved for ``channels``."""
    a = array.array("h")
    for v in buf:
        s = int(v * 32767.0)
        s = 32767 if s > 32767 else (-32768 if s < -32768 else s)
        for _ in range(channels):
            a.append(s)
    if sys.byteorder == "big":                # pragma: no cover
        a.byteswap()
    return a.tobytes()


def _from_pcm(data: bytes) -> list[float]:
    """Inverse of :func:`_pcm` for the rare mixer-format-mismatch path."""
    a = array.array("h")
    a.frombytes(data)
    if sys.byteorder == "big":                # pragma: no cover
        a.byteswap()
    return [v / 32768.0 for v in a]


# ---------------------------------------------------------------------------
# Percussion and texture voices (all write straight into the master buffer)
# ---------------------------------------------------------------------------
def _kick(buf: list[float], start: int, amp: float = 0.6) -> None:
    n = min(_n(0.20), len(buf) - start)
    if n < 2:
        return
    env = _env(n, 0.001, 0.10, 0.0, 0.09)
    s0, s1 = TWO_PI * 150.0 / SAMPLE_RATE, TWO_PI * 47.0 / SAMPLE_RATE
    sweep = 0.055 * SAMPLE_RATE
    a = 1.0 - math.exp(-TWO_PI * 800.0 / SAMPLE_RATE)
    ph = y = 0.0
    for i in range(n):
        k = i / sweep if i < sweep else 1.0
        ph += s0 + (s1 - s0) * k
        y += a * (math.sin(ph) - y)
        buf[start + i] += y * env[i] * amp


def _snare(buf: list[float], start: int, rng: random.Random, amp: float = 0.42) -> None:
    n = min(_n(0.17), len(buf) - start)
    if n < 2:
        return
    env = _env(n, 0.001, 0.075, 0.0, 0.09)
    step = TWO_PI * 185.0 / SAMPLE_RATE
    a = 1.0 - math.exp(-TWO_PI * 900.0 / SAMPLE_RATE)
    ph = lp = 0.0
    for i in range(n):
        ph += step
        x = rng.uniform(-1.0, 1.0)
        lp += a * (x - lp)
        buf[start + i] += ((x - lp) * 1.1 + math.sin(ph) * 0.45) * env[i] * amp


def _hat(buf: list[float], start: int, rng: random.Random, amp: float = 0.16) -> None:
    n = min(_n(0.045), len(buf) - start)
    if n < 2:
        return
    env = _env(n, 0.0005, 0.016, 0.0, 0.024)
    a = 1.0 - math.exp(-TWO_PI * 2400.0 / SAMPLE_RATE)
    lp = 0.0
    for i in range(n):
        x = rng.uniform(-1.0, 1.0)
        lp += a * (x - lp)
        buf[start + i] += (x - lp) * env[i] * amp


def _shaker(buf: list[float], start: int, rng: random.Random, amp: float = 0.12) -> None:
    n = min(_n(0.11), len(buf) - start)
    if n < 2:
        return
    env = _env(n, 0.012, 0.045, 0.0, 0.05)
    a = 1.0 - math.exp(-TWO_PI * 4200.0 / SAMPLE_RATE)
    lp = 0.0
    for i in range(n):
        x = rng.uniform(-1.0, 1.0)
        lp += a * (x - lp)
        buf[start + i] += (x - lp) * env[i] * amp


def _tick(buf: list[float], start: int, rng: random.Random, amp: float = 0.14) -> None:
    """Dry wooden click."""
    n = min(_n(0.06), len(buf) - start)
    if n < 2:
        return
    env = _env(n, 0.0005, 0.020, 0.0, 0.035)
    a = 1.0 - math.exp(-TWO_PI * 1800.0 / SAMPLE_RATE)
    step = TWO_PI * 620.0 / SAMPLE_RATE
    ph = lp = 0.0
    for i in range(n):
        ph += step
        x = rng.uniform(-1.0, 1.0)
        lp += a * (x - lp)
        buf[start + i] += ((x - lp) * 0.8 + math.sin(ph) * 0.5) * env[i] * amp


def _tom(buf: list[float], start: int, amp: float = 0.34, f0: float = 190.0) -> None:
    n = min(_n(0.34), len(buf) - start)
    if n < 2:
        return
    env = _env(n, 0.001, 0.16, 0.0, 0.17)
    s0, s1 = TWO_PI * f0 / SAMPLE_RATE, TWO_PI * f0 * 0.55 / SAMPLE_RATE
    ph = 0.0
    for i in range(n):
        ph += s0 + (s1 - s0) * (i / n)
        buf[start + i] += math.sin(ph) * env[i] * amp


def _bell(buf: list[float], start: int, freq: float, amp: float = 0.26,
          tau: float = 2.4) -> None:
    """Additive bell: higher partials decay faster, with a short attack ramp."""
    at = max(1, int(0.004 * SAMPLE_RATE))
    for ratio, part in ((1.0, 1.0), (2.0, 0.45), (3.01, 0.22), (4.16, 0.10)):
        n = _n(tau * 1.6)
        env = _decay(n, tau / (ratio ** 0.6))
        for i in range(at):                      # 4 ms ramp: no onset click
            env[i] *= i / at
        _voice(buf, start, n / SAMPLE_RATE, freq * ratio, "sine", amp * part, env)


def _wind(buf: list[float], start: int, dur: float, amp: float,
          rng: random.Random, cutoff: float = 520.0) -> None:
    """Slow filtered noise bed with a breathing amplitude."""
    n = min(_n(dur), len(buf) - start)
    if n < 2:
        return
    a = 1.0 - math.exp(-TWO_PI * cutoff / SAMPLE_RATE)
    lfo = TWO_PI * 0.07 / SAMPLE_RATE
    y = ph = 0.0
    for i in range(n):
        y += a * (rng.uniform(-1.0, 1.0) - y)
        ph += lfo
        buf[start + i] += y * (0.62 + 0.38 * math.sin(ph)) * amp


# ---------------------------------------------------------------------------
# Events: a track is a list of note events + a list of hit events
# ---------------------------------------------------------------------------
def _note(t: float, dur: float, midi: float, kind: str = "sine", amp: float = 0.12,
          a: float = 0.01, d: float = 0.2, s: float = 0.6, r: float = 0.25,
          cutoff: float = 0.0, vib: float = 0.0) -> dict[str, Any]:
    return {"t": t, "dur": dur, "midi": midi, "kind": kind, "amp": amp,
            "a": a, "d": d, "s": s, "r": r, "cutoff": cutoff, "vib": vib}


def _hit(t: float, kind: str, amp: float = 0.4, dur: float = 0.0,
         freq: float = 0.0) -> dict[str, Any]:
    return {"t": t, "kind": kind, "amp": amp, "dur": dur, "freq": freq}


def _pad(ev: list, t: float, dur: float, notes: list[int], kind: str = "tri",
         amp: float = 0.05, a: float = 0.9, d: float = 0.35, s: float = 0.8,
         r: float = 1.2, cutoff: float = 2200.0) -> None:
    for m in notes:
        ev.append(_note(t, dur, m, kind, amp, a, d, s, r, cutoff))


def _bass(ev: list, t: float, dur: float, midi: float, kind: str = "sine",
          amp: float = 0.20, cutoff: float = 0.0, a: float = 0.02) -> None:
    ev.append(_note(t, dur, midi, kind, amp, a, 0.25, 0.75,
                    min(0.4, dur * 0.5), cutoff))


def _arp(ev: list, t: float, notes: list[int], steps: int, step: float,
         kind: str = "tri", amp: float = 0.06, cutoff: float = 2800.0) -> None:
    """Cycle through ``notes`` one per ``step``, plucked envelope."""
    for i in range(steps):
        ev.append(_note(t + i * step, step * 0.92, notes[i % len(notes)],
                        kind, amp, 0.006, 0.20, 0.28, min(0.6, step * 0.8), cutoff))


def _grid_hits(hits: list, pattern: dict, bar: float, bars: int, div: int = 16) -> None:
    """``pattern`` maps a hit kind to ``(step indices in a bar, amplitude)``."""
    step = bar / div
    for b in range(bars):
        for kind, (steps, amp) in pattern.items():
            for s in steps:
                hits.append(_hit(b * bar + s * step, kind, amp))


def _melody(rng: random.Random, prog: list[str], bar: float, bars: int,
            scale: tuple[int, ...], root_midi: int, lo: int, hi: int,
            density: float, kind: str = "sine", amp: float = 0.12,
            dur_beats: float = 1.0, vib: float = 0.0, cutoff: float = 3200.0,
            grid: int = 8) -> list[dict[str, Any]]:
    """Chord-aware melody: chord tones on strong beats, mostly stepwise motion."""
    beat = bar / 4.0
    step = bar / grid
    ev: list[dict[str, Any]] = []
    prev: int | None = None
    for b in range(bars):
        ch = prog[b % len(prog)]
        tones = chord_pcs(ch)
        for s in range(grid):
            if s and rng.random() > density:
                continue
            strong = (s % max(2, grid // 2)) == 0
            cands = [m for m in range(lo, hi + 1)
                     if (m - root_midi) % 12 in scale]
            if strong:
                ct = [m for m in cands if m % 12 in tones]
                if ct:
                    cands = ct
            if prev is None:
                pick = rng.choice(cands)
            else:
                near = [m for m in cands if abs(m - prev) <= 4]
                pick = rng.choice(near if near else cands)
            if pick == prev and rng.random() < 0.6 and len(cands) > 1:
                pick = rng.choice([m for m in cands if m != prev] or cands)
            dur = beat * dur_beats
            if rng.random() < 0.2:
                dur *= 1.5
            ev.append(_note(b * bar + s * step, dur, pick, kind, amp,
                            0.02, 0.3, 0.55, min(0.6, dur), cutoff, vib))
            prev = pick
    return ev


def _emit_note(buf: list[float], e: dict, off: float, rng: random.Random) -> None:
    start = int((e["t"] + off) * SAMPLE_RATE)
    if start >= len(buf) or e["dur"] <= 0.0:
        return
    n = _n(e["dur"])
    if n < 4:
        return
    env = _env(n, e["a"], e["d"], e["s"], e["r"])
    _voice(buf, start, e["dur"], midi_to_freq(e["midi"]), e["kind"], e["amp"],
           env, e["cutoff"], e["vib"])


def _emit_hit(buf: list[float], h: dict, off: float, rng: random.Random) -> None:
    start = int((h["t"] + off) * SAMPLE_RATE)
    if start >= len(buf) or start < 0:
        return
    kind, amp = h["kind"], h["amp"]
    if kind == "kick":
        _kick(buf, start, amp)
    elif kind == "snare":
        _snare(buf, start, rng, amp)
    elif kind == "hat":
        _hat(buf, start, rng, amp)
    elif kind == "shaker":
        _shaker(buf, start, rng, amp)
    elif kind == "tick":
        _tick(buf, start, rng, amp)
    elif kind == "tom":
        _tom(buf, start, amp)
    elif kind == "bell":
        _bell(buf, start, h["freq"] or 262.0, amp)
    elif kind == "wind":
        _wind(buf, start, h["dur"] or 1.0, amp, rng)


def _render(buf: list[float], events: list, hits: list, loop_sec: float,
            wrap_sec: float, rng: random.Random) -> None:
    """Render events into ``buf``, duplicating early ones past the loop end so
    the crossfade tail carries real music.  Events that already reach the tail
    (drones, wind beds) are not duplicated."""
    end = loop_sec + wrap_sec - 1e-3
    for e in events:
        _emit_note(buf, e, 0.0, rng)
        if e["t"] < wrap_sec and e["t"] + e["dur"] < end:
            _emit_note(buf, e, loop_sec, rng)
    for h in hits:
        _emit_hit(buf, h, 0.0, rng)
        dur = h["dur"] or 0.5
        if h["t"] < wrap_sec and h["t"] + dur < end:
            _emit_hit(buf, h, loop_sec, rng)


# ---------------------------------------------------------------------------
# The eight tracks
# ---------------------------------------------------------------------------
def _build_title(sp, rng):
    """Warm, hopeful menu theme in C major: pad, held bass, gentle arpeggio."""
    bar, bars, prog = sp["bar"], sp["bars"], sp["prog"]
    ev, hits = [], []
    for b in range(bars):
        t, ch = b * bar, prog[b % len(prog)]
        notes = chord_notes(ch, 4)
        _pad(ev, t, bar * 0.97, notes, "tri", 0.055, 1.1, 0.35, 0.8, 1.3, 2300.0)
        root = notes[0] - 24
        _bass(ev, t, bar * 0.88, root, "sine", 0.22)
        _bass(ev, t + bar * 0.5, bar * 0.34, root, "sine", 0.11)
        seq = [notes[0], notes[1], notes[2], notes[1]]
        _arp(ev, t, [m + 12 for m in seq], 4, bar / 4.0, "tri", 0.062, 2600.0)
    ev += _melody(rng, prog, bar, bars, _MAJOR, 72, 67, 86, 0.34,
                  "sine", 0.110, 1.0, 0.004, 3200.0, grid=8)
    return ev, hits


def _build_village(sp, rng):
    """Pastoral, brighter G major with a soft shaker and a plucked arpeggio."""
    bar, bars, prog = sp["bar"], sp["bars"], sp["prog"]
    ev, hits = [], []
    for b in range(bars):
        t, ch = b * bar, prog[b % len(prog)]
        notes = chord_notes(ch, 4)
        _pad(ev, t, bar * 0.96, notes, "tri", 0.058, 0.8, 0.35, 0.8, 1.0, 2600.0)
        root = notes[0] - 24
        _bass(ev, t, bar * 0.42, root, "sine", 0.20)
        _bass(ev, t + bar * 0.5, bar * 0.36, root + 7, "sine", 0.12)
        seq = [notes[0], notes[1], notes[2], notes[1], notes[2]]
        _arp(ev, t, [m + 12 for m in seq], 8, bar / 8.0, "tri", 0.046, 3000.0)
        if b % 4 == 3:                                    # little bell answer
            hits.append(_hit(t + bar * 0.5, "bell", 0.16,
                             freq=midi_to_freq(notes[2] + 12)))
    ev += _melody(rng, prog, bar, bars, _MAJOR, 67, 67, 88, 0.42,
                  "tri", 0.095, 1.0, 0.0, 3400.0, grid=8)
    _grid_hits(hits, {"shaker": ((2, 6, 10, 14), 0.075)}, bar, bars)
    return ev, hits


def _build_forest(sp, rng):
    """Airy D major: sine pad, high arpeggio, woodblock ticks and a wind bed."""
    bar, bars, prog = sp["bar"], sp["bars"], sp["prog"]
    ev, hits = [], []
    for b in range(bars):
        t, ch = b * bar, prog[b % len(prog)]
        notes = chord_notes(ch, 4)
        _pad(ev, t, bar * 0.95, notes, "sine", 0.048, 1.2, 0.35, 0.8, 1.4, 2000.0)
        _pad(ev, t, bar * 0.95, [notes[0] + 12, notes[2] + 12], "tri",
             0.026, 1.6, 0.35, 0.8, 1.6, 2400.0)
        _bass(ev, t, bar * 0.85, notes[0] - 24, "sine", 0.17)
        seq = [notes[0], notes[2], notes[1], notes[2]]
        _arp(ev, t, [m + 12 for m in seq], 8, bar / 8.0, "sine", 0.036, 3600.0)
    ev += _melody(rng, prog, bar, bars, _MAJOR, 74, 69, 88, 0.30,
                  "sine", 0.098, 1.0, 0.005, 3000.0, grid=8)
    hits.append(_hit(0.0, "wind", 0.05, bars * bar + XFADE))
    _grid_hits(hits, {"tick": ((3, 11), 0.11)}, bar, bars)
    return ev, hits


def _build_swamp(sp, rng):
    """D minor: continuous low drone, sparse m7 pad, sparse kick and ticks."""
    bar, bars, prog = sp["bar"], sp["bars"], sp["prog"]
    ev, hits = [], []
    all_dur = bars * bar + XFADE
    _pad(ev, 0.0, all_dur, [38], "sine", 0.150, 0.8, 0.5, 0.8, 0.8, 1200.0)
    _pad(ev, 0.0, all_dur, [45], "sine", 0.070, 1.0, 0.5, 0.8, 0.8, 1400.0)
    for b in range(bars):
        t, ch = b * bar, prog[b % len(prog)]
        notes = chord_notes(ch, 3)
        _pad(ev, t, bar * 0.7, notes, "tri", 0.045, 0.7, 0.6, 0.8, 0.8, 1500.0)
        _bass(ev, t, bar * 0.45, notes[0] - 12, "saw", 0.10, 900.0)
        if b % 4 == 2:                                    # croak
            ev.append(_note(t + bar * 0.75, 0.22, notes[1], "saw", 0.055,
                            0.02, 0.1, 0.3, 0.12, 800.0, 0.02))
    ev += _melody(rng, prog, bar, bars, _MINOR, 62, 62, 79, 0.24,
                  "tri", 0.085, 1.0, 0.006, 2200.0, grid=4)
    _grid_hits(hits, {"kick": ((0, 10), 0.34), "tick": ((6, 14), 0.09)}, bar, bars)
    return ev, hits


def _build_highlands(sp, rng):
    """E minor: open-fifth drone, eighth-note bass pulse, wind and shaker."""
    bar, bars, prog = sp["bar"], sp["bars"], sp["prog"]
    ev, hits = [], []
    all_dur = bars * bar + XFADE
    _pad(ev, 0.0, all_dur, [40, 47], "tri", 0.075, 0.9, 0.5, 0.85, 0.8, 1800.0)
    for b in range(bars):
        t, ch = b * bar, prog[b % len(prog)]
        notes = chord_notes(ch, 4)
        _pad(ev, t, bar * 0.9, [notes[0], notes[0] + 7], "tri",
             0.045, 0.5, 0.5, 0.8, 0.5, 2200.0)
        root = notes[0] - 24
        for k in range(8):                                # driving pulse
            _bass(ev, t + k * bar / 8.0, bar / 9.0, root if k % 4 else root + 12,
                  "saw", 0.105, 700.0, 0.004)
    ev += _melody(rng, prog, bar, bars, _MINOR, 64, 64, 83, 0.55,
                  "sine", 0.105, 1.0, 0.006, 3000.0, grid=8)
    hits.append(_hit(0.0, "wind", 0.055, bars * bar + XFADE))
    _grid_hits(hits, {"kick": ((0, 8), 0.30), "tom": ((6,), 0.22),
                      "shaker": ((2, 6, 10, 14), 0.09)}, bar, bars)
    return ev, hits


def _build_ruins(sp, rng):
    """A harmonic minor: drone, slow pad, tremolo fifths, deep toms."""
    bar, bars, prog = sp["bar"], sp["bars"], sp["prog"]
    ev, hits = [], []
    all_dur = bars * bar + XFADE
    _pad(ev, 0.0, all_dur, [45], "sine", 0.130, 0.9, 0.5, 0.85, 0.8, 1200.0)
    _pad(ev, 0.0, all_dur, [52], "tri", 0.045, 1.1, 0.5, 0.8, 0.8, 1600.0)
    for b in range(bars):
        t, ch = b * bar, prog[b % len(prog)]
        notes = chord_notes(ch, 3)
        _pad(ev, t, bar * 0.88, notes, "sine", 0.048, 1.0, 0.5, 0.8, 0.8, 1800.0)
        _bass(ev, t, bar * 0.8, notes[0] - 12, "tri", 0.14)
        trem = notes[2] + 24                              # tremolo on the fifth
        for k in range(16):
            _arp(ev, t + k * bar / 16.0, [trem], 1, bar / 16.0, "sine", 0.024, 4200.0)
    ev += _melody(rng, prog, bar, bars, _HARM_MINOR, 69, 69, 86, 0.36,
                  "tri", 0.088, 1.0, 0.004, 2600.0, grid=8)
    _grid_hits(hits, {"tom": ((0, 7, 11), 0.26), "tick": ((4, 12), 0.08)}, bar, bars)
    return ev, hits


def _build_graveyard(sp, rng):
    """A minor: slow mournful pad, tolling bell every second bar, no drums."""
    bar, bars, prog = sp["bar"], sp["bars"], sp["prog"]
    ev, hits = [], []
    for b in range(bars):
        t, ch = b * bar, prog[b % len(prog)]
        notes = chord_notes(ch, 4)
        _pad(ev, t, bar * 0.98, notes, "sine", 0.052, 1.5, 0.5, 0.8, 1.8, 1700.0)
        _bass(ev, t, bar * 0.9, notes[0] - 24, "sine", 0.19, 0.0, 0.08)
        if b % 2 == 0:
            hits.append(_hit(t, "bell", 0.22, freq=midi_to_freq(notes[0] + 12)))
    ev += _melody(rng, prog, bar, bars, _MINOR, 69, 69, 84, 0.34,
                  "sine", 0.090, 2.0, 0.007, 2400.0, grid=4)
    return ev, hits


def _build_battle(sp, rng):
    """D minor, 132 bpm: driving eighth bass, fast lead, full drum kit."""
    bar, bars, prog = sp["bar"], sp["bars"], sp["prog"]
    ev, hits = [], []
    for b in range(bars):
        t, ch = b * bar, prog[b % len(prog)]
        notes = chord_notes(ch, 3)
        _pad(ev, t, bar * 0.95, notes, "saw", 0.030, 0.06, 0.3, 0.7, 0.2, 1500.0)
        root = notes[0] - 12
        for k in range(8):                                # eighth-note pulse
            m = root if k % 4 else root + 12
            _bass(ev, t + k * bar / 8.0, bar / 8.6, m, "saw", 0.145, 1000.0, 0.003)
    ev += _melody(rng, prog, bar, bars, _MINOR, 74, 69, 88, 0.72,
                  "square", 0.075, 0.5, 0.004, 3200.0, grid=8)
    _grid_hits(hits, {"kick": ((0, 3, 6, 8, 11, 14), 0.52),
                      "snare": ((4, 12), 0.34),
                      "hat": ((0, 2, 4, 6, 8, 10, 12, 14), 0.11)}, bar, bars)
    return ev, hits


# ---------------------------------------------------------------------------
# Track table
# ---------------------------------------------------------------------------
_SPECS: dict[str, dict[str, Any]] = {
    "title": dict(
        ru="Титульный экран", mood="спокойное начало, тёплая надежда",
        bpm=66, bars=12, prog=["Cmaj7", "G", "Am", "F"],
        build=_build_title, tone=7600.0),
    "village": dict(
        ru="Деревня", mood="уютно и безмятежно, пастораль",
        bpm=72, bars=12, prog=["G", "Em", "C", "D"],
        build=_build_village, tone=8000.0),
    "forest": dict(
        ru="Лес", mood="загадочно, но мягко, шелест листвы",
        bpm=68, bars=12, prog=["Dmaj7", "Bm7", "Gmaj7", "A"],
        build=_build_forest, tone=7200.0),
    "swamp": dict(
        ru="Болото", mood="тревожно и сыро, тягучий гул",
        bpm=84, bars=12, prog=["Dm", "Bb", "Gm", "A7"],
        build=_build_swamp, tone=6200.0),
    "highlands": dict(
        ru="Высокогорье", mood="ветрено и сурово, открытые квинты",
        bpm=96, bars=16, prog=["Em", "C", "G", "D"],
        build=_build_highlands, tone=6600.0),
    "ruins": dict(
        ru="Руины", mood="древняя тайна, настороженность",
        bpm=90, bars=12, prog=["Am", "F", "Dm", "E7"],
        build=_build_ruins, tone=6400.0),
    "graveyard": dict(
        ru="Кладбище", mood="скорбно и тихо, далёкий колокол",
        bpm=60, bars=8, prog=["Am", "F", "Dm", "E"],
        build=_build_graveyard, tone=7000.0),
    "battle": dict(
        ru="Бой", mood="напряжённо и стремительно, драйв",
        bpm=132, bars=20, prog=["Dm", "Bb", "F", "C"],
        build=_build_battle, tone=9000.0),
}

for _sp in _SPECS.values():                              # bar length in seconds
    _sp["bar"] = 240.0 / float(_sp["bpm"])

TRACKS: dict[str, dict[str, Any]] = {
    name: {
        "title": _SPECS[name]["ru"],
        "mood": _SPECS[name]["mood"],
        "seconds": round(_n(_SPECS[name]["bars"] * _SPECS[name]["bar"]) / SAMPLE_RATE, 3),
        "bpm": _SPECS[name]["bpm"],
    }
    for name in TRACK_ORDER
}


# ---------------------------------------------------------------------------
# Synthesis + cache
# ---------------------------------------------------------------------------
_CACHE: dict[str, bytes] = {}
_STATS: dict[str, dict[str, float]] = {}


def _measure(buf: list[float]) -> dict[str, float]:
    """Peak, length and longest silent stretch of a finished loop."""
    n = len(buf)
    if not n:
        return {"seconds": 0.0, "peak": 0.0, "samples": 0, "silent": 0.0}
    hop = max(1, int(0.25 * SAMPLE_RATE))
    peak = 0.0
    longest = run = 0
    i = 0
    while i < n:
        j = min(n, i + hop)
        m = 0.0
        for k in range(i, j):
            v = buf[k]
            if v < 0.0:
                v = -v
            if v > m:
                m = v
        if m > peak:
            peak = m
        if m < 1e-4:
            run += 1
            if run > longest:
                longest = run
        else:
            run = 0
        i = j
    return {"seconds": n / SAMPLE_RATE, "peak": peak, "samples": float(n),
            "silent": longest * hop / SAMPLE_RATE}


def _synthesise(name: str) -> list[float]:
    """Render one finished loop (crossfaded, soft-clipped, normalised)."""
    sp = _SPECS[name]
    rng = random.Random(SEED + 7919 * TRACK_ORDER.index(name))
    bar, bars = sp["bar"], sp["bars"]
    loop = _n(bars * bar)
    xf = _n(XFADE)
    buf = [0.0] * (loop + xf)
    events, hits = sp["build"](sp, rng)
    _render(buf, events, hits, loop / SAMPLE_RATE, XFADE, rng)
    _lp_ip(buf, float(sp["tone"]))                       # gentle master tone
    _norm_ip(buf, PRE_PEAK)                              # headroom for the clip
    _soft_ip(buf, 1.0)                                   # tanh: never square off
    for i in range(xf):                                  # seamless loop seam
        w = i / xf
        buf[i] = buf[i] * w + buf[loop + i] * (1.0 - w)
    del buf[loop:]
    return _norm_ip(buf, TARGET_PEAK)


def _pcm_for(name: str) -> bytes:
    """16-bit mono PCM of one track, rendered once and cached."""
    data = _CACHE.get(name)
    if data is None:
        if name not in _SPECS:
            return b""
        buf = _synthesise(name)
        _STATS[name] = _measure(buf)
        data = _pcm(buf, 1)
        del buf
        _CACHE[name] = data
    return data


def _stats_for(name: str) -> dict[str, float]:
    if name not in _STATS:
        _pcm_for(name)
    return _STATS.get(name, {"seconds": 0.0, "peak": 0.0, "samples": 0.0, "silent": 0.0})


def validate() -> list[str]:
    """Return problems found; an empty list means the bank is healthy."""
    problems: list[str] = []
    for name in TRACK_ORDER:
        if name not in TRACKS:
            problems.append(f"missing track: {name}")
            continue
        for key in ("title", "mood", "seconds", "bpm"):
            if key not in TRACKS[name]:
                problems.append(f"{name}: missing track key '{key}'")
        if name not in _SPECS:
            problems.append(f"{name}: missing generator")
            continue
        data = _pcm_for(name)
        st = _stats_for(name)
        if not data or st["samples"] == 0:
            problems.append(f"{name}: empty buffer")
            continue
        if not (MIN_DUR <= st["seconds"] <= MAX_DUR):
            problems.append(f"{name}: duration {st['seconds']:.2f}s outside "
                            f"{MIN_DUR:.0f}-{MAX_DUR:.0f}s")
        if not (MIN_PEAK <= st["peak"] <= MAX_PEAK):
            problems.append(f"{name}: peak {st['peak']:.3f} outside "
                            f"{MIN_PEAK}-{MAX_PEAK}")
        if st["silent"] > SILENCE_LIMIT:
            problems.append(f"{name}: silent for {st['silent']:.2f}s "
                            f"(> {SILENCE_LIMIT:.0f}s)")
    for extra in TRACKS:
        if extra not in TRACK_ORDER:
            problems.append(f"unexpected extra track: {extra}")
    return problems


def write_wav(track: str, path: str) -> None:
    """Dump one generated loop to a real mono 16-bit 22050 Hz .wav file."""
    if track not in _SPECS:
        raise KeyError(f"unknown track: {track}")
    data = _pcm_for(track)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(data)


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
def _init_mixer():
    """(freq, size, channels) of a usable 16-bit mixer, or None."""
    if pygame is None:
        return None
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=1024)
        init = pygame.mixer.get_init()
        if init and init[1] == -16:
            return init
        pygame.mixer.quit()                     # unexpected format: retry once
        pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=1024)
        init = pygame.mixer.get_init()
        return init if (init and init[1] == -16) else None
    except Exception:
        return None


class MusicPlayer:
    """Looping background music; silently inert when audio is unavailable.

    Tracks are synthesised on first use (~1-2 s each) and then cached, so a
    game start costs nothing and the second ``play`` of a track is instant.
    """

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = bool(enabled)
        self._master = 0.75
        self._sounds: dict[str, Any] = {}
        self._current: str | None = None
        self._playing: Any = None
        self._fmt = _init_mixer() if self._enabled else None
        self._ok = self._fmt is not None

    # ------------------------------------------------------------- internals
    def _sound(self, track: str):
        snd = self._sounds.get(track)
        if snd is not None or not self._ok:
            return snd
        try:
            freq, _size, channels = self._fmt
            data = _pcm_for(track)
            if not data:
                return None
            if freq != SAMPLE_RATE or channels != 1:
                floats = _from_pcm(data)
                if freq != SAMPLE_RATE:
                    floats = _resample(floats, SAMPLE_RATE, freq)
                data = _pcm(floats, channels)
            snd = pygame.mixer.Sound(buffer=data)
            snd.set_volume(self._master)
            self._sounds[track] = snd
            return snd
        except Exception:
            self._ok = False
            return None

    # ----------------------------------------------------------- public API
    @property
    def available(self) -> bool:
        return self._ok

    @property
    def current(self) -> str | None:
        return self._current

    def names(self) -> list[str]:
        return sorted(TRACKS)

    def play(self, track: str, fade_ms: int = 700) -> None:
        if track not in TRACKS:
            return
        self._current = track
        if not self._ok:
            return
        try:
            snd = self._sound(track)
            if snd is None:
                return
            if self._playing is not None and self._playing is not snd:
                self._playing.fadeout(max(0, int(fade_ms)))
            snd.set_volume(self._master)
            snd.play(loops=-1, fade_ms=max(0, int(fade_ms)))
            self._playing = snd
        except Exception:
            self._ok = False

    def stop(self, fade_ms: int = 400) -> None:
        self._current = None
        if not self._ok:
            return
        try:
            for snd in self._sounds.values():
                snd.fadeout(max(0, int(fade_ms)))
            if self._playing is not None:
                self._playing.stop()
            self._playing = None
        except Exception:
            self._ok = False

    def set_volume(self, master: float) -> None:
        try:
            v = max(0.0, min(1.0, float(master)))
        except (TypeError, ValueError):
            v = 0.0
        self._master = v
        for snd in self._sounds.values():
            try:
                snd.set_volume(v)
            except Exception:
                pass

    def next_track(self) -> str:
        """Advance the playlist, start that track and return its name."""
        if self._current in TRACK_ORDER:
            idx = (TRACK_ORDER.index(self._current) + 1) % len(TRACK_ORDER)
        else:
            idx = 0
        name = TRACK_ORDER[idx]
        self.play(name)
        return name


def build_player(enabled: bool = True) -> MusicPlayer:
    return MusicPlayer(enabled)


# ---------------------------------------------------------------------------
# Manual inspection: dump every track into %TEMP%/pixelrpg_music
# ---------------------------------------------------------------------------
def main() -> int:
    out_dir = os.path.join(os.environ.get("TEMP") or os.environ.get("TMP")
                           or os.getcwd(), "pixelrpg_music")
    os.makedirs(out_dir, exist_ok=True)
    print(f"{'track':<12}{'seconds':>9}{'peak':>7}{'bytes':>10}  title")
    print("-" * 60)
    total = 0
    for name in TRACK_ORDER:
        path = os.path.join(out_dir, name + ".wav")
        write_wav(name, path)
        st = _stats_for(name)
        size = os.path.getsize(path)
        total += size
        print(f"{name:<12}{st['seconds']:>9.2f}{st['peak']:>7.3f}{size:>10}  "
              f"{TRACKS[name]['title']} / {TRACKS[name]['bpm']} bpm")
    print("-" * 60)
    print(f"{len(TRACK_ORDER)} tracks, {total} bytes "
          f"({total / 1048576.0:.1f} MiB) -> {out_dir}")
    problems = validate()
    print("validate():", "OK - no problems" if not problems else problems)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())

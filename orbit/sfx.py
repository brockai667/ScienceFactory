"""ORBIT zvukove efekty - syntetizovane cez numpy (ziadne subory, ziadne licencie).
Kazda funkcia vrati mono float64 so spickou 1.0; hlasitost nastavi mix_audio voci hlasu."""
import math
import numpy as np


def _norm(s):
    return s / (np.abs(s).max() + 1e-9)


def _fade(s, sr, a=0.002, r=0.01):
    na, nr = max(1, int(a * sr)), max(1, int(r * sr))
    s[:na] *= np.linspace(0, 1, na)
    s[-nr:] *= np.linspace(1, 0, nr)
    return s


def pop(sr, rng, f0=820.0, f1=360.0, dur=0.08):
    # makky "pop": sinus s padajucou vyskou + kratky sum na nabehu
    n = int(dur * sr); t = np.arange(n) / sr
    f = f1 + (f0 - f1) * np.exp(-t / 0.012)
    s = np.sin(2 * math.pi * np.cumsum(f) / sr) * np.exp(-t / 0.02)
    s += rng.normal(0, 1, n) * np.exp(-t / 0.0025) * 0.3
    return _norm(_fade(s, sr))


def tick(sr, rng, f=2300.0, dur=0.03):
    n = int(dur * sr); t = np.arange(n) / sr
    s = np.sin(2 * math.pi * f * t) * np.exp(-t / 0.006) + rng.normal(0, 1, n) * np.exp(-t / 0.0015) * 0.2
    return _norm(_fade(s, sr, 0.001, 0.005))


def chirp(sr, rng):
    # vesele robotie pipnutie: 2-3 kratke stupajuce tony, mierne hranate (tanh) s vibratom
    notes = [(1100, 1750, 0.065), (1500, 2300, 0.05), (2100, 1500, 0.07)]
    if rng.random() < 0.5:
        notes = notes[:2] + [(1700, 2600, 0.06)]
    out = []
    for f0, f1, d in notes:
        n = int(d * sr); t = np.arange(n) / sr
        f = f0 + (f1 - f0) * (t / d) ** 0.7 + 40 * np.sin(2 * math.pi * 38 * t)
        s = np.tanh(2.5 * np.sin(2 * math.pi * np.cumsum(f) / sr)) * np.sin(math.pi * t / d) ** 0.6
        out += [s, np.zeros(int(0.022 * sr))]
    return _norm(_fade(np.concatenate(out), sr, 0.003, 0.02))


def riser(sr, rng, dur=0.9):
    # stupajuci ton + sum, konci ostro (pred peciatkou)
    n = int(dur * sr); t = np.arange(n) / sr; u = t / dur
    f = 170 * (1300 / 170) ** (u ** 1.3)
    ph = 2 * math.pi * np.cumsum(f) / sr
    tone = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3.01 * ph)
    nz = np.diff(rng.normal(0, 1, n + 1))                     # zhruba hornopriepustny sum
    s = (tone * 0.7 + nz * 0.25 * u) * u ** 2.2
    return _norm(_fade(s, sr, 0.01, 0.018))

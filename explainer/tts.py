#!/usr/bin/env python3
"""Kokoro TTS pre explainer (lokalny, zadarmo) - rovnaky model ako denna fabrika,
len samostatne, aby explainer nezavisel od pro_engine (iny engine, iny format).

speak(text) -> numpy float32 mono @ 24 kHz. Cisla/roky sa prepisu na slova (inak "19hundred92").
"""
import os
import re
import sys

import numpy as np
import requests

from common import ROOT

SR = 24000
_KOK = {}


def kokoro_dir(cfg_dir=None):
    for c in (cfg_dir, os.path.join(ROOT, "kokoro"), r"C:\Users\damia\kokoro"):
        if c and os.path.exists(os.path.join(c, "kokoro-v1.0.onnx")):
            return c
    return os.path.join(ROOT, "kokoro")


def ensure_kokoro(md):
    os.makedirs(md, exist_ok=True)
    base = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
    for fn in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        p = os.path.join(md, fn)
        if not os.path.exists(p):
            sys.stderr.write(f"[kokoro] stahujem {fn}...\n")
            with open(p, "wb") as f:
                f.write(requests.get(base + fn, timeout=600).content)


_SM = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
       "fifteen sixteen seventeen eighteen nineteen").split()
_TN = "twenty thirty forty fifty sixty seventy eighty ninety".split()


def _n2w(n):
    n = int(n)
    if n < 20:
        return _SM[n]
    if n < 100:
        return _TN[n // 10 - 2] + ("" if n % 10 == 0 else " " + _SM[n % 10])
    if n < 1000:
        s = _SM[n // 100] + " hundred"
        return s if n % 100 == 0 else s + " " + _n2w(n % 100)
    for div, w in ((10 ** 9, "billion"), (10 ** 6, "million"), (10 ** 3, "thousand")):
        if n >= div:
            s = _n2w(n // div) + " " + w
            return s if n % div == 0 else s + " " + _n2w(n % div)
    return str(n)


def _yr2w(y):
    y = int(y)
    if 2000 <= y <= 2009:
        return "two thousand" + ("" if y == 2000 else " " + _SM[y - 2000])
    a, b = divmod(y, 100)
    if b == 0:
        return _n2w(a) + " hundred"
    if b < 10:
        return _n2w(a) + " oh " + _SM[b]
    return _n2w(a) + " " + _n2w(b)


def speakable(s):
    s = str(s)
    _CUR = {"$": ("dollar", "dollars"), "\u00a3": ("pound", "pounds"), "\u20ac": ("euro", "euros")}

    def _cur(m):
        num = m.group(2).replace(",", "")
        unit = (m.group(3) or "").strip()
        word = _CUR[m.group(1)][0 if (num in ("1", "1.0") and not unit) else 1]
        return num + ((" " + unit) if unit else "") + " " + word
    s = re.sub(r"([$\u00a3\u20ac])\s?(\d[\d,]*\.?\d*)(?:\s+(million|billion|trillion|thousand))?\b", _cur, s)

    def _dec(m):
        a, b = divmod(int(m.group(1)), 100)
        return _n2w(a) + " " + ("hundreds" if b == 0 else _TN[b // 10 - 2][:-1] + "ies")
    s = re.sub(r"\b(1[5-9]\d0|20\d0)s\b", _dec, s)
    s = re.sub(r"\b(1[5-9]\d\d|20\d\d)\b", lambda m: _yr2w(m.group(1)), s)
    s = re.sub(r"\b\d{1,3}(?:,\d{3})+\b", lambda m: _n2w(m.group(0).replace(",", "")), s)
    s = re.sub(r"\b\d{5,}\b", lambda m: _n2w(m.group(0)), s)
    # jednotky, ktore Kokoro cita po pismenach
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s?MB/s\b", r"\1 megabytes per second", s)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s?GB/s\b", r"\1 gigabytes per second", s)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s?Gbps\b", r"\1 gigabits per second", s)
    s = re.sub(r"\b(\d+(?:\.\d+)?)\s?Mbps\b", r"\1 megabits per second", s)
    s = re.sub(r"\bUSB-C\b", "USB C", s)
    s = re.sub(r"\bUSB-A\b", "USB A", s)
    return s


def chunks(s, limit=280):
    s = speakable(s)
    sents = re.split(r"(?<=[.!?])\s+", str(s).strip())
    out, cur = [], ""
    for sent in sents:
        while len(sent) > limit:
            cut = sent.rfind(" ", 0, limit)
            cut = cut if cut > 40 else limit
            out.append((cur + " " + sent[:cut]).strip())
            cur = ""
            sent = sent[cut:].strip()
        if len(cur) + len(sent) + 1 > limit:
            out.append(cur.strip())
            cur = sent
        else:
            cur = (cur + " " + sent).strip()
    if cur:
        out.append(cur)
    return [c for c in out if c]


def load(voice="am_michael", speed=1.0, model_dir=None):
    from kokoro_onnx import Kokoro
    md = kokoro_dir(model_dir)
    ensure_kokoro(md)
    _KOK["k"] = Kokoro(os.path.join(md, "kokoro-v1.0.onnx"), os.path.join(md, "voices-v1.0.bin"))
    _KOK["voice"] = voice
    _KOK["speed"] = float(speed)


def speak(text):
    """Vrati float32 pole @24kHz pre cely text (spojene chunky)."""
    if "k" not in _KOK:
        load()
    parts = []
    for ch in chunks(text):
        samples, sr = _KOK["k"].create(ch, voice=_KOK["voice"], speed=_KOK["speed"])
        if sr != SR:
            # kokoro vzdy 24k, ale pre istotu linearne prevzorkuj
            idx = np.linspace(0, len(samples) - 1, int(len(samples) * SR / sr))
            samples = np.interp(idx, np.arange(len(samples)), samples)
        parts.append(np.asarray(samples, dtype=np.float32))
    if not parts:
        return np.zeros(int(SR * 0.3), dtype=np.float32)
    return np.concatenate(parts)

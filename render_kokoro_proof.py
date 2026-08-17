# -*- coding: utf-8 -*-
"""Proof: prerenderuje scripts/bridge.json s Kokoro hlasom (Adam) namiesto edge-tts.
Monkeypatch make_video.tts -> Kokoro; zvysok pipeline ostava. Spustaj z ScienceFactory."""
import os, subprocess, sys

import soundfile as sf
from kokoro_onnx import Kokoro

sys.argv = ["make_video.py", "scripts/bridge.json"]
import make_video

VOICE = sys.argv[2] if False else "am_adam"
K = Kokoro(r"C:\Users\damia\kokoro\kokoro-v1.0.onnx", r"C:\Users\damia\kokoro\voices-v1.0.bin")


def kokoro_tts(text, voice, out_mp3, rate="+0%", pitch="+0Hz"):
    s, sr = K.create(text, voice=VOICE, speed=1.0, lang="en-us")
    wav = out_mp3 + ".tmp.wav"
    sf.write(wav, s, sr)
    subprocess.run(["ffmpeg", "-y", "-i", wav, "-b:a", "160k", out_mp3], capture_output=True)
    try:
        os.remove(wav)
    except OSError:
        pass
    dur = len(s) / sr
    toks = text.split() or [text]
    wts = [len(w) + 1 for w in toks]
    tot = sum(wts) or 1
    out, t = [], 0.0
    for w, wt in zip(toks, wts):
        d = dur * wt / tot
        out.append((t, d, w))
        t += d
    return out


make_video.tts = kokoro_tts
print("Renderujem bridge s Kokoro hlasom:", VOICE)
make_video.main()

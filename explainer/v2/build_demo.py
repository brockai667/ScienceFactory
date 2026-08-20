#!/usr/bin/env python3
"""Explainer v2 - DEMO builder (1 kapitola, ~60-90 s, HyperFrames).

Ciel: ukazat novy pohybovy jazyk podla explainer/LEARNINGS.md:
  - reveal KAZDEHO prvku az ked ho hlas vyslovi (word timings z faster-whisper)
  - power3 dojazdy, ziadny bounce; velocity-matched push seams medzi beatmi
  - konzistentna scena, kamera push, count-up so skalovanim, marker kruh,
    SVG draw, split karty; zrno + vineta; SFX (whoosh/tick) mixnute do hlasu
  - vystup: HTML+GSAP kompozicia -> `npx hyperframes render`

Pouzitie:
  python explainer/v2/build_demo.py            # style A (paper) aj B (poster)
  python explainer/v2/build_demo.py --style a  # len A
  python explainer/v2/build_demo.py --no-render  # len vygeneruj HTML

Vystup: temp/hf_demo/{index.html, demo_a.mp4, demo_b.mp4, voice.wav, words.json}
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys

import numpy as np
import soundfile as sf

V2 = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(V2)
ROOT = os.path.dirname(EXP)
sys.path.insert(0, EXP)
sys.path.insert(0, V2)
import svglib  # noqa: E402
import tts  # noqa: E402

SR = tts.SR
GAP = 0.35          # ticho medzi beatmi
OV = 0.5            # prekryv seam (push-slide)
W, H = 1920, 1080
PROJ = os.path.join(ROOT, "temp", "hf_demo")
IMGS = json.load(open(os.path.join(ROOT, "temp", "demo_images.json"))) if os.path.exists(
    os.path.join(ROOT, "temp", "demo_images.json")) else {}

# ---------------------------------------------------------------- scenar (cue-shaped)
BEATS = [
    {"id": "hook", "tpl": "hook_kinetic",
     "say": "You have probably seen a white USB port on an old computer, and assumed it was just cheap plastic. It is not. White is the original. The very first USB ever made.",
     "slams": [("white USB port", "THE WHITE USB PORT."), ("cheap plastic.", "“CHEAP PLASTIC”"),
               ("It is not.", "IT'S NOT."), ("the original.", "THE ORIGINAL."),
               ("first USB ever", "THE FIRST USB EVER.")]},
    {"id": "title", "tpl": "titlecard",
     "say": "White USB ports.",
     "title": "White USB ports", "kicker": "EVERY USB COLOR, PART 1"},
    {"id": "what", "tpl": "image_focus", "img": "port",
     "say": "White means USB one point zero, straight from nineteen ninety six. Spot one, and you are looking at a real piece of computer history.",
     "head": "USB 1.0", "cues": [("White means", "headline"), ("Spot one", "label"), ("computer history", "circle")],
     "label": "1996 — the first generation"},
    {"id": "before", "tpl": "list_build",
     "say": "Before USB, every device had its own plug. One port for the printer. Another for the keyboard. A third one for the mouse.",
     "head": "Before USB",
     "sub": ("its own plug.", "one plug per device"),
     "items": [("printer.", "printer", "Printer"), ("keyboard.", "keyboard", "Keyboard"), ("mouse.", "mouse", "Mouse")]},
    {"id": "speed", "tpl": "stat_countup",
     "say": "Top speed? One and a half megabytes per second. A single photo from your phone would take three whole seconds to copy.",
     "num_end": 1.5, "unit": "MB/s", "label": "USB 1.0 top speed",
     "cues": [("Top speed", "count"), ("whole seconds", "sub")],
     "sub": "3 seconds — one photo", "img": "phone"},
    {"id": "twist", "tpl": "twist_split",
     "say": "But here is the twist. USB one never died. Car stereos and cheap MP3 players still use it today. Why pay for a faster chip, when the slow one does the job?",
     "head": "It never died",
     "cues": [("stereos", "left"), ("players", "right"), ("faster chip", "line")],
     "left": ("stereo", "Car stereo"), "right": ("mp3", "MP3 player"),
     "line": "Why pay for more?"},
    {"id": "outro", "tpl": "outro_typeon",
     "say": "So next time you see a white port, remember. That is not cheap plastic. That is the founder.",
     "type_text": "That's the founder.", "cues": [("founder", "type")]},
]

STYLES = {
    "a": {  # paper notes - referencny look, ale zivy
        "bg": "#fbfbf9", "bg2": "#ececea", "ink": "#191919", "muted": "#7a7a7a",
        "accent": "#1c4ed8", "accent2": "#d62828", "card": "#ffffff",
        "font": "ComicNeue", "font_file": "ComicNeue-Bold.ttf", "grain": 0.05},
    "b": {  # bold poster dark
        "bg": "#101012", "bg2": "#1a1a1e", "ink": "#f4f2ec", "muted": "#8b8b90",
        "accent": "#ffd21f", "accent2": "#ff4d4d", "card": "#1d1d22",
        "font": "Anton", "font_file": "Anton-Regular.ttf", "grain": 0.07},
}


# ---------------------------------------------------------------- audio
def synth_voice():
    tts.load("am_michael", 1.0)
    parts, meta, cur = [], [], 0.0
    for b in BEATS:
        a = tts.speak(b["say"])
        n = min(len(a), int(0.012 * SR))
        ramp = np.linspace(0, 1, n, dtype=np.float32)
        a[:n] *= ramp
        a[-n:] *= ramp[::-1]
        b["t0"], b["t1"] = cur, cur + len(a) / SR
        parts += [a, np.zeros(int(GAP * SR), dtype=np.float32)]
        cur += len(a) / SR + GAP
        meta.append((b["id"], b["t0"], b["t1"]))
    voice = np.concatenate(parts)
    return voice, cur


def word_timings(wav_path):
    from faster_whisper import WhisperModel
    m = WhisperModel("base.en", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(wav_path, word_timestamps=True, language="en")
    return [{"w": w.word.strip(), "s": max(0.0, w.start), "e": w.end}
            for seg in segs for w in (seg.words or [])]


_NUMW = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
         "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}


def _norm(s):
    """lower, bez interpunkcie; slovne cisla -> cislice (whisper pise 'Spot 1')."""
    toks = re.sub(r"[^a-z0-9 ]", "", str(s).lower()).split()
    return [_NUMW.get(t, t) for t in toks]


def cue_time(words, t0, t1, phrase):
    """Cas KONCA prvej zhody frazy vo vnutri beat okna (reveal az ked to dopovie... resp. zacne
    - berieme start prveho slova frazy + 60 % jej trvania, nech reveal sadne do rec."""
    target = _norm(phrase)
    if not target:
        return t0
    win = [w for w in words if t0 - 0.2 <= w["s"] <= t1 + 0.2]
    nw = [_norm(w["w"]) or [""] for w in win]
    flat = [x[0] for x in nw]
    for i in range(len(flat)):
        if flat[i:i + len(target)] == target:
            s = win[i]["s"]
            e = win[min(i + len(target) - 1, len(win) - 1)]["e"]
            return s + 0.6 * (e - s)
    print(f"   [cue] NENAJDENE '{phrase}' v beate ({t0:.1f}-{t1:.1f}) -> fallback stred")
    return t0 + 0.5 * (t1 - t0)


# ---------------------------------------------------------------- SFX
def _env(n, peak):
    e = np.hanning(max(3, n * 2))[:n]
    return (e * peak).astype(np.float32)


def sfx_whoosh(dur=0.28, vol=0.10):
    n = int(dur * SR)
    rng = np.random.default_rng(7)
    x = rng.standard_normal(n).astype(np.float32)
    # low-pass sweep dolu (naiv IIR)
    y = np.zeros_like(x)
    a = np.linspace(0.02, 0.25, n)
    acc = 0.0
    for i in range(n):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y * _env(n, vol)


def sfx_tick(vol=0.10):
    n = int(0.05 * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * 1750 * t).astype(np.float32)
    return x * _env(n, vol)


def sfx_riser(dur=0.9, vol=0.06):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 180 + 520 * (t / dur) ** 2
    x = np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32)
    return x * np.linspace(0.1, 1, n).astype(np.float32) * vol


def mix_audio(voice, total, events):
    out = np.zeros(int(total * SR) + SR, dtype=np.float32)
    out[:len(voice)] += voice
    for t, kind in events:
        s = {"whoosh": sfx_whoosh(), "tick": sfx_tick(), "riser": sfx_riser()}[kind]
        i = int(t * SR)
        if 0 <= i < len(out) - len(s):
            out[i:i + len(s)] += s
    peak = float(np.abs(out).max() or 1.0)
    return out * min(1.0, 0.9 / peak)


# ---------------------------------------------------------------- HTML helpers
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def words_spans(text, cls):
    return "".join(f'<span class="{cls}">{esc(w)}</span> ' for w in str(text).split())


class Comp:
    """Zbiera klipy (html) a tweeny (js) s absolutnymi casmi."""

    def __init__(self):
        self.html, self.js = [], []
        self.sfx = []

    def clip(self, inner, start, dur, track=1, style="", cid=None):
        ida = f' id="{cid}"' if cid else ""
        self.html.append(
            f'<div{ida} class="clip" data-start="{start:.3f}" data-duration="{dur:.3f}" '
            f'data-track-index="{track}" style="{style}">{inner}</div>')

    def tw(self, code):
        self.js.append(code)


def beat_shell(c, b, i, inner, style_extra=""):
    """Beat kontajner: push-slide entrance, matched exit, jemny camera push."""
    t0, t1 = b["t0"], b["t1"]
    dur = (t1 - t0) + OV
    bid = f'b_{b["id"]}'
    c.clip(f'<div id="{bid}_cam" class="cam">{inner}</div>', t0, dur, track=2 + (i % 2),
           style=f"position:absolute;inset:0;{style_extra}", cid=bid)
    if i > 0:
        c.tw(f'tl.fromTo("#{bid}",{{x:110,opacity:0}},{{x:0,opacity:1,duration:0.55,ease:"power3.out"}},{t0:.3f});')
        c.sfx.append((t0, "whoosh"))
    ex0 = t1 + OV - 0.45
    c.tw(f'tl.to("#{bid}",{{x:-110,opacity:0,duration:0.42,ease:"power2.in"}},{ex0:.3f});')
    c.tw(f'tl.fromTo("#{bid}_cam",{{scale:1.0}},{{scale:1.045,duration:{t1 - t0:.3f},ease:"power1.inOut"}},{t0:.3f});')
    return bid


def reveal_words(c, sel, at, stagger=0.05):
    c.tw(f'tl.fromTo("{sel}",{{opacity:0,y:26}},{{opacity:1,y:0,duration:0.5,ease:"power3.out",stagger:{stagger}}},{at:.3f});')


# ---------------------------------------------------------------- templates
def tpl_hook_kinetic(c, b, i, words, S):
    rows = "".join(
        f'<div class="slam" id="slam{k}" style="{"color:" + S["accent2"] if k == 2 else ("color:" + S["accent"] if k >= 3 else "")}">{esc(txt)}</div>'
        for k, (_, txt) in enumerate(b["slams"]))
    inner = (f'<div class="hooksplit"><div class="hookcol">{rows}</div>'
             f'<div class="hookart">{svglib.usb_port(S, "hk", 560, 420)}</div></div>')
    bid = beat_shell(c, b, i, inner)
    t00 = b["t0"] + 0.2
    # port sa POSKLADA hned od zaciatku (telo -> otvor -> jazycek -> lesk)
    for k, part in enumerate(("#hk_body", "#hk_hole", "#hk_tongue", "#hk_glint")):
        c.tw(f'tl.fromTo("{part}",{{opacity:0,scale:0.8,transformOrigin:"50% 50%"}},'
             f'{{opacity:1,scale:1,duration:0.45,ease:"power3.out"}},{t00 + 0.18 * k:.3f});')
    c.tw(f'tl.fromTo("#hk",{{y:16}},{{y:-6,duration:{b["t1"] - b["t0"] - 0.4:.3f},ease:"power1.out"}},{t00:.3f});')
    for k, (cue, _) in enumerate(b["slams"]):
        t = b["t0"] + 0.25 if k == 0 else cue_time(words, b["t0"], b["t1"], cue)
        c.tw(f'tl.fromTo("#slam{k}",{{opacity:0,scale:1.28,y:10}},{{opacity:1,scale:1,y:0,duration:0.34,ease:"power3.out"}},{t:.3f});')
        c.sfx.append((t, "tick"))
    return bid


def tpl_titlecard(c, b, i, words, S):
    inner = (f'<div class="titlewrap"><div class="titleart" id="tc_a">{svglib.usb_port(S, "tc", 330, 250)}</div>'
             f'<div class="kicker" id="tc_k">{esc(b["kicker"])}</div>'
             f'<div class="bigtitle" id="tc_t">{words_spans(b["title"], "tw")}</div>'
             f'<div class="underline" id="tc_u"></div></div>')
    beat_shell(c, b, i, inner)
    c.tw(f'tl.fromTo("#tc_a",{{opacity:0,y:-30,scale:0.9}},{{opacity:1,y:0,scale:1,duration:0.55,ease:"power3.out"}},{b["t0"] + 0.05:.3f});')
    reveal_words(c, "#tc_t .tw", b["t0"] + 0.15, 0.12)
    c.tw(f'tl.fromTo("#tc_k",{{opacity:0}},{{opacity:1,duration:0.4,ease:"power2.out"}},{b["t0"] + 0.05:.3f});')
    c.tw(f'tl.fromTo("#tc_u",{{width:0}},{{width:560,duration:0.55,ease:"power3.out"}},{b["t0"] + 0.5:.3f});')


def tpl_svg_focus(c, b, i, words, S):
    """Velky port v karte, zastrcka sa don ZASUNIE na cue; headline vpravo, label, marker kruh."""
    t_head = cue_time(words, b["t0"], b["t1"], b["cues"][0][0])
    t_plug = cue_time(words, b["t0"], b["t1"], b["cues"][1][0])
    t_circ = cue_time(words, b["t0"], b["t1"], b["cues"][2][0])
    inner = (
        '<div class="split">'
        f'<div class="frame art" id="if_f"><div class="artcenter">{svglib.usb_port(S, "ifp", 560, 420)}</div>'
        f'<div class="plugfly" id="if_pl">{svglib.usb_plug(S, "ifpl", 300, 210)}</div>'
        f'<svg id="if_svg" viewBox="0 0 760 570"><ellipse id="if_ell" cx="380" cy="270" rx="235" ry="175" pathLength="100"/></svg>'
        f'<div class="label" id="if_l">{esc(b["label"])}</div></div>'
        f'<div class="side"><div class="headline" id="if_h">{words_spans(b["head"], "tw")}</div></div>'
        '</div>')
    beat_shell(c, b, i, inner)
    c.tw(f'tl.fromTo("#if_f",{{x:-90,opacity:0}},{{x:0,opacity:1,duration:0.6,ease:"power3.out"}},{b["t0"] + 0.05:.3f});')
    reveal_words(c, "#if_h .tw", t_head, 0.09)
    # zastrcka priletí a zasunie sa do portu (dva kroky: prilet, zasunutie)
    c.tw(f'tl.fromTo("#if_pl",{{x:430,y:-260,opacity:0,rotation:8}},{{x:96,y:-150,opacity:1,rotation:0,duration:0.55,ease:"power3.out"}},{t_plug:.3f});')
    c.tw(f'tl.to("#if_pl",{{x:6,duration:0.45,ease:"power2.in"}},{t_plug + 0.65:.3f});')
    c.tw(f'tl.fromTo("#if_l",{{opacity:0,y:18}},{{opacity:1,y:0,duration:0.45,ease:"power3.out"}},{t_plug:.3f});')
    c.tw(f'tl.fromTo("#if_ell",{{strokeDasharray:100,strokeDashoffset:100}},{{strokeDashoffset:0,duration:0.7,ease:"power2.inOut"}},{t_circ:.3f});')
    c.sfx.append((t_plug + 1.0, "tick"))
    c.sfx.append((t_circ, "tick"))


def tpl_list_build(c, b, i, words, S):
    draw = {"printer": svglib.printer, "keyboard": svglib.keyboard, "mouse": svglib.mouse}
    plugs = ["db25", "din", "ps2"]
    cells = "".join(
        f'<div class="cell" id="lb{k}"><div class="svgbox">{draw[key](S, "lb" + key, 300, 240)}</div>'
        f'<div class="plugrow" id="lbp{k}">{svglib.old_plug(S, "lbpl" + str(k), plugs[k], 96, 96)}</div>'
        f'<div class="cl">{esc(lab)}</div></div>'
        for k, (_, key, lab) in enumerate(b["items"]))
    subc, subt = b.get("sub", (None, ""))
    subh = f'<div class="sublab" id="lb_s">{esc(subt)}</div>' if subc else ""
    inner = (f'<div class="listwrap"><div class="headline center" id="lb_h">{words_spans(b["head"], "tw")}</div>'
             f'{subh}<div class="row">{cells}</div></div>')
    beat_shell(c, b, i, inner)
    reveal_words(c, "#lb_h .tw", b["t0"] + 0.15, 0.09)
    if subc:
        t_s = cue_time(words, b["t0"], b["t1"], subc)
        c.tw(f'tl.fromTo("#lb_s",{{opacity:0,y:16}},{{opacity:1,y:0,duration:0.45,ease:"power3.out"}},{t_s:.3f});')
    for k, (cue, _, _) in enumerate(b["items"]):
        t = cue_time(words, b["t0"], b["t1"], cue)
        c.tw(f'tl.fromTo("#lb{k}",{{opacity:0,scale:0.82,y:30}},{{opacity:1,scale:1,y:0,duration:0.5,ease:"power3.out"}},{t:.3f});')
        # kazde zariadenie ma INU zastrcku - dopadne pod zariadenie o chvilu neskor
        c.tw(f'tl.fromTo("#lbp{k}",{{opacity:0,y:-26,rotation:-10}},{{opacity:1,y:0,rotation:0,duration:0.4,ease:"power3.out"}},{t + 0.35:.3f});')
        c.sfx.append((t, "tick"))
    # tlaciaren "vypluje" papier ked pride jej cue
    t_pr = cue_time(words, b["t0"], b["t1"], b["items"][0][0])
    c.tw(f'tl.fromTo("#lbprinter_paper",{{y:-46,opacity:0}},{{y:0,opacity:1,duration:0.6,ease:"power2.out"}},{t_pr + 0.3:.3f});')


def tpl_stat_countup(c, b, i, words, S):
    t_count = cue_time(words, b["t0"], b["t1"], b["cues"][0][0]) + 0.3
    t_sub = cue_time(words, b["t0"], b["t1"], b["cues"][1][0])
    inner = (
        '<div class="split">'
        f'<div class="side"><div class="bignum" id="sc_n">0.0 <span class="unit">{esc(b["unit"])}</span></div>'
        f'<div class="statlab" id="sc_l">{esc(b["label"])}</div>'
        f'<div class="substat" id="sc_s">{esc(b["sub"])}</div></div>'
        f'<div class="artside" id="sc_f">{svglib.smartphone(S, "scp", 300, 520)}'
        f'<div class="miniport" id="sc_mp">{svglib.usb_port(S, "scpo", 260, 195)}</div></div>'
        '</div>')
    beat_shell(c, b, i, inner)
    dur = 1.3
    c.tw(f'var o={{v:0}};tl.to(o,{{v:{b["num_end"]},duration:{dur},ease:"power2.out",onUpdate:function(){{'
         f'document.getElementById("sc_n").childNodes[0].nodeValue=o.v.toFixed(1)+" ";}}}},{t_count:.3f});')
    c.tw(f'tl.fromTo("#sc_n",{{opacity:0,scale:0.8}},{{opacity:1,scale:1,duration:{dur},ease:"power2.out"}},{t_count:.3f});')
    c.tw(f'tl.fromTo("#sc_l",{{opacity:0,y:16}},{{opacity:1,y:0,duration:0.4,ease:"power3.out"}},{t_count + 0.4:.3f});')
    c.tw(f'tl.fromTo("#sc_s",{{opacity:0,y:22}},{{opacity:1,y:0,duration:0.5,ease:"power3.out"}},{t_sub:.3f});')
    c.tw(f'tl.fromTo("#sc_f",{{x:90,opacity:0}},{{x:0,opacity:1,duration:0.6,ease:"power3.out"}},{b["t0"] + 0.1:.3f});')
    # fotka POMALY lezie z mobilu do portu pocas "three whole seconds" (vtip = ako dlho to trva)
    c.tw(f'tl.fromTo("#scp_photo",{{x:0,y:0,opacity:1}},{{x:186,y:96,duration:2.6,ease:"none"}},{t_sub:.3f});')
    c.tw(f'tl.fromTo("#sc_mp",{{opacity:0}},{{opacity:1,duration:0.4,ease:"power2.out"}},{t_sub - 0.2:.3f});')
    c.sfx.append((t_count, "riser"))
    c.sfx.append((t_sub, "tick"))


def tpl_twist_split(c, b, i, words, S):
    t_l = cue_time(words, b["t0"], b["t1"], b["cues"][0][0])
    t_r = cue_time(words, b["t0"], b["t1"], b["cues"][1][0])
    t_line = cue_time(words, b["t0"], b["t1"], b["cues"][2][0])
    _, ll = b["left"]
    _, rl = b["right"]
    inner = (
        f'<div class="listwrap"><div class="headline center" id="tw_h">{words_spans(b["head"], "tw")}</div>'
        '<div class="row tilt">'
        f'<div class="card lft" id="tw_l"><div class="cardart">{svglib.car_stereo(S, "twcs", 430, 235)}</div><div class="cl">{esc(ll)}</div></div>'
        f'<div class="card rgt" id="tw_r"><div class="cardart">{svglib.mp3_player(S, "twm3", 210, 300)}</div><div class="cl">{esc(rl)}</div></div>'
        f'</div><div class="punch" id="tw_p">{words_spans(b["line"], "tw")}</div></div>')
    beat_shell(c, b, i, inner)
    reveal_words(c, "#tw_h .tw", b["t0"] + 0.15, 0.09)
    c.tw(f'tl.fromTo("#tw_l",{{x:-160,opacity:0,rotationY:14}},{{x:0,opacity:1,rotationY:7,duration:0.6,ease:"power3.out"}},{t_l:.3f});')
    c.tw(f'tl.fromTo("#tw_r",{{x:160,opacity:0,rotationY:-14}},{{x:0,opacity:1,rotationY:-7,duration:0.6,ease:"power3.out"}},{t_r:.3f});')
    reveal_words(c, "#tw_p .tw", t_line, 0.07)
    # USB slot na radiu blikne (konecna pulzna dvojica, nie loop)
    c.tw(f'tl.fromTo("#twcs_usb",{{opacity:0.4}},{{opacity:1,duration:0.3,ease:"power2.out"}},{t_l + 0.5:.3f});')
    c.tw(f'tl.fromTo("#twcs_usb",{{opacity:1}},{{opacity:0.55,duration:0.3,yoyo:false}},{t_l + 0.9:.3f});')
    c.tw(f'tl.to("#twcs_usb",{{opacity:1,duration:0.3}},{t_l + 1.2:.3f});')
    c.sfx += [(t_l, "tick"), (t_r, "tick")]


def tpl_outro_typeon(c, b, i, words, S):
    t_type = cue_time(words, b["t0"], b["t1"], b["cues"][0][0]) - 1.2
    txt = b["type_text"]
    chars = "".join(f'<span class="ch">{esc(ch)}</span>' for ch in txt)
    inner = (f'<div class="titlewrap"><div class="outroart"><div id="ot_port">{svglib.usb_port(S, "otp", 430, 320)}</div>'
             f'<div class="crownbox" id="ot_cr">{svglib.crown(S, "otcr", 190, 132)}</div>'
             f'<div class="smanbox" id="ot_sm">{svglib.stickman(S, "otsm", 230, 340)}</div></div>'
             f'<div class="typeline" id="ot_t">{chars}<span class="caret" id="ot_c"></span></div></div>')
    beat_shell(c, b, i, inner)
    c.tw(f'tl.fromTo("#ot_port",{{opacity:0,y:24}},{{opacity:1,y:0,duration:0.5,ease:"power3.out"}},{b["t0"] + 0.15:.3f});')
    c.tw(f'tl.fromTo("#ot_sm",{{opacity:0,x:40}},{{opacity:1,x:0,duration:0.5,ease:"power3.out"}},{b["t0"] + 0.4:.3f});')
    n = len(txt)
    per = 0.055
    c.tw(f'tl.fromTo("#ot_t .ch",{{opacity:0}},{{opacity:1,duration:0.01,ease:"none",stagger:{per}}},{t_type:.3f});')
    # koruna DOPADNE na port presne na slovo "founder"
    t_cr = t_type + 1.2
    c.tw(f'tl.fromTo("#ot_cr",{{opacity:0,y:-240,rotation:-14}},{{opacity:1,y:0,rotation:-7,duration:0.5,ease:"power2.in"}},{t_cr:.3f});')
    c.tw(f'tl.to("#ot_port",{{y:8,duration:0.12,ease:"power2.out"}},{t_cr + 0.48:.3f});')
    c.tw(f'tl.to("#ot_port",{{y:0,duration:0.25,ease:"power3.out"}},{t_cr + 0.6:.3f});')
    c.sfx.append((t_cr + 0.5, "tick"))
    for k in range(6):
        c.tw(f'tl.set("#ot_c",{{opacity:{k % 2}}},{t_type + n * per + 0.25 + 0.4 * k:.3f});')


TPLS = {"hook_kinetic": tpl_hook_kinetic, "titlecard": tpl_titlecard, "image_focus": tpl_svg_focus,
        "list_build": tpl_list_build, "stat_countup": tpl_stat_countup, "twist_split": tpl_twist_split,
        "outro_typeon": tpl_outro_typeon}

GRAIN_URI = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>"
             "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' seed='7'/>"
             "<feColorMatrix type='saturate' values='0'/></filter>"
             "<rect width='240' height='240' filter='url(%23n)' opacity='0.55'/></svg>")


def build_html(style_key, total, comp):
    S = STYLES[style_key]
    css = f"""
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:{S['bg']}}}
@font-face{{font-family:Main;src:url('public/{S['font_file']}')}}
#root{{position:relative;width:{W}px;height:{H}px;font-family:Main,'Comic Sans MS',sans-serif;color:{S['ink']}}}
.bgfield{{position:absolute;inset:0;background:radial-gradient(circle at 50% 42%,{S['bg']} 52%,{S['bg2']} 100%)}}
.grain{{position:absolute;inset:0;background-image:url("{GRAIN_URI}");opacity:{S['grain']};pointer-events:none}}
.vign{{position:absolute;inset:0;background:radial-gradient(circle at 50% 50%,transparent 62%,rgba(0,0,0,0.16) 100%)}}
.cam{{position:absolute;inset:0;transform-origin:50% 46%}}
.hooksplit{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:80px;padding:0 100px}}
.hookcol{{display:flex;flex-direction:column;gap:30px;align-items:flex-start}}
.hookart{{flex:none}}
.slam{{font-size:96px;font-weight:700;letter-spacing:1px}}
.titlewrap{{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:26px}}
.kicker{{font-size:34px;letter-spacing:6px;color:{S['muted']}}}
.bigtitle{{font-size:150px;font-weight:700;text-align:center}}
.underline{{height:10px;background:{S['accent']};border-radius:6px}}
.split{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:90px;padding:0 110px}}
.side{{flex:1;display:flex;flex-direction:column;gap:30px;justify-content:center}}
.headline{{font-size:96px;font-weight:700;line-height:1.12}}
.headline.center{{text-align:center}}
.frame{{position:relative;width:760px;height:570px;background:{S['card']};border-radius:14px;
  box-shadow:14px 14px 0 {S['accent']},0 18px 42px rgba(0,0,0,0.18);flex:none}}
.frame.art{{background:linear-gradient(180deg,{S['card']} 0%,{S['bg2']} 100%)}}
.artcenter{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}}
.plugfly{{position:absolute;left:50%;top:50%;margin-left:-40px;margin-top:-40px}}
.artside{{position:relative;flex:none;display:flex;align-items:center;gap:30px}}
.miniport{{margin-bottom:-40px}}
.svgbox{{display:flex;align-items:center;justify-content:center;height:250px}}
.plugrow{{height:100px;display:flex;align-items:center;justify-content:center}}
.cardart{{display:flex;align-items:center;justify-content:center;height:320px}}
.outroart{{display:flex;align-items:flex-end;gap:40px;position:relative}}
.crownbox{{position:absolute;left:118px;top:-88px}}
.smanbox{{margin-bottom:-16px}}
#if_svg{{position:absolute;inset:10px;width:calc(100% - 20px);height:calc(100% - 20px)}}
#if_ell{{fill:none;stroke:{S['accent2']};stroke-width:9;stroke-linecap:round}}
.label{{position:absolute;left:24px;bottom:-64px;font-size:40px;color:{S['muted']}}}
.statlab{{font-size:52px;color:{S['muted']}}}
.titleart{{margin-bottom:-8px}}
.listwrap{{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:70px}}
.row{{display:flex;gap:110px}}
.row.tilt{{perspective:1400px}}
.cell{{display:flex;flex-direction:column;align-items:center;gap:22px}}
.circle{{width:330px;height:330px;border-radius:50%;overflow:hidden;background:{S['card']};
  box-shadow:0 14px 34px rgba(0,0,0,0.2),0 0 0 10px {S['card']}}}
.circle img{{width:100%;height:100%;object-fit:cover}}
.cl{{font-size:42px;font-weight:700}}
.sublab{{font-size:46px;color:{S['muted']};margin-top:-34px}}
.card{{width:520px;background:{S['card']};border-radius:16px;padding:16px 16px 12px;box-shadow:0 18px 44px rgba(0,0,0,0.22)}}
.card img{{width:100%;height:340px;object-fit:cover;border-radius:10px}}
.card .cl{{text-align:center;padding-top:12px}}
.punch{{font-size:74px;font-weight:700;color:{S['accent']}}}
.bignum{{font-size:210px;font-weight:700;line-height:1}}
.unit{{font-size:90px;color:{S['muted']}}}
.substat{{font-size:64px;font-weight:700;color:{S['accent2']}}}
.typeline{{font-size:110px;font-weight:700}}
.caret{{display:inline-block;width:10px;height:96px;background:{S['accent']};margin-left:8px;vertical-align:-8px}}
.hud{{position:absolute;top:34px;right:44px;display:flex;flex-direction:column;align-items:center;gap:8px}}
.hudbox{{width:74px;height:74px;border-radius:16px;background:{S['card']};box-shadow:0 6px 18px rgba(0,0,0,0.18);
  display:flex;align-items:center;justify-content:center}}
.hudbox span{{display:block;width:38px;height:16px;border-radius:4px;background:#fff;border:3px solid {S['ink']}}}
.hudlab{{font-size:24px;letter-spacing:3px;color:{S['muted']}}}
#pbar{{position:absolute;left:0;top:0;height:9px;background:{S['ink']};opacity:0.92}}
.tw{{display:inline-block}}
.ch{{display:inline}}
"""
    html_clips = "\n".join(comp.html)
    js = "\n".join(comp.js)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width={W}, height={H}"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css}</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{total:.3f}" data-width="{W}" data-height="{H}">
<div class="clip bgfield" data-start="0" data-duration="{total:.3f}" data-track-index="0"></div>
{html_clips}
<div class="clip hud" data-start="1.5" data-duration="{total - 1.5:.3f}" data-track-index="8" id="hud">
  <div class="hudbox"><span></span></div><div class="hudlab">WHITE</div></div>
<div class="clip" data-start="0" data-duration="{total:.3f}" data-track-index="9"><div id="pbar"></div></div>
<div class="clip grain" data-start="0" data-duration="{total:.3f}" data-track-index="10"></div>
<div class="clip vign" data-start="0" data-duration="{total:.3f}" data-track-index="11"></div>
<audio id="vo" src="public/demo_audio.wav" data-start="0" data-duration="{total:.3f}" data-track-index="12" data-volume="1"></audio>
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
tl.fromTo("#pbar",{{width:0}},{{width:{W},duration:{total:.3f},ease:"none"}},0);
tl.fromTo("#hud",{{opacity:0}},{{opacity:1,duration:0.5,ease:"power2.out"}},1.5);
{js}
window.__timelines["main"] = tl;
</script></body></html>
"""


# ---------------------------------------------------------------- main
def main():
    style_arg = None
    if "--style" in sys.argv:
        style_arg = sys.argv[sys.argv.index("--style") + 1].lower()
    do_render = "--no-render" not in sys.argv

    os.makedirs(os.path.join(PROJ, "public"), exist_ok=True)
    # projektove subory pre hyperframes CLI
    hj = os.path.join(PROJ, "hyperframes.json")
    if not os.path.exists(hj):
        json.dump({"name": "hf-demo", "version": 1}, open(hj, "w"))
        json.dump({}, open(os.path.join(PROJ, "meta.json"), "w"))

    wavp = os.path.join(PROJ, "voice.wav")
    wjp = os.path.join(PROJ, "words.json")
    if os.path.exists(wavp) and os.path.exists(wjp):
        words = json.load(open(wjp))
        # t0/t1 do beatov (ulozene vedla)
        tm = json.load(open(os.path.join(PROJ, "beats_t.json")))
        for b in BEATS:
            b["t0"], b["t1"] = tm[b["id"]]
        total = max(t1 for _, t1 in tm.values()) + 1.2
        print(f"  hlas: cache ({total:.1f}s)")
    else:
        print("  hlas: kokoro...")
        voice, total = synth_voice()
        total += 0.8
        sf.write(wavp, voice, SR)
        json.dump({b["id"]: [b["t0"], b["t1"]] for b in BEATS}, open(os.path.join(PROJ, "beats_t.json"), "w"))
        print(f"  hlas: {total:.1f}s; whisper align...")
        words = word_timings(wavp)
        json.dump(words, open(wjp, "w"))
    print(f"  slov: {len(words)}")

    # obrazky do public/
    for k, p in IMGS.items():
        if p and os.path.exists(p):
            shutil.copy(p, os.path.join(PROJ, "public", os.path.basename(p)))
    for f in ("ComicNeue-Bold.ttf", "Anton-Regular.ttf"):
        src = os.path.join(ROOT, "assets", "fonts", f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(PROJ, "public", f))

    # kompozicia (spolocna pre oba styly)
    comp = Comp()
    for i, b in enumerate(BEATS):
        TPLS[b["tpl"]](comp, b, i, words, STYLES["a"])
    # audio mix s SFX
    mixed = mix_audio(sf.read(wavp, dtype="float32")[0], total, comp.sfx)
    sf.write(os.path.join(PROJ, "public", "demo_audio.wav"), mixed, SR)

    outs = []
    for sk in (["a", "b"] if not style_arg else [style_arg]):
        html = build_html(sk, total, comp)
        with open(os.path.join(PROJ, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)
        shutil.copy(os.path.join(PROJ, "index.html"), os.path.join(PROJ, f"index_{sk}.html"))
        if do_render:
            out = os.path.join(PROJ, f"demo_{sk}.mp4")
            print(f"  render {sk} -> {out}")
            r = subprocess.run(f'npx hyperframes render --output "{out}"',
                               cwd=PROJ, capture_output=True, text=True, timeout=1800, shell=True)
            if r.returncode != 0:
                print(r.stdout[-800:])
                print(r.stderr[-800:])
                raise SystemExit(f"render {sk} zlyhal")
            outs.append(out)
    print("HOTOVO:", *outs)


if __name__ == "__main__":
    main()

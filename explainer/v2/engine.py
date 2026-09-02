#!/usr/bin/env python3
"""Explainer v2 ENGINE: spec JSON -> HyperFrames kompozicie (dlhe 16:9 + reels 9:16) -> MP4.

Vstup: spec (viď specs/usb_demo.json) = seria + intro + kapitoly s beatmi. Kazdy beat ma:
  tpl   : intro_compare | intro_grid | hook | title | focus | list | stat | compare | outro
  say   : hovoreny text (Kokoro), cues: {nazov_prvku: fraza zo say} -> reveal presne na slovo
  vizualy: {"kind": "<svglib objekt>", ...} alebo {"emoji": "🖨️"} alebo {"query": "printer"}

Poucenia z demo iteracii (LEARNINGS.md + 7 kol):
  - reveal na ZACIATKU slova (cue_time), nikdy prazdna obrazovka (prvy prvok t0+0.25)
  - power3 dojazdy, velocity-matched push seams, kamera push per beat
  - dash-kreslene prvky maju opacity 0 az do kreslenia (inak bodka)
  - pozicie markerov sa POCITAJU z layoutu, nie od oka
  - kazda scena ma vizual + deje sa nieco kazde ~2-4 s (pulzy, draw-on, travel)
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
for p in (EXP, V2):
    if p not in sys.path:
        sys.path.insert(0, p)
import icons  # noqa: E402
import svglib  # noqa: E402
import tts  # noqa: E402

SR = tts.SR
GAP = 0.35
OV = 0.5
CARD_T = 1.4           # karta kapitoly (bez reci)
ENDCARD_T = 2.8        # reel koncovka
HF_CMD = "npx -y hyperframes@0.8.4 render --workers {workers} --protocol-timeout 600000 --output \"{out}\""

STYLE = {  # paper (schvaleny)
    "bg": "#fbfbf9", "bg2": "#ececea", "ink": "#191919", "muted": "#7a7a7a",
    "accent": "#1c4ed8", "accent2": "#d62828", "card": "#ffffff", "ok": "#2e9e5b",
    "font_file": "ComicNeue-Bold.ttf", "grain": 0.05,
}
CONF_COLORS = ["#1c4ed8", "#d62828", "#f4a259", "#5b8e7d", "#ffd21f"]


# ================================================================ util
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def words_spans(text, cls="tw"):
    return "".join(f'<span class="{cls}">{esc(w)}</span> ' for w in str(text).split())


_NUMW = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
         "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}


import unicodedata


def _norm(s):
    s = unicodedata.normalize("NFKC", str(s)).replace("‑", "-").replace(" ", " ").replace(" ", " ")
    s = s.lower().replace("gbps", " gigabits per second ").replace("mbps", " megabits per second ")
    s = s.replace("mb/s", " megabytes per second ").replace("gb/s", " gigabytes per second ")
    toks = re.sub(r"[^a-z0-9 ]", " ", s).split()
    return [_NUMW.get(t, t) for t in toks]


def rel_cue(words_rel, dur, phrase, default=0.5):
    """Cas (relativne k beatu) ZACIATKU frazy. words_rel = slova s relativnymi casmi."""
    target = _norm(phrase or "")
    if not target:
        return max(0.12, default * dur)
    # slova whispera mozu byt viac-tokenove po normalizacii (napr. "10.2" -> ["10", "2"]); rozbal
    flat, owner = [], []
    for wi, w in enumerate(words_rel):
        for t in (_norm(w["w"]) or [""]):
            flat.append(t)
            owner.append(wi)

    def find(tg):
        for i in range(len(flat)):
            if flat[i:i + len(tg)] == tg:
                ws = words_rel[owner[i]]["s"]
                we = words_rel[owner[min(i + len(tg) - 1, len(flat) - 1)]]["e"]
                return max(0.12, ws + 0.12 * (we - ws))
        return None
    t = find(target)
    if t is None and len(target) > 1:
        # fallback: najdlhsi prefix frazy (cisla/jednotky casto prepise whisper inak)
        for k in range(len(target) - 1, 0, -1):
            t = find(target[:k])
            if t is not None:
                break
    return t


class CueLog:
    missing = []


def cue(b, name, default=0.5):
    """Absolutny cas reveal prvku `name` v beate b (b['_t0'] = start beatu v aktualnej kompozicii)."""
    phrase = (b.get("cues") or {}).get(name)
    t = rel_cue(b.get("_words", []), b["_dur"], phrase, default) if phrase else None
    if t is None:
        if phrase:
            CueLog.missing.append((b.get("id", b.get("tpl")), name, phrase))
        t = max(0.12, default * b["_dur"])
    return b["_t0"] + t


# ================================================================ SFX
def _env(n, peak):
    return (np.hanning(max(3, n * 2))[:n] * peak).astype(np.float32)


def sfx_whoosh(dur=0.28, vol=0.10):
    n = int(dur * SR)
    x = np.random.default_rng(7).standard_normal(n).astype(np.float32)
    y = np.zeros_like(x)
    a = np.linspace(0.02, 0.25, n)
    acc = 0.0
    for i in range(n):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y * _env(n, vol)


def sfx_tick(vol=0.10):
    n = int(0.05 * SR)
    return np.sin(2 * np.pi * 1750 * np.arange(n) / SR).astype(np.float32) * _env(n, vol)


def sfx_riser(dur=0.9, vol=0.06):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 180 + 520 * (t / dur) ** 2
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.linspace(0.1, 1, n) * vol).astype(np.float32)


def mix_audio(parts, total, events):
    out = np.zeros(int(total * SR) + SR, dtype=np.float32)
    pos = 0
    for a in parts:
        out[pos:pos + len(a)] += a
        pos += len(a)
    for t, kind in events:
        s = {"whoosh": sfx_whoosh(), "tick": sfx_tick(), "riser": sfx_riser()}[kind]
        i = int(t * SR)
        if 0 <= i < len(out) - len(s):
            out[i:i + len(s)] += s
    peak = float(np.abs(out).max() or 1.0)
    return out * min(1.0, 0.9 / peak)


# ================================================================ vizualy
SVGLIB = {"usb_port": svglib.usb_port, "usb_plug": svglib.usb_plug, "printer": svglib.printer,
          "keyboard": svglib.keyboard, "mouse": svglib.mouse, "computer_tower": svglib.computer_tower,
          "smartphone": svglib.smartphone, "car_stereo": svglib.car_stereo, "mp3_player": svglib.mp3_player,
          "crown": svglib.crown, "stickman": svglib.stickman, "music_note": svglib.music_note}


class Visuals:
    """Resolver vizualov + zoznam pouzitych ikon na instalaciu do public/."""

    def __init__(self):
        self.used = {}

    def html(self, spec, pid, w, h):
        """Vrati HTML pre vizual: svglib (animovatelne casti) alebo OpenMoji <img>."""
        if not spec:
            return ""
        if isinstance(spec, str):
            spec = {"emoji": spec}
        kind = spec.get("kind")
        if kind in SVGLIB:
            kw = {k: v for k, v in spec.items() if k not in ("kind",)}
            fn = SVGLIB[kind]
            try:
                return fn(STYLE, pid, w, h, **kw)
            except TypeError:
                return fn(STYLE, pid, w, h)
        p = icons.resolve(spec)
        if not p:
            hits = icons.search(spec.get("query") or spec.get("label") or "", 1)
            p = icons.path_for_hex(hits[0][1]) if hits else None
        if not p:
            return f'<div id="{pid}" class="missing" style="width:{w}px;height:{h}px"></div>'
        self.used[p] = True
        return f'<img id="{pid}" class="om" src="public/icons/{os.path.basename(p)}" style="width:{w}px;height:{h}px"/>'

    def is_usb(self, spec):
        return isinstance(spec, dict) and spec.get("kind") == "usb_port"


# ================================================================ kompozicia
class Comp:
    def __init__(self, mode, W, H):
        self.mode, self.W, self.H = mode, W, H
        self.html, self.js, self.sfx = [], [], []
        self.long = mode == "long"

    def clip(self, inner, start, dur, track=1, style="", cid=None):
        ida = f' id="{cid}"' if cid else ""
        self.html.append(f'<div{ida} class="clip" data-start="{start:.3f}" data-duration="{dur:.3f}" '
                         f'data-track-index="{track}" style="{style}">{inner}</div>')

    def tw(self, code):
        self.js.append(code)

    def tick(self, t):
        self.sfx.append((t, "tick"))


def beat_shell(c, b, i, inner, animate_in=True):
    t0, t1 = b["_t0"], b["_t0"] + b["_dur"]
    bid = f'b_{b["_id"]}'
    c.clip(f'<div id="{bid}_cam" class="cam">{inner}</div>', t0, (t1 - t0) + OV, track=2 + (i % 2),
           style="position:absolute;inset:0", cid=bid)
    if animate_in:
        c.tw(f'tl.fromTo("#{bid}",{{x:110,opacity:0}},{{x:0,opacity:1,duration:0.45,ease:"power3.out"}},{t0:.3f});')
        c.sfx.append((t0, "whoosh"))
    c.tw(f'tl.to("#{bid}",{{x:-110,opacity:0,duration:0.36,ease:"power2.in"}},{t1 + OV - 0.45:.3f});')
    c.tw(f'tl.fromTo("#{bid}_cam",{{scale:1.0}},{{scale:1.045,duration:{t1 - t0:.3f},ease:"power1.inOut"}},{t0:.3f});')
    return bid


def reveal_words(c, sel, at, stagger=0.07):
    c.tw(f'tl.fromTo("{sel}",{{opacity:0,y:26}},{{opacity:1,y:0,duration:0.42,ease:"power3.out",stagger:{stagger}}},{at:.3f});')


def pop(c, sel, at, dur=0.45, dx=0, dy=26, scale=None):
    frm = f"opacity:0,x:{dx},y:{dy}" + (f",scale:{scale}" if scale else "")
    to = "opacity:1,x:0,y:0" + (",scale:1" if scale else "")
    c.tw(f'tl.fromTo("{sel}",{{{frm}}},{{{to},duration:{dur},ease:"power3.out"}},{at:.3f});')


def draw(c, sel, at, dur=0.6, opacity=1):
    """Dash-kreslenie (prvok musi mat pathLength=100, dasharray/offset 100 a opacity 0 v markupu)."""
    c.tw(f'tl.set("{sel}",{{opacity:{opacity}}},{at:.3f});'
         f'tl.fromTo("{sel}",{{strokeDashoffset:100}},{{strokeDashoffset:0,duration:{dur},ease:"power2.inOut"}},{at:.3f});')


def text_layer(text, w, h, size, id_, cls="tw", extra=""):
    return f'<div id="{id_}" class="tl" style="width:{w}px;{extra}font-size:{size}px">{words_spans(text, cls)}</div>'


def scrib_svg(pid, color, w=640):
    return (f'<svg class="scrib" viewBox="0 0 {w} 120" preserveAspectRatio="none">'
            f'<path id="{pid}" d="M 8 66 C 160 38, 340 90, {w - 8} 50" pathLength="100" fill="none" stroke="{color}" '
            f'stroke-width="13" stroke-linecap="round" stroke-dasharray="100" stroke-dashoffset="100" opacity="0"/></svg>')


def ell_svg(pid, cx, cy, rx, ry, color, W, H, sw=10):
    return (f'<svg class="overlay" viewBox="0 0 {W} {H}"><ellipse id="{pid}" cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" '
            f'pathLength="100" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" '
            f'stroke-dasharray="100" stroke-dashoffset="100" opacity="0"/></svg>')


# ================================================================ sablony
def tpl_intro_compare(c, b, i, V):
    L, R = b["left"], b["right"]
    long = c.long
    vw, vh = (460, 345) if long else (440, 330)
    t_l = min(b["_t0"] + 0.25, cue(b, "left", 0.1))
    t_r = cue(b, "right", 0.35)
    t_line = cue(b, "line", 0.6)
    t_strike = cue(b, "strike", 0.85)
    lay = 'class="row" style="gap:150px"' if long else 'class="col" style="gap:40px"'
    inner = (
        f'<div class="center"><div {lay}>'
        f'<div class="cell" id="ic_l"><div class="vbox" style="height:{vh + 20}px">{V.html(L.get("vis"), "icl", vw, vh)}</div><div class="cl">{esc(L.get("label", ""))}</div></div>'
        f'<div class="cell" id="ic_r"><div class="vbox" style="height:{vh + 20}px">{V.html(R.get("vis"), "icr", vw, vh)}</div><div class="cl">{esc(R.get("label", ""))}</div></div>'
        f'</div><div class="punchline" id="ic_q" style="font-size:{82 if long else 70}px">{words_spans(b.get("line", ""))}{scrib_svg("ic_s", STYLE["accent2"])}</div></div>')
    beat_shell(c, b, i, inner, animate_in=i > 0)
    c.tw(f'tl.fromTo("#ic_l",{{opacity:0,x:-120,rotationY:12}},{{opacity:1,x:0,rotationY:0,duration:0.5,ease:"power3.out"}},{t_l:.3f});')
    c.tw(f'tl.fromTo("#ic_r",{{opacity:0,x:120,rotationY:-12}},{{opacity:1,x:0,rotationY:0,duration:0.5,ease:"power3.out"}},{t_r:.3f});')
    reveal_words(c, "#ic_q .tw", t_line)
    draw(c, "#ic_s", t_strike, 0.45)
    c.sfx += [(t_l, "tick"), (t_r, "tick"), (t_strike, "tick")]


def tpl_intro_grid(c, b, i, V, chapters, series):
    long = c.long
    n = len(chapters)
    cols = 4 if long else 2
    rows = math.ceil(n / cols)
    W, H = c.W, c.H
    # layout vypocet (pozicie potrebujeme pre kruzok)
    tw_, th_ = (210, 158) if long else (300, 225)
    lab = 34 if long else 40
    gx, gy = (60, 34) if long else (60, 40)
    cell_h = th_ + 2 + int(lab * 1.5)
    gw = cols * tw_ + (cols - 1) * gx
    gh = rows * cell_h + (rows - 1) * gy
    x0 = (W - gw) / 2
    y0 = (320 if long else 520) if rows <= 2 or not long else 300
    if not long:
        y0 = max(420, (H - gh) / 2 + 60)
    tiles = ""
    centers = []
    for k, ch in enumerate(chapters):
        r, col = divmod(k, cols)
        x = x0 + col * (tw_ + gx)
        y = y0 + r * (cell_h + gy)
        centers.append((x + tw_ / 2, y + th_ / 2))
        tiles += (f'<div class="gcell" id="vg{k}" style="left:{x:.0f}px;top:{y:.0f}px;width:{tw_}px">'
                  f'{V.html(ch.get("icon"), "vgp" + str(k), tw_, th_)}<div class="gl" style="font-size:{lab}px">{esc(ch.get("label", ch.get("name", "")))}</div></div>')
    cx, cy = centers[0]
    ecy = cy + int(lab * 0.9)
    title_size = 104 if long else 84
    title_top = 96 if long else 230
    inner = (f'<div class="stage"><div class="seriestitle" id="vg_t" style="top:{title_top}px;font-size:{title_size}px">{words_spans(series)}</div>'
             f'{tiles}{ell_svg("vg_ell", cx, ecy, tw_ * 0.8, cell_h * 0.62, STYLE["accent2"], W, H)}'
             f'<div class="stamp" id="vg_st" style="left:{cx + tw_ * 0.12:.0f}px;top:{cy - th_ * 0.5 - 80:.0f}px">{svglib.stamp_badge(STYLE, "vgstb", b.get("stamp", "PART 1"), 240, 124)}</div></div>')
    beat_shell(c, b, i, inner)
    t_grid = cue(b, "grid", 0.05)
    for k in range(n):
        c.tw(f'tl.fromTo("#vg{k}",{{opacity:0,scale:0.8,y:24}},{{opacity:1,scale:1,y:0,duration:0.4,ease:"power3.out"}},{t_grid + 0.11 * k:.3f});')
        if k % 2 == 0:
            c.tick(t_grid + 0.11 * k)
    reveal_words(c, "#vg_t .tw", cue(b, "title", 0.55), 0.08)
    for pz in b.get("pulse", []):
        t_p = cue_ph(b, pz.get("cue"))
        for k in pz.get("items", []):
            if k < n:
                c.tw(f'tl.to("#vg{k}",{{scale:1.14,duration:0.22,ease:"power2.out"}},{t_p:.3f});'
                     f'tl.to("#vg{k}",{{scale:1.0,duration:0.35,ease:"power2.inOut"}},{t_p + 0.24:.3f});')
        c.tick(t_p)
    t_mark = cue(b, "mark", 0.85)
    draw(c, "#vg_ell", t_mark, 0.6)
    c.tw(f'tl.fromTo("#vg_st",{{opacity:0,scale:1.8,rotation:-7}},{{opacity:1,scale:1,rotation:0,duration:0.3,ease:"power3.out"}},{t_mark + 0.4:.3f});')
    c.tick(t_mark)


def cue_ph(b, phrase, default=0.5):
    t = rel_cue(b.get("_words", []), b["_dur"], phrase, default) if phrase else None
    if t is None:
        t = max(0.12, default * b["_dur"])
    return b["_t0"] + t


def tpl_hook(c, b, i, V, hero):
    long = c.long
    slams = b.get("slams", [])
    rows = ""
    for k, sl in enumerate(slams):
        color = sl.get("color", "ink")
        col = {"ink": STYLE["ink"], "red": STYLE["accent2"], "blue": STYLE["accent"]}.get(color, STYLE["ink"])
        scrib = scrib_svg("hk_scrib", STYLE["accent2"]) if sl.get("strike") else ""
        rows += f'<div class="slam" id="slam{k}" style="color:{col};font-size:{96 if long else 72}px">{esc(sl["text"])}{scrib}</div>'
    hw, hh = (560, 420) if long else (620, 465)
    hero_html = V.html(hero, "hk", hw, hh)
    if long:
        inner = f'<div class="hooksplit"><div class="hookcol">{rows}</div><div class="hookart">{hero_html}</div></div>'
    else:
        inner = f'<div class="col" style="position:absolute;inset:0;justify-content:center;gap:50px;padding:0 70px"><div class="hookart">{hero_html}</div><div class="hookcol">{rows}</div></div>'
    beat_shell(c, b, i, inner)
    t00 = b["_t0"] + 0.2
    if V.is_usb(hero):
        for k, part in enumerate(("#hk_body", "#hk_hole", "#hk_tongue", "#hk_glint")):
            c.tw(f'tl.fromTo("{part}",{{opacity:0,scale:0.8,transformOrigin:"50% 50%"}},{{opacity:1,scale:1,duration:0.45,ease:"power3.out"}},{t00 + 0.18 * k:.3f});')
    else:
        pop(c, "#hk", t00, 0.55, dy=30, scale=0.85)
    c.tw(f'tl.fromTo("#hk",{{y:16}},{{y:-6,duration:{b["_dur"] - 0.4:.3f},ease:"power1.out"}},{t00:.3f});')
    strike_t = None
    for k, sl in enumerate(slams):
        t = b["_t0"] + 0.25 if k == 0 else cue_ph(b, sl.get("cue"), (k + 0.5) / (len(slams) + 0.5))
        c.tw(f'tl.fromTo("#slam{k}",{{opacity:0,scale:1.28,y:10}},{{opacity:1,scale:1,y:0,duration:0.3,ease:"power3.out"}},{t:.3f});')
        c.tick(t)
        if sl.get("strike_on"):
            strike_t = cue_ph(b, sl["strike_on"], (k + 1) / (len(slams) + 0.5))
    if strike_t is not None:
        draw(c, "#hk_scrib", strike_t, 0.45)


def tpl_title(c, b, i, V, hero):
    long = c.long
    inner = (f'<div class="center col" style="gap:26px"><div id="tc_a">{V.html(hero, "tc", 330 if long else 380, 250 if long else 285)}</div>'
             f'<div class="kicker" id="tc_k">{esc(b.get("kicker", ""))}</div>'
             f'<div class="bigtitle" id="tc_t" style="font-size:{150 if long else 112}px">{words_spans(b.get("title", ""))}</div>'
             f'<div class="underline" id="tc_u"></div></div>')
    beat_shell(c, b, i, inner)
    pop(c, "#tc_a", b["_t0"] + 0.05, 0.55, dy=-30, scale=0.9)
    reveal_words(c, "#tc_t .tw", b["_t0"] + 0.15, 0.12)
    c.tw(f'tl.fromTo("#tc_k",{{opacity:0}},{{opacity:1,duration:0.4,ease:"power2.out"}},{b["_t0"] + 0.05:.3f});')
    c.tw(f'tl.fromTo("#tc_u",{{width:0}},{{width:{560 if long else 420},duration:0.55,ease:"power3.out"}},{b["_t0"] + 0.5:.3f});')


def tpl_focus(c, b, i, V, hero):
    long = c.long
    vis = b.get("vis") or hero
    usb = V.is_usb(vis)
    fw, fh = (760, 570) if long else (760, 560)
    hw, hh = (560, 420) if long else (520, 390)
    t_head = cue(b, "head", 0.1)
    t_act = cue(b, "action", 0.45)
    t_circ = cue(b, "circle", 0.85)
    t_year = cue(b, "stamp", 0.3) if (b.get("cues") or {}).get("stamp") else t_act + 0.2
    bits = "".join(f'<div class="bit" id="if_b{k}"></div>' for k in range(5)) if usb else ""
    plug = f'<div class="plugfly" id="if_pl">{svglib.usb_plug(STYLE, "ifpl", 300, 210)}</div>' if usb else ""
    stamp = (f'<div class="stamp" id="if_st" style="right:-40px;top:-46px">{svglib.stamp_badge(STYLE, "ifstb", b["stamp"], 230, 120)}</div>'
             if b.get("stamp") else "")
    callouts = "".join(
        f'<div class="callout" id="if_c{k}"><span class="cdot" style="background:{co[0]}"></span>{esc(co[1])}</div>'
        for k, co in enumerate(b.get("callouts", [])))
    card = (f'<div class="frame art" id="if_f" style="width:{fw}px;height:{fh}px"><div class="artcenter">{V.html(vis, "ifp", hw, hh)}</div>'
            f'{plug}{bits}{stamp}{ell_svg("if_ell", fw / 2, fh / 2 - 8, fw * 0.31, fh * 0.3, STYLE["accent2"], fw, fh, 9)}'
            f'<div class="label" id="if_l">{esc(b.get("label", ""))}</div></div>')
    side = (f'<div class="side"><div class="headline" id="if_h" style="font-size:{96 if long else 80}px">{words_spans(b.get("head", ""))}</div>{callouts}</div>')
    if long:
        inner = f'<div class="split">{card}{side}</div>'
    else:
        inner = f'<div class="col" style="position:absolute;inset:0;justify-content:center;gap:60px;padding:0 90px 60px">{side}{card}</div>'
    beat_shell(c, b, i, inner)
    c.tw(f'tl.fromTo("#if_f",{{x:-90,opacity:0}},{{x:0,opacity:1,duration:0.6,ease:"power3.out"}},{b["_t0"] + 0.05:.3f});')
    reveal_words(c, "#if_h .tw", t_head, 0.09)
    if usb:
        px = -352 if long else -420
        c.tw(f'tl.fromTo("#if_pl",{{x:{px - 290},y:-65,opacity:0,rotation:-4}},{{x:{px - 78},y:-65,opacity:1,rotation:0,duration:0.55,ease:"power3.out"}},{t_act:.3f});')
        c.tw(f'tl.to("#if_pl",{{x:{px},duration:0.45,ease:"power2.in"}},{t_act + 0.65:.3f});')
        for k in range(5):
            d0 = t_act + 1.12 + 0.14 * k
            c.tw(f'tl.fromTo("#if_b{k}",{{x:-200,y:{-58 + 16 * k},opacity:0}},{{x:52,opacity:1,duration:0.5,ease:"power1.in"}},{d0:.3f});'
                 f'tl.to("#if_b{k}",{{opacity:0,duration:0.12}},{d0 + 0.5:.3f});'
                 f'tl.fromTo("#if_b{k}",{{x:-200,opacity:0}},{{x:52,opacity:1,duration:0.5,ease:"power1.in"}},{d0 + 0.9:.3f});'
                 f'tl.to("#if_b{k}",{{opacity:0,duration:0.12}},{d0 + 1.4:.3f});')
        c.tick(t_act + 1.0)
    else:
        # genericky hero: jemny "spotlight" pulz na action cue
        c.tw(f'tl.to("#ifp",{{scale:1.08,duration:0.25,ease:"power2.out"}},{t_act:.3f});tl.to("#ifp",{{scale:1,duration:0.4,ease:"power2.inOut"}},{t_act + 0.27:.3f});')
        c.tick(t_act)
    if b.get("stamp"):
        c.tw(f'tl.fromTo("#if_st",{{opacity:0,scale:1.8,rotation:-7}},{{opacity:1,scale:1,rotation:0,duration:0.3,ease:"power3.out"}},{t_year:.3f});')
    pop(c, "#if_l", t_year + 0.15, 0.45, dy=18)
    draw(c, "#if_ell", t_circ, 0.7)
    c.tick(t_circ)
    t_co = cue(b, "callouts", 0.6) if (b.get("cues") or {}).get("callouts") else t_act + 0.5
    for k in range(len(b.get("callouts", []))):
        c.tw(f'tl.fromTo("#if_c{k}",{{opacity:0,x:-26}},{{opacity:1,x:0,duration:0.45,ease:"power3.out"}},{t_co + 0.45 * k:.3f});')


def tpl_list(c, b, i, V, hero):
    """Polozky s ikonami; volitelne `hub` (vizual v strede hore) + spojovacie ciary (krizia sa = chaos)."""
    long = c.long
    items = b.get("items", [])[:4]
    n = max(1, len(items))
    W, H = c.W, c.H
    hub = b.get("hub")
    if long:
        iw, ih = (300, 230) if n <= 3 else (250, 190)
        cxs = [W / 2 + (k - (n - 1) / 2) * (530 if n <= 3 else 420) for k in range(n)]
        ytop = 640 if hub else 470
        hub_pos = (W / 2 - 125, 190)
        head_top, sub_top = 30, 156
    else:
        iw, ih = (270, 205) if n <= 3 else (230, 175)
        if n <= 2:
            cxs = [W / 2 + (k - (n - 1) / 2) * 460 for k in range(n)]
        else:
            cxs = [W / 2 + (k - (n - 1) / 2) * 330 for k in range(n)]
        ytop = 1080 if hub else 860
        hub_pos = (W / 2 - 125, 560)
        head_top, sub_top = 250, 380
    cells = ""
    plug_kinds = ["db25", "din", "ps2", "din"]
    for k, it in enumerate(items):
        sub = (f'<div class="plugrow" id="lbp{k}">{svglib.old_plug(STYLE, "lbpl" + str(k), plug_kinds[k], 88, 88)}</div>'
               if it.get("plug") else "")
        cells += (f'<div class="acell" id="lb{k}" style="left:{cxs[k] - 170:.0f}px;top:{ytop}px">'
                  f'<div class="vbox" style="height:{ih + 20}px">{V.html(it.get("vis"), "lbv" + str(k), iw, ih)}</div>'
                  f'{sub}<div class="cl">{esc(it.get("label", ""))}</div></div>')
    cables = ""
    if hub:
        hx, hy = hub_pos[0] + 125, hub_pos[1] + 160
        tgt = [(hx - 35, hy - 10), (hx + 45, hy + 45), (hx + 18, hy + 100), (hx - 40, hy + 60)]
        for k in range(n):
            sx = cxs[k]
            sy = ytop + ih + (110 if items[k].get("plug") else 20)
            tx, ty = tgt[k % 4]
            bend = (sx - W / 2) * -0.9
            cables += (f'<path id="lbc{k}" d="M {sx:.0f} {sy:.0f} C {sx:.0f} {sy - 250:.0f}, {W / 2 + bend:.0f} {ty + 260:.0f}, {tx:.0f} {ty:.0f}" '
                       f'pathLength="100" fill="none" stroke="{STYLE["ink"]}" stroke-width="10" stroke-linecap="round" '
                       f'opacity="0" stroke-dasharray="100" stroke-dashoffset="100"/>')
    hub_html = (f'<div class="towerbox" id="lb_t" style="left:{hub_pos[0]:.0f}px;top:{hub_pos[1]:.0f}px">{V.html(hub, "lbhub", 250, 320)}</div>'
                if hub else "")
    mess = f'<div class="mess" id="lb_m" style="left:{W / 2 - 260:.0f}px;top:{hub_pos[1] + 370:.0f}px">?!</div>' if hub else ""
    inner = (f'<div class="stage"><div class="headline tcenter abs" id="lb_h" style="top:{head_top}px;font-size:{96 if long else 80}px">{words_spans(b.get("head", ""))}</div>'
             f'<div class="sublab abs" id="lb_s" style="top:{sub_top}px">{esc((b.get("sub") or {}).get("text", ""))}</div>'
             f'{hub_html}<svg class="overlay" viewBox="0 0 {W} {H}">{cables}</svg>{cells}{mess}</div>')
    beat_shell(c, b, i, inner)
    reveal_words(c, "#lb_h .tw", b["_t0"] + 0.15, 0.09)
    if hub:
        pop(c, "#lb_t", b["_t0"] + 0.4, 0.55, dy=-30)
    if b.get("sub"):
        pop(c, "#lb_s", cue_ph(b, b["sub"].get("cue"), 0.25), 0.45, dy=16)
    last = b["_t0"]
    for k, it in enumerate(items):
        t = cue_ph(b, it.get("cue"), (k + 1) / (n + 1))
        if k == 0:
            t = min(t, b["_t0"] + 1.6)          # headline sam na scene max 1.6 s
        t = max(t, last + 0.25)                 # nikdy pred predoslou polozkou
        last = max(last, t)
        c.tw(f'tl.fromTo("#lb{k}",{{opacity:0,scale:0.82,y:30}},{{opacity:1,scale:1,y:0,duration:0.5,ease:"power3.out"}},{t:.3f});')
        if it.get("plug"):
            c.tw(f'tl.fromTo("#lbp{k}",{{opacity:0,y:-26,rotation:-10}},{{opacity:1,y:0,rotation:0,duration:0.4,ease:"power3.out"}},{t + 0.3:.3f});')
        if hub:
            draw(c, f"#lbc{k}", t + 0.45, 0.7, 0.85)
        c.tick(t)
    if hub:
        t_m = min(last + 0.9, b["_t0"] + b["_dur"] - 0.4)
        c.tw(f'tl.fromTo("#lb_m",{{opacity:0,scale:0.5}},{{opacity:1,scale:1,duration:0.35,ease:"power3.out"}},{t_m:.3f});'
             f'tl.to("#lb_t",{{x:6,duration:0.07}},{t_m + 0.05:.3f});tl.to("#lb_t",{{x:-6,duration:0.07}},{t_m + 0.12:.3f});tl.to("#lb_t",{{x:0,duration:0.08}},{t_m + 0.19:.3f});')


def tpl_stat(c, b, i, V, hero):
    long = c.long
    t_count = cue(b, "count", 0.2) - 0.15
    t_sub = cue(b, "sub", 0.65)
    vis = b.get("vis")
    travel = b.get("travel")   # {"to": vis, "seconds": 3}
    art = V.html(vis, "scp", 300 if long else 340, 520 if long else 590) if vis else ""
    to_html = (f'<div class="miniport" id="sc_mp">{V.html(travel.get("to"), "scto", 260, 195)}</div>' if travel else "")
    timer = ""
    if travel:
        secs = int(travel.get("seconds", 3))
        timer = '<div class="timer">' + "".join(f'<span class="tick" id="sc_t{k}">{k + 1}s</span>' for k in range(secs)) + "</div>"
    token = '<div class="token" id="sc_tok"></div>' if travel else ""
    num = f'<div class="bignum" id="sc_n" style="font-size:{210 if long else 170}px">{b.get("num_start", "0.0")} <span class="unit">{esc(b.get("unit", ""))}</span></div>'
    side = (f'<div class="side">{num}<div class="statlab" id="sc_l">{esc(b.get("label", ""))}</div>'
            f'<div class="substat" id="sc_s">{esc(b.get("sub", ""))}</div></div>')
    artside = f'<div class="artside" id="sc_f">{art}{token}{to_html}{timer}</div>' if art else ""
    if long:
        inner = f'<div class="split">{side}{artside}</div>'
    else:
        inner = f'<div class="col" style="position:absolute;inset:0;justify-content:center;gap:60px;padding:0 90px">{side}{artside}</div>'
    beat_shell(c, b, i, inner)
    dec = int(b.get("decimals", 1))
    c.tw(f'var o{b["_id"]}={{v:{float(b.get("num_from", 0))}}};tl.to(o{b["_id"]},{{v:{float(b["num_end"])},duration:1.3,ease:"power2.out",onUpdate:function(){{'
         f'document.getElementById("sc_n").childNodes[0].nodeValue=o{b["_id"]}.v.toFixed({dec})+" ";}}}},{t_count:.3f});')
    c.tw(f'tl.fromTo("#sc_n",{{opacity:0,scale:0.8}},{{opacity:1,scale:1,duration:1.3,ease:"power2.out"}},{t_count:.3f});')
    pop(c, "#sc_l", t_count + 0.4, 0.4, dy=16)
    pop(c, "#sc_s", t_sub, 0.5, dy=22)
    if art:
        c.tw(f'tl.fromTo("#sc_f",{{x:90,opacity:0}},{{x:0,opacity:1,duration:0.6,ease:"power3.out"}},{b["_t0"] + 0.1:.3f});')
    if travel:
        secs = int(travel.get("seconds", 3))
        c.tw(f'tl.fromTo("#sc_mp",{{opacity:0}},{{opacity:1,duration:0.4,ease:"power2.out"}},{t_sub - 0.2:.3f});')
        c.tw(f'tl.fromTo("#sc_tok",{{x:0,y:0,opacity:0}},{{opacity:1,duration:0.2}},{t_sub:.3f});'
             f'tl.to("#sc_tok",{{x:{300 if long else 340},duration:{secs * 0.85:.2f},ease:"none"}},{t_sub:.3f});'
             f'tl.to("#sc_tok",{{opacity:0,duration:0.2}},{t_sub + secs * 0.85:.3f});')
        for k in range(secs):
            c.tw(f'tl.fromTo("#sc_t{k}",{{opacity:0,scale:0.7}},{{opacity:1,scale:1,duration:0.25,ease:"power3.out"}},{t_sub + 0.4 + 0.85 * k:.3f});')
            c.tick(t_sub + 0.4 + 0.85 * k)
    c.sfx.append((t_count, "riser"))


def tpl_compare(c, b, i, V, hero):
    long = c.long
    L, R = b["left"], b["right"]
    c_l = cue_ph(b, L.get("cue"), 0.3)
    c_r = cue_ph(b, R.get("cue"), 0.55)
    # karty nikdy necakaju na cue dlhsie ako ~1.3/2.1 s (prazdna scena = smrt); cue spusti badge + pulz
    t_l = min(c_l, b["_t0"] + 1.3)
    t_r = min(c_r, b["_t0"] + 2.1)
    t_line = cue(b, "line", 0.8)
    cw, chh = (520, 340) if long else (440, 300)
    ekg = ""
    if b.get("ekg"):
        ekg = (f'<svg class="ekgi" viewBox="0 0 900 120" style="width:{900 if long else 760}px;height:{120 if long else 100}px;margin:-30px 0"><path id="cp_ekg" d="M 0 60 L 200 60 L 240 60 L 270 18 L 300 104 L 330 40 L 360 70 L 390 60 L 640 60 L 670 22 L 700 100 L 730 60 L 900 60" '
               f'pathLength="100" fill="none" stroke="{STYLE["accent2"]}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round" '
               f'stroke-dasharray="100" stroke-dashoffset="100" opacity="0"/></svg>')
    notes = ""
    if R.get("notes"):
        notes = ('<div class="notes">' + "".join(svglib.music_note(STYLE, f"cp_n{k}", 56 - 6 * k, 72 - 8 * k) for k in range(3)) + "</div>")

    def card(cid, X, okid, extra=""):
        return (f'<div class="card" id="{cid}" style="width:{cw}px"><div class="okbadge" id="{okid}">✓</div>{extra}'
                f'<div class="cardart" style="height:{chh}px">{V.html(X.get("vis"), cid + "v", cw - 80, chh - 40)}</div><div class="cl">{esc(X.get("label", ""))}</div></div>')
    row = f'<div class="row tilt" style="gap:{110 if long else 50}px">{card("cp_l", L, "cp_okl")}{card("cp_r", R, "cp_okr", notes)}</div>'
    if not long:
        row = f'<div class="col" style="gap:40px">{card("cp_l", L, "cp_okl")}{card("cp_r", R, "cp_okr", notes)}</div>'
    inner = (f'<div class="center col" style="gap:{70 if long else 50}px"><div class="headline tcenter" id="cp_h" style="font-size:{96 if long else 80}px">{words_spans(b.get("head", ""))}</div>'
             f'{ekg}{row}<div class="punch" id="cp_p" style="font-size:{74 if long else 60}px">{words_spans(b.get("line", ""))}</div></div>')
    beat_shell(c, b, i, inner)
    reveal_words(c, "#cp_h .tw", b["_t0"] + 0.15, 0.09)
    if b.get("ekg"):
        t_e = cue_ph(b, b["ekg"], 0.2)
        c.tw(f'tl.set("#cp_ekg",{{opacity:1}},{t_e:.3f});tl.fromTo("#cp_ekg",{{strokeDashoffset:100}},{{strokeDashoffset:0,duration:1.1,ease:"none"}},{t_e:.3f});')
        c.tick(t_e + 0.35)
        c.tick(t_e + 0.85)
    c.tw(f'tl.fromTo("#cp_l",{{x:-160,opacity:0,rotationY:14}},{{x:0,opacity:1,rotationY:{7 if long else 0},duration:0.6,ease:"power3.out"}},{t_l:.3f});')
    c.tw(f'tl.fromTo("#cp_r",{{x:160,opacity:0,rotationY:-14}},{{x:0,opacity:1,rotationY:{-7 if long else 0},duration:0.6,ease:"power3.out"}},{t_r:.3f});')
    for cid, okid, tc, tin in (("#cp_l", "#cp_okl", c_l, t_l), ("#cp_r", "#cp_okr", c_r, t_r)):
        tb = max(tc, tin + 0.7)
        c.tw(f'tl.fromTo("{okid}",{{opacity:0,scale:1.7}},{{opacity:1,scale:1,duration:0.3,ease:"power3.out"}},{tb:.3f});')
        c.tw(f'tl.to("{cid}",{{scale:1.06,duration:0.18,ease:"power2.out"}},{tb:.3f});tl.to("{cid}",{{scale:1,duration:0.3,ease:"power3.out"}},{tb + 0.18:.3f});')
    if R.get("notes"):
        for k in range(3):
            c.tw(f'tl.fromTo("#cp_n{k}",{{opacity:0,y:20,x:0,rotation:-8}},{{opacity:1,y:-110,x:{18 + 26 * k},rotation:8,duration:0.9,ease:"power1.out"}},{t_r + 0.5 + 0.4 * k:.3f});'
                 f'tl.to("#cp_n{k}",{{opacity:0,duration:0.3}},{t_r + 1.2 + 0.4 * k:.3f});')
    reveal_words(c, "#cp_p .tw", t_line, 0.07)
    c.sfx += [(t_l, "tick"), (t_r, "tick")]


def tpl_outro(c, b, i, V, hero):
    long = c.long
    t_key = cue(b, "key", 0.85)
    t_type = t_key - 1.25
    txt = b.get("type_text", "")
    chars = "".join(f'<span class="ch">{esc(ch)}</span>' for ch in txt)
    conf = "".join(f'<div class="cf" id="ot_cf{k}" style="background:{CONF_COLORS[k % 5]}"></div>' for k in range(10))
    hw, hh = (430, 320) if long else (460, 345)
    inner = (f'<div class="center col" style="gap:30px"><div class="outroart"><div id="ot_port">{V.html(hero, "otp", hw, hh)}<div class="confbox">{conf}</div></div>'
             f'<div class="crownbox" id="ot_cr" style="left:{hw * 0.27:.0f}px;top:-58px">{svglib.crown(STYLE, "otcr", 190, 132)}</div>'
             f'<div class="smanbox" id="ot_sm">{svglib.stickman(STYLE, "otsm", 230, 340)}</div></div>'
             f'<div class="typeline" id="ot_t" style="font-size:{110 if long else 84}px">{chars}<span class="caret" id="ot_c"></span></div></div>')
    beat_shell(c, b, i, inner)
    pop(c, "#ot_port", b["_t0"] + 0.15, 0.5, dy=24)
    pop(c, "#ot_sm", b["_t0"] + 0.4, 0.5, dx=40, dy=0)
    for k, rot in enumerate((16, -12, 10, 0)):
        c.tw(f'tl.to("#otsm_arm",{{rotation:{rot},transformOrigin:"12% 8%",duration:0.3,ease:"power2.inOut"}},{b["_t0"] + 0.9 + 0.3 * k:.3f});')
    n = len(txt)
    per = 0.055
    c.tw(f'tl.fromTo("#ot_t .ch",{{opacity:0}},{{opacity:1,duration:0.01,ease:"none",stagger:{per}}},{t_type:.3f});')
    t_cr = t_key - 0.45
    c.tw(f'tl.fromTo("#ot_cr",{{opacity:0,y:-240,rotation:-14}},{{opacity:1,y:0,rotation:-7,duration:0.5,ease:"power2.in"}},{t_cr:.3f});')
    c.tw(f'tl.to("#ot_port",{{y:8,duration:0.12,ease:"power2.out"}},{t_cr + 0.48:.3f});tl.to("#ot_port",{{y:0,duration:0.25,ease:"power3.out"}},{t_cr + 0.6:.3f});')
    confp = [(-150, -190, -40), (-90, -240, 25), (-20, -260, -15), (60, -235, 30), (130, -185, -25),
             (-120, -140, 40), (100, -150, -35), (20, -210, 15), (-60, -230, -30), (160, -120, 20)]
    for k, (dx, dy, rot) in enumerate(confp):
        c.tw(f'tl.fromTo("#ot_cf{k}",{{opacity:0,x:0,y:0,rotation:0}},{{opacity:1,x:{dx},y:{dy},rotation:{rot},duration:0.45,ease:"power2.out"}},{t_cr + 0.5:.3f});'
             f'tl.to("#ot_cf{k}",{{y:{dy + 130},opacity:0,rotation:{rot * 2},duration:0.55,ease:"power1.in"}},{t_cr + 0.95:.3f});')
    c.tick(t_cr + 0.5)
    for k in range(6):
        c.tw(f'tl.set("#ot_c",{{opacity:{k % 2}}},{t_type + n * per + 0.25 + 0.4 * k:.3f});')


def tpl_chapter_card(c, b, i, V, chapter, idx, total):
    long = c.long
    inner = (f'<div class="center col" style="gap:24px"><div id="cc_a">{V.html(chapter.get("icon"), "ccv", 420 if long else 480, 315 if long else 360)}</div>'
             f'<div class="bigtitle" id="cc_t" style="font-size:{120 if long else 96}px">{esc(chapter.get("label") or chapter.get("name", ""))}</div>'
             f'<div class="kicker" id="cc_n">{idx + 1} / {total}</div></div>')
    beat_shell(c, b, i, inner)
    pop(c, "#cc_a", b["_t0"] + 0.05, 0.5, dy=-24, scale=0.9)
    pop(c, "#cc_t", b["_t0"] + 0.25, 0.45, dy=20)
    c.tw(f'tl.fromTo("#cc_n",{{opacity:0}},{{opacity:1,duration:0.35}},{b["_t0"] + 0.5:.3f});')


def tpl_endcard(c, b, i, V, spec):
    inner = (f'<div class="center col" style="gap:60px;padding:0 80px"><div class="bigtitle" id="ec_t" style="font-size:76px;text-align:center">{words_spans(spec.get("series", ""))}</div>'
             f'<div class="punch" id="ec_c" style="font-size:64px;color:{STYLE["accent"]};text-align:center">{esc(spec.get("cta", "Full video on YouTube: link in bio"))}</div>'
             f'<div id="ec_s">{svglib.stickman(STYLE, "ecsm", 230, 340)}</div></div>')
    beat_shell(c, b, i, inner)
    reveal_words(c, "#ec_t .tw", b["_t0"] + 0.1, 0.06)
    pop(c, "#ec_c", b["_t0"] + 0.7, 0.45, dy=20)
    pop(c, "#ec_s", b["_t0"] + 0.4, 0.5, dy=30)


# ================================================================ CSS / HTML
GRAIN_URI = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>"
             "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' seed='7'/>"
             "<feColorMatrix type='saturate' values='0'/></filter><rect width='240' height='240' filter='url(%23n)' opacity='0.55'/></svg>")


def css(W, H, long):
    S = STYLE
    return f"""
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:{S['bg']}}}
@font-face{{font-family:Main;src:url('public/{S['font_file']}')}}
#root{{position:relative;width:{W}px;height:{H}px;font-family:Main,'Comic Sans MS',sans-serif;color:{S['ink']}}}
.bgfield{{position:absolute;inset:0;background:radial-gradient(circle at 50% 42%,{S['bg']} 52%,{S['bg2']} 100%)}}
.grain{{position:absolute;inset:0;background-image:url("{GRAIN_URI}");opacity:{S['grain']};pointer-events:none}}
.vign{{position:absolute;inset:0;background:radial-gradient(circle at 50% 50%,transparent 62%,rgba(0,0,0,0.16) 100%)}}
.cam{{position:absolute;inset:0;transform-origin:50% 46%}}
.stage{{position:absolute;inset:0}}
.center{{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:center}}
.col{{display:flex;flex-direction:column;align-items:center}}
.row{{display:flex;align-items:flex-start}}
.row.tilt{{perspective:1400px}}
.abs{{position:absolute;left:0;right:0}}
.tw{{display:inline-block}}
.ch{{display:inline}}
.tl{{font-weight:700;line-height:1.12}}
.cell{{display:flex;flex-direction:column;align-items:center;gap:14px}}
.vbox{{display:flex;align-items:center;justify-content:center}}
.cl{{font-size:{42 if long else 40}px;font-weight:700}}
.punchline{{font-size:82px;font-weight:700;position:relative;margin-top:10px}}
.scrib{{position:absolute;left:-12px;right:-12px;top:0;bottom:0;width:calc(100% + 24px);height:100%}}
.overlay{{position:absolute;inset:0;width:100%;height:100%}}
.seriestitle{{position:absolute;left:40px;right:40px;text-align:center;font-weight:700}}
.gcell{{position:absolute;display:flex;flex-direction:column;align-items:center;gap:2px}}
.gl{{font-weight:700;color:{S['muted']}}}
.stamp{{position:absolute}}
.hooksplit{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:80px;padding:0 100px}}
.hookcol{{display:flex;flex-direction:column;gap:30px;align-items:flex-start}}
.hookart{{flex:none}}
.slam{{font-weight:700;letter-spacing:1px;position:relative}}
.kicker{{font-size:34px;letter-spacing:6px;color:{S['muted']}}}
.bigtitle{{font-weight:700;text-align:center}}
.underline{{height:10px;background:{S['accent']};border-radius:6px}}
.split{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:90px;padding:0 110px}}
.side{{flex:1;display:flex;flex-direction:column;gap:30px;justify-content:center}}
.headline{{font-weight:700;line-height:1.12}}
.tcenter{{text-align:center}}
.frame{{position:relative;background:{S['card']};border-radius:14px;box-shadow:14px 14px 0 {S['accent']},0 18px 42px rgba(0,0,0,0.18);flex:none}}
.frame.art{{background:linear-gradient(180deg,{S['card']} 0%,{S['bg2']} 100%)}}
.artcenter{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}}
.plugfly{{position:absolute;left:50%;top:50%;margin-left:-40px;margin-top:-40px}}
.bit{{position:absolute;left:50%;top:50%;width:26px;height:26px;border-radius:6px;background:{S['accent']};opacity:0}}
.label{{position:absolute;left:24px;bottom:-64px;font-size:40px;color:{S['muted']}}}
.callout{{font-size:46px;color:{S['muted']};display:flex;align-items:center;gap:18px}}
.cdot{{display:inline-block;width:26px;height:26px;border-radius:50%;flex:none}}
.sublab{{font-size:46px;color:{S['muted']};text-align:center}}
.towerbox{{position:absolute}}
.acell{{position:absolute;width:340px;display:flex;flex-direction:column;align-items:center;gap:6px}}
.plugrow{{height:100px;display:flex;align-items:center;justify-content:center}}
.mess{{position:absolute;font-size:96px;font-weight:700;color:{S['accent2']};transform:rotate(-8deg)}}
.bignum{{font-weight:700;line-height:1}}
.unit{{font-size:0.43em;color:{S['muted']}}}
.statlab{{font-size:52px;color:{S['muted']}}}
.substat{{font-size:64px;font-weight:700;color:{S['accent2']}}}
.artside{{position:relative;flex:none;display:flex;align-items:center;gap:30px}}
.miniport{{margin-bottom:-40px}}
.token{{position:absolute;left:120px;top:45%;width:34px;height:34px;border-radius:7px;background:#8ecae6;border:4px solid {S['ink']};opacity:0}}
.timer{{position:absolute;left:40px;top:-70px;display:flex;gap:26px}}
.tick{{font-size:52px;font-weight:700;color:{S['accent2']}}}
.card{{position:relative;background:{S['card']};border-radius:16px;padding:16px 16px 12px;box-shadow:0 18px 44px rgba(0,0,0,0.22)}}
.cardart{{display:flex;align-items:center;justify-content:center}}
.card .cl{{text-align:center;padding-top:12px}}
.okbadge{{position:absolute;right:22px;top:14px;font-size:64px;color:{S['ok']};font-weight:700}}
.notes{{position:absolute;left:300px;top:26px;display:flex;gap:10px}}
.punch{{font-weight:700;color:{S['accent']}}}
.ekg{{position:absolute;width:900px;height:120px}}
.outroart{{display:flex;align-items:flex-end;gap:40px;position:relative}}
.crownbox{{position:absolute}}
.smanbox{{margin-bottom:-16px}}
.confbox{{position:absolute;left:50%;top:40%;width:0;height:0}}
.cf{{position:absolute;width:20px;height:30px;border-radius:4px;opacity:0}}
.typeline{{font-weight:700}}
.caret{{display:inline-block;width:10px;height:0.9em;background:{S['accent']};margin-left:8px;vertical-align:-8px}}
.hud{{position:absolute;right:{44 if long else 34}px;top:{34 if long else 150}px;display:flex;flex-direction:column;align-items:center;gap:8px}}
.hudbox{{width:{74 if long else 90}px;height:{74 if long else 90}px;border-radius:16px;background:{S['card']};box-shadow:0 6px 18px rgba(0,0,0,0.18);display:flex;align-items:center;justify-content:center;overflow:hidden}}
.hudbox img,.hudbox svg{{width:80%;height:80%}}
.hudlab{{font-size:{24 if long else 30}px;letter-spacing:3px;color:{S['muted']}}}
#pbar{{position:absolute;left:0;top:0;height:{7 if long else 9}px;background:{S['ink']};opacity:0.92}}
.om{{object-fit:contain}}
.missing{{border:4px dashed {S['muted']};border-radius:12px}}
"""


def build_html(comp, total, hud=None, hud_start=0.0):
    W, H = comp.W, comp.H
    hud_html = ""
    hud_js = ""
    if hud:
        hud_html = (f'<div class="clip hud" data-start="{hud_start:.3f}" data-duration="{total - hud_start:.3f}" data-track-index="8" id="hud">'
                    f'<div class="hudbox">{hud[0]}</div><div class="hudlab">{esc(hud[1])}</div></div>')
        hud_js = f'tl.fromTo("#hud",{{opacity:0}},{{opacity:1,duration:0.5,ease:"power2.out"}},{hud_start:.3f});'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width={W}, height={H}"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css(W, H, comp.long)}</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{total:.3f}" data-width="{W}" data-height="{H}">
<div class="clip bgfield" data-start="0" data-duration="{total:.3f}" data-track-index="0"></div>
{chr(10).join(comp.html)}
{hud_html}
<div class="clip" data-start="0" data-duration="{total:.3f}" data-track-index="9"><div id="pbar"></div></div>
<div class="clip grain" data-start="0" data-duration="{total:.3f}" data-track-index="10"></div>
<div class="clip vign" data-start="0" data-duration="{total:.3f}" data-track-index="11"></div>
<audio id="vo" src="{comp.audio_src}" data-start="0" data-duration="{total:.3f}" data-track-index="12" data-volume="1"></audio>
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
tl.fromTo("#pbar",{{width:0}},{{width:{W},duration:{total:.3f},ease:"none"}},0);
{hud_js}
{chr(10).join(comp.js)}
window.__timelines["main"] = tl;
</script></body></html>
"""


# ================================================================ audio pipeline
def all_units(spec):
    """Vsetky hovorene jednotky v poradi dlheho videa: (uid, beat-dict)."""
    units = []
    intro = spec.get("intro") or {}
    for key in ("compare", "grid"):
        if intro.get(key) and intro[key].get("say"):
            b = intro[key]
            b["_id"] = f"intro_{key}"
            b["tpl"] = "intro_" + key
            units.append(b)
    for ci, ch in enumerate(spec["chapters"]):
        for bi, b in enumerate(ch["beats"]):
            b["_id"] = f"c{ci}b{bi}"
            b["_chapter"] = ci
            units.append(b)
    if spec.get("outro") and spec["outro"].get("say"):
        b = spec["outro"]
        b["_id"] = "outro"
        b["tpl"] = "outro"
        units.append(b)
    return units


def synth_units(units, work, voice="am_michael", speed=1.0):
    os.makedirs(work, exist_ok=True)
    tts.load(voice, speed)
    for b in units:
        p = os.path.join(work, f"u_{b['_id']}.wav")
        if not os.path.exists(p):
            a = tts.speak(b["say"])
            n = min(len(a), int(0.012 * SR))
            ramp = np.linspace(0, 1, n, dtype=np.float32)
            a[:n] *= ramp
            a[-n:] *= ramp[::-1]
            sf.write(p, a, SR)
        b["_wav"] = p
        b["_dur"] = sf.info(p).duration


def align_words(units, work):
    """Jeden whisper prechod cez vsetky jednotky (spojene) -> relativne slova per jednotka."""
    from faster_whisper import WhisperModel
    parts, cur, spans = [], 0.0, []
    for b in units:
        a, _ = sf.read(b["_wav"], dtype="float32")
        parts += [a, np.zeros(int(GAP * SR), dtype=np.float32)]
        spans.append((b, cur, cur + len(a) / SR))
        cur += len(a) / SR + GAP
    full = os.path.join(work, "_all.wav")
    sf.write(full, np.concatenate(parts), SR)
    m = WhisperModel("base.en", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(full, word_timestamps=True, language="en")
    words = [{"w": w.word.strip(), "s": max(0.0, w.start), "e": w.end} for seg in segs for w in (seg.words or [])]
    for b, s0, s1 in spans:
        b["_words"] = [{"w": w["w"], "s": w["s"] - s0, "e": w["e"] - s0} for w in words if s0 - 0.2 <= w["s"] <= s1 + 0.2]


# ================================================================ skladanie
class Seq:
    def __init__(self):
        self.t = 0.0
        self.audio = []

    def add(self, b):
        b["_t0"] = self.t
        a, _ = sf.read(b["_wav"], dtype="float32")
        self.audio += [a, np.zeros(int(GAP * SR), dtype=np.float32)]
        self.t += b["_dur"] + GAP

    def silence(self, d, b=None):
        if b is not None:
            b["_t0"] = self.t
            b["_dur"] = d
        self.audio.append(np.zeros(int(d * SR), dtype=np.float32))
        self.t += d


def hud_for(V, ch):
    return (V.html(ch.get("icon"), "hudv", 60, 60), ch.get("label") or ch.get("name", ""))


def build_long(spec, V):
    W, H = 1920, 1080
    c = Comp("long", W, H)
    seq = Seq()
    marks = []
    intro = spec.get("intro") or {}
    i = 0
    if intro.get("compare"):
        seq.add(intro["compare"])
        n1, n2 = len(c.html), len(c.js)
        tpl_intro_compare(c, intro["compare"], i, V)
        _scope_ids(c, n1, n2, "uic_")
        i += 1
    if intro.get("grid"):
        seq.add(intro["grid"])
        n1, n2 = len(c.html), len(c.js)
        tpl_intro_grid(c, intro["grid"], i, V, spec["chapters"], spec.get("series", ""))
        _scope_ids(c, n1, n2, "uig_")
        i += 1
    hud_start = seq.t
    chs = spec["chapters"]
    hero = spec.get("hero")
    for ci, ch in enumerate(chs):
        marks.append((ch.get("name") or ch.get("label"), seq.t))
        if ci > 0:
            card = {"_id": f"card{ci}", "tpl": "card"}
            seq.silence(CARD_T, card)
            n1, n2 = len(c.html), len(c.js)
            tpl_chapter_card(c, card, i, V, ch, ci, len(chs))
            _scope_ids(c, n1, n2, f"ucard{ci}_")
            i += 1
        for b in ch["beats"]:
            seq.add(b)
            run_tpl(c, b, i, V, hero, spec)
            i += 1
    if spec.get("outro") and spec["outro"].get("_wav"):
        seq.add(spec["outro"])
        n1, n2 = len(c.html), len(c.js)
        tpl_outro(c, spec["outro"], i, V, hero)
        _scope_ids(c, n1, n2, "uout_")
    total = seq.t + 0.8
    hud = hud_for(V, chs[0]) if chs else None
    return c, seq, total, marks, hud, hud_start


def build_reel(spec, V, ci):
    W, H = 1080, 1920
    c = Comp("reel", W, H)
    seq = Seq()
    ch = spec["chapters"][ci]
    hero = spec.get("hero")
    i = 0
    for b in ch["beats"]:
        seq.add(b)
        run_tpl(c, b, i, V, hero, spec)
        i += 1
    end = {"_id": "endcard", "tpl": "endcard"}
    seq.silence(ENDCARD_T, end)
    n1, n2 = len(c.html), len(c.js)
    tpl_endcard(c, end, i, V, spec)
    _scope_ids(c, n1, n2, "uend_")
    total = seq.t + 0.3
    return c, seq, total, hud_for(V, ch), 0.0


_ID_RE = re.compile(r'id="([A-Za-z_][\w-]*)"')


def _scope_ids(c, n_html, n_js, uid):
    """Vsetky id="X" v novo pridanych klipoch -> id="<uid>X" a selektory "#X" / getElementById("X") v js."""
    ids = set()
    for k in range(n_html, len(c.html)):
        ids.update(_ID_RE.findall(c.html[k]))
    if not ids:
        return
    pat = re.compile(r'id="(' + "|".join(sorted(map(re.escape, ids), key=len, reverse=True)) + r')"')
    for k in range(n_html, len(c.html)):
        c.html[k] = pat.sub(lambda m: f'id="{uid}{m.group(1)}"', c.html[k])
    sel = re.compile(r'([#"(])(' + "|".join(sorted(map(re.escape, ids), key=len, reverse=True)) + r')(?=["\s.,)\]])')
    for k in range(n_js, len(c.js)):
        js = c.js[k]
        js = re.sub(r'"#(' + "|".join(map(re.escape, ids)) + r')(?=[" .])', lambda m: f'"#{uid}{m.group(1)}', js)
        js = re.sub(r'getElementById\("(' + "|".join(map(re.escape, ids)) + r')"\)', lambda m: f'getElementById("{uid}{m.group(1)}")', js)
        c.js[k] = js


def run_tpl(c, b, i, V, hero, spec):
    n_html, n_js = len(c.html), len(c.js)
    _run_tpl_inner(c, b, i, V, hero, spec)
    _scope_ids(c, n_html, n_js, f"u{b['_id']}_")


def _run_tpl_inner(c, b, i, V, hero, spec):
    t = b.get("tpl")
    if t == "hook":
        tpl_hook(c, b, i, V, hero)
    elif t == "title":
        tpl_title(c, b, i, V, hero)
    elif t == "focus":
        tpl_focus(c, b, i, V, hero)
    elif t == "list":
        tpl_list(c, b, i, V, hero)
    elif t == "stat":
        tpl_stat(c, b, i, V, hero)
    elif t == "compare":
        tpl_compare(c, b, i, V, hero)
    elif t == "outro":
        tpl_outro(c, b, i, V, hero)
    else:
        # fallback: nadpis + hero
        b2 = dict(b, title=b.get("show", b.get("head", "")), kicker="")
        tpl_title(c, b2, i, V, hero)


# ================================================================ render
def hf_render(proj, out, workers=2):
    cmd = HF_CMD.format(workers=workers, out=out)
    r = subprocess.run(cmd, cwd=proj, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=7200, shell=True)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError("hyperframes render zlyhal:\n" + (r.stdout or "")[-1500:] + (r.stderr or "")[-800:])


def write_comp(proj, name, comp, seq, total, hud, hud_start):
    mixed = mix_audio(seq.audio, total, comp.sfx)
    wav = f"public/{name}_audio.wav"
    sf.write(os.path.join(proj, wav), mixed, SR)
    comp.audio_src = wav
    html = build_html(comp, total, hud, hud_start)
    p = os.path.join(proj, f"{name}.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    return p


def render_spec(spec, out_dir, do_long=True, do_reels=True, workers=2, only_reels=None):
    """Cely beh: TTS -> align -> kompozicie -> render. Vrati meta dict (kompatibilny s publish.py)."""
    proj = os.path.join(out_dir, "_hf")
    os.makedirs(os.path.join(proj, "public"), exist_ok=True)
    if not os.path.exists(os.path.join(proj, "hyperframes.json")):
        json.dump({"name": "explainer", "version": 1}, open(os.path.join(proj, "hyperframes.json"), "w"))
        json.dump({}, open(os.path.join(proj, "meta.json"), "w"))
    shutil.copy(os.path.join(ROOT, "assets", "fonts", STYLE["font_file"]), os.path.join(proj, "public", STYLE["font_file"]))
    units = all_units(spec)
    print(f"  hlas: {len(units)} jednotiek (kokoro)...")
    synth_units(units, os.path.join(out_dir, "_voice"), spec.get("voice", "am_michael"), float(spec.get("speed", 1.0)))
    print(f"  zarovnanie slov (whisper)...")
    align_words(units, os.path.join(out_dir, "_voice"))
    V = Visuals()
    icons.ensure()
    meta = {"series": spec.get("series"), "title": spec.get("title"), "description": spec.get("description", ""),
            "hashtags": spec.get("hashtags", []), "credits": icons.CREDIT}
    CueLog.missing.clear()
    comps = []
    if do_long:
        c, seq, total, marks, hud, hud_start = build_long(spec, V)
        comps.append(("long", c, seq, total, hud, hud_start))
        meta["chapters_ts"] = [(n, _hms(t)) for n, t in marks]
        meta["duration"] = total
    if do_reels:
        for ci, ch in enumerate(spec["chapters"]):
            if only_reels is not None and ci not in only_reels:
                continue
            c, seq, total, hud, hs = build_reel(spec, V, ci)
            comps.append((f"reel_{ci + 1:02d}_{_slug(ch.get('label') or ch.get('name'))}", c, seq, total, hud, hs))
    icons.install(list(V.used.keys()), os.path.join(proj, "public"))
    if CueLog.missing:
        print("  [cue] nenajdene (fallback stred):", CueLog.missing[:12])
    meta["cue_missing"] = CueLog.missing[:]
    meta["reels"] = []
    for name, c, seq, total, hud, hs in comps:
        html = write_comp(proj, name, c, seq, total, hud, hs)
        shutil.copy(html, os.path.join(proj, "index.html"))
        out = os.path.join(out_dir, f"{name}.mp4")
        print(f"  render {name} ({total:.0f}s)...")
        hf_render(proj, out, workers)
        if name == "long":
            meta["long"] = out
        else:
            ci = int(name.split("_")[1]) - 1
            ch = spec["chapters"][ci]
            meta["reels"].append({"path": out, "chapter": ci, "label": ch.get("label") or ch.get("name"),
                                  "name": ch.get("name"), "hook": ch.get("hook", ""), "duration": total})
    return meta


def _hms(sec):
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "_", str(t).lower()).strip("_")[:30] or "x"


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = set(a for a in sys.argv[1:] if a.startswith("--"))
    spec = json.load(open(args[0], encoding="utf-8"))
    out_dir = args[1] if len(args) > 1 else os.path.join(ROOT, "temp", "v2_out")
    os.makedirs(out_dir, exist_ok=True)
    only = None
    for f in flags:
        if f.startswith("--reel="):
            only = [int(f.split("=")[1]) - 1]
    meta = render_spec(spec, out_dir, do_long="--reels" not in flags, do_reels="--long" not in flags, only_reels=only)
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("HOTOVO", meta.get("long"), len(meta.get("reels", [])), "reels")

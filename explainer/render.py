#!/usr/bin/env python3
"""Render explainer videa zo skriptu JSON: dlhe 16:9 (YouTube) + 9:16 reels po kapitolach.

Pouzitie:
  python explainer/render.py explainer/scripts/<slug>.json            # dlhe + reels
  python explainer/render.py explainer/scripts/<slug>.json --long     # len dlhe
  python explainer/render.py explainer/scripts/<slug>.json --reels    # len reels
  python explainer/render.py ... --no-images                          # bez AI obrazkov (rychly test)

Princip: slideshow. Kazdy "beat" = jeden slajd (text + obrazok/panacik), prvky nabehnu
pop-in animaciou (10 snimok), potom drzi. Snimky -> ffmpeg concat (per-file duration).
Progress bar sa kresli vo ffmpeg (drawbox s casom), HUD kapitoly je vpaleny v slajde.
Hlas: Kokoro per beat (cache wav) - dlhe video aj reels pouzivaju tie iste kusky.
"""
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assets  # noqa: E402
import common  # noqa: E402
import tts  # noqa: E402
from assets import INK, GREY, font, draw_block, paste_center  # noqa: E402

ANIM_FRAMES = 10          # pop-in dlzka v snimkach (pri 30 fps = 0.33 s)
BEAT_GAP = 0.22           # ticho medzi beatmi
CHAPTER_CARD = 1.4        # karta kapitoly (bez reci)
CHAPTER_GAP = 0.5
OUTRO_HOLD = 1.6
ENDCARD_REEL = 2.8
POSE_CYCLE = ["present", "point_right", "shrug", "think", "arms_crossed", "idle", "wave"]


def ease_out_back(t, s=1.70158):
    t = min(max(t, 0.0), 1.0) - 1.0
    return t * t * ((s + 1) * t + s) + 1


def run(args, timeout=3600):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg fail: " + (r.stderr or "")[-1200:])
    return r


# ---------------------------------------------------------------- kontext renderu
class Ctx:
    def __init__(self, cfg, mode, spec, out_dir, use_images=True, images=None):
        e = cfg["explainer"]
        self.cfg = cfg
        self.e = e
        self.mode = mode                      # 'long' | 'reel'
        self.W = e["long_w"] if mode == "long" else e["reel_w"]
        self.H = e["long_h"] if mode == "long" else e["reel_h"]
        self.fps = int(e["fps"])
        self.spec = spec
        self.out_dir = out_dir
        self.use_images = use_images
        self.bg = assets.background(self.W, self.H)
        self.ff = cfg.get("ffmpeg", "ffmpeg")
        self._stick = {}
        self.images = images or {}            # prompt -> path (z prefetch_images)

    def stick(self, pose, h, mood="smile"):
        key = (pose, h, mood)
        if key not in self._stick:
            self._stick[key] = assets.stickman(pose, h, mood)
        return self._stick[key]

    def img(self, prompt):
        if not prompt or not self.use_images:
            return None
        return self.images.get(prompt)


# ---------------------------------------------------------------- obrazky (prefetch)
def collect_prompts(spec):
    out = []
    for ch in spec["chapters"]:
        if ch.get("icon"):
            out.append((ch["icon"], 768, 768))
        for b in ch["beats"]:
            for k in ("image", "image2", "image3"):
                if b.get(k):
                    out.append((b[k], 1024, 768))
    if spec.get("thumb_image"):
        out.append((spec["thumb_image"], 1024, 768))
    seen, uniq = set(), []
    for p in out:
        if p[0] not in seen:
            seen.add(p[0])
            uniq.append(p)
    return uniq


def prefetch_images(spec, cfg, use_images=True, workers=1):
    """Pollinations ma limit 1 request / 15 s (anonym) alebo / 5 s (token) -> 1 worker, gap riesi assets."""
    if not use_images:
        return {}
    style = cfg["explainer"]["image_style"]
    prompts = collect_prompts(spec)
    est = len(prompts) * (assets.MIN_GAP + 8) / 60
    print(f"  obrazky: {len(prompts)} promptov (~{est:.0f} min{'' if assets.POLLI_TOKEN else ', bez POLLINATIONS_TOKEN'})")
    res = {}

    def one(item):
        prompt, w, h = item
        seed = int.from_bytes(prompt.encode("utf-8")[:4].ljust(4, b"\0"), "little") % 9000 + 1
        return prompt, assets.gen_image(prompt, w, h, seed=seed, style=style)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for prompt, path in ex.map(one, prompts):
            if path:
                res[prompt] = path
            else:
                print(f"   [img] CHYBA (slajd pojde bez obrazka): {prompt[:60]}")
    print(f"  obrazky hotove: {len(res)}/{len(prompts)}")
    return res


# ---------------------------------------------------------------- hlas
def build_voice(spec, cfg, work):
    """TTS pre kazdy hovoreny kus. Ulozi wav do work/voice_<id>.wav, vrati dict id -> (path, dur)."""
    e = cfg["explainer"]
    tts.load(e["kokoro_voice"], e["kokoro_speed"], e.get("kokoro_model_dir"))
    os.makedirs(work, exist_ok=True)
    units = [("open", spec.get("hook_say", ""))]
    for ci, ch in enumerate(spec["chapters"]):
        for bi, b in enumerate(ch["beats"]):
            units.append((f"c{ci}_b{bi}", b.get("say", "")))
    units.append(("outro", (spec.get("outro") or {}).get("say", "")))
    out = {}
    total = 0.0
    for uid, text in units:
        p = os.path.join(work, f"voice_{uid}.wav")
        if not text.strip():
            continue
        if not os.path.exists(p):
            a = tts.speak(text)
            # kratky fade na okrajoch proti klikaniu
            n = min(len(a), int(0.012 * tts.SR))
            if n > 1:
                ramp = np.linspace(0, 1, n, dtype=np.float32)
                a[:n] *= ramp
                a[-n:] *= ramp[::-1]
            sf.write(p, a, tts.SR)
        info = sf.info(p)
        out[uid] = (p, info.duration)
        total += info.duration
    print(f"  hlas: {len(out)} kusov, {total / 60:.1f} min")
    return out


# ---------------------------------------------------------------- slajdy (vrstvy)
def _text_layer(text, w, h, start, min_size=30, bold=True, fill=INK, align="center", valign="middle"):
    layer = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    draw_block(layer, text, (0, 0, int(w), int(h)), start=start, min_size=min_size, bold=bold,
               fill=fill, align=align, valign=valign)
    return layer


def _framed(ctx, prompt, w, h, style="blue"):
    p = ctx.img(prompt)
    if not p:
        return None
    return assets.framed(p, w, h, style)


def _labeled(im, label, fsize):
    """Obrazok + popisok pod nim v jednej vrstve."""
    if not label:
        return im
    f = font(fsize)
    lh = int(fsize * 1.5)
    out = Image.new("RGBA", (max(im.size[0], int(ImageDraw.Draw(im).textlength(label, font=f)) + 20),
                             im.size[1] + lh), (0, 0, 0, 0))
    out.alpha_composite(im, ((out.size[0] - im.size[0]) // 2, 0))
    d = ImageDraw.Draw(out)
    tw = d.textlength(label, font=f)
    d.text(((out.size[0] - tw) / 2, im.size[1] + 6), label, font=f, fill=INK)
    return out


def layers_for_beat(ctx, beat, idx):
    """Vrati zoznam vrstiev [(img, cx, cy, order)] pre dany beat v danom mode.
    order = poradie pop-in (0 = prve)."""
    W, H = ctx.W, ctx.H
    long = ctx.mode == "long"
    typ = beat.get("type", "figure_text")
    show = beat.get("show", "")
    pose = beat.get("pose") or POSE_CYCLE[idx % len(POSE_CYCLE)]
    mood = beat.get("mood", "smile")
    L = []

    def add(im, cx, cy, order):
        if im is not None:
            L.append((im, cx, cy, order))

    # -- pomocne rozmery
    if long:
        body_start = 78
        img_w, img_h = 760, 570
    else:
        body_start = 74
        img_w, img_h = 880, 660

    if typ == "title":
        if long:
            add(_text_layer(show, 1400, 480, 108), W / 2, H / 2, 0)
        else:
            add(_text_layer(show, 900, 700, 100), W / 2, H / 2 - 40, 0)
        return L

    if typ == "image_text":
        fr = _framed(ctx, beat.get("image"), img_w, img_h)
        if fr is None:
            typ = "figure_text"
        else:
            if long:
                add(fr, 140 + fr.size[0] / 2, H / 2 + 20, 0)
                add(_text_layer(show, 820, 520, body_start), 1400, H / 2, 1)
            else:
                add(_text_layer(show, 920, 420, body_start), W / 2, 500, 1)
                add(fr, W / 2, 1150, 0)
            return L

    if typ == "figure_text":
        sh = 640 if long else 600
        sm = ctx.stick(pose, sh, mood)
        if long:
            add(sm, 470, H / 2 + 30, 0)
            add(_text_layer(show, 980, 520, body_start), 1350, H / 2, 1)
        else:
            add(_text_layer(show, 920, 440, body_start), W / 2, 520, 1)
            add(sm, W / 2, 1150, 0)
        return L

    if typ == "image_only":
        if long:
            fr = _framed(ctx, beat.get("image"), 1120, 700, "soft")
            if fr is None:
                add(_text_layer(show, 1400, 480, 100), W / 2, H / 2, 0)
                return L
            add(fr, W / 2, H / 2 - 40, 0)
            if show:
                add(_text_layer(show, 1400, 120, 54, min_size=30), W / 2, H - 120, 1)
        else:
            fr = _framed(ctx, beat.get("image"), 900, 900, "soft")
            if fr is None:
                add(_text_layer(show, 900, 700, 96), W / 2, H / 2, 0)
                return L
            add(fr, W / 2, 1000, 0)
            if show:
                add(_text_layer(show, 920, 260, 66, min_size=34), W / 2, 420, 1)
        return L

    if typ == "two_images":
        a = _framed(ctx, beat.get("image"), 620 if long else 480, 460 if long else 360)
        b = _framed(ctx, beat.get("image2"), 620 if long else 480, 460 if long else 360)
        if a is None or b is None:
            beat = dict(beat, type="image_text", image=beat.get("image") or beat.get("image2"))
            return layers_for_beat(ctx, beat, idx)
        la, lb = beat.get("label", ""), beat.get("label2", "")
        fs = 44 if long else 40
        a, b = _labeled(a, la, fs), _labeled(b, lb, fs)
        if long:
            if show:
                add(_text_layer(show, 1500, 150, 70, min_size=36), W / 2, 150, 0)
            add(a, W / 2 - 400, H / 2 + 80, 1)
            add(b, W / 2 + 400, H / 2 + 80, 2)
        else:
            if show:
                add(_text_layer(show, 920, 300, 70, min_size=36), W / 2, 460, 0)
            add(a, W / 2, 900, 1)
            add(b, W / 2, 1360, 2)
        return L

    if typ == "three_images":
        ims = [_framed(ctx, beat.get(k), 340 if long else 300, 340 if long else 300, "circle")
               for k in ("image", "image2", "image3")]
        labs = [beat.get("label", ""), beat.get("label2", ""), beat.get("label3", "")]
        if any(i is None for i in ims):
            beat = dict(beat, type="image_text")
            return layers_for_beat(ctx, beat, idx)
        fs = 40 if long else 36
        ims = [_labeled(i, l, fs) for i, l in zip(ims, labs)]
        if long:
            if show:
                add(_text_layer(show, 1500, 150, 70, min_size=36), W / 2, 150, 0)
            for k, im in enumerate(ims):
                add(im, W / 2 + (k - 1) * 520, H / 2 + 90, k + 1)
        else:
            if show:
                add(_text_layer(show, 920, 300, 70, min_size=36), W / 2, 420, 0)
            for k, im in enumerate(ims):
                add(im, W / 2 + (k - 1) * 340, 1050, k + 1)
        return L

    if typ == "stat":
        num = str(beat.get("stat", show))
        lab = beat.get("label", "") if beat.get("stat") else ""
        fr = _framed(ctx, beat.get("image"), 620 if long else 700, 460 if long else 520)
        if long:
            if fr is not None:
                add(_text_layer(num, 900, 300, 200, min_size=80), 560, H / 2 - 60, 0)
                if lab:
                    add(_text_layer(lab, 900, 160, 60, min_size=32, fill=GREY), 560, H / 2 + 150, 1)
                add(fr, 1420, H / 2, 2)
            else:
                add(_text_layer(num, 1500, 340, 230, min_size=90), W / 2, H / 2 - 80, 0)
                if lab:
                    add(_text_layer(lab, 1500, 160, 64, min_size=32, fill=GREY), W / 2, H / 2 + 170, 1)
        else:
            add(_text_layer(num, 960, 320, 190, min_size=80), W / 2, 560, 0)
            if lab:
                add(_text_layer(lab, 920, 160, 60, min_size=32, fill=GREY), W / 2, 790, 1)
            if fr is not None:
                add(fr, W / 2, 1230, 2)
        return L

    # fallback
    add(_text_layer(show, 1400 if long else 900, 480 if long else 700, 100), W / 2, H / 2, 0)
    return L


def hud_layer(ctx, chapter):
    """Ikona + nazov kapitoly (vpravo hore) - stale viditelne pocas kapitoly."""
    if chapter is None:
        return None
    label = chapter.get("label") or chapter.get("name", "")
    long = ctx.mode == "long"
    ic = ctx.img(chapter.get("icon"))
    size = 64 if long else 84
    fs = 26 if long else 30
    f = font(fs)
    d0 = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    tw = int(d0.textlength(label, font=f))
    w = max(size + 30, tw + 20)
    h = size + int(fs * 1.6) + 20
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if ic:
        circ = assets.framed(ic, size, size, "circle", border=3, offset=4)
        layer.alpha_composite(circ, ((w - circ.size[0]) // 2, 0))
    else:
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle([(w - size) // 2, 4, (w + size) // 2, size + 4], radius=12, outline=INK, width=3)
    d = ImageDraw.Draw(layer)
    d.text(((w - tw) / 2, size + 12), label, font=f, fill=INK)
    return layer


def compose(ctx, layers, p, hud=None):
    """Zloz snimku: pozadie + vrstvy s pop-in progresom p (0..1) + HUD."""
    fr = ctx.bg.copy()
    n = max(1, len(layers))
    for im, cx, cy, order in layers:
        # kazda vrstva startuje neskor (stagger), trva 60 % celkoveho okna
        start = order * (0.4 / n)
        q = (p - start) / 0.6
        if q <= 0:
            continue
        q = min(q, 1.0)
        sc = 0.82 + 0.18 * ease_out_back(q)
        al = min(1.0, q * 1.6)
        paste_center(fr, im, cx, cy, sc, al)
    if hud is not None:
        if ctx.mode == "long":
            fr.alpha_composite(hud, (ctx.W - hud.size[0] - 30, 22))
        else:
            fr.alpha_composite(hud, (ctx.W - hud.size[0] - 34, 150))
    return fr


def grid_layers(ctx, spec):
    """Cold open: mriezka vsetkych kapitol (dlazdice s popiskom)."""
    chs = spec["chapters"]
    n = len(chs)
    long = ctx.mode == "long"
    cols = 4 if long else 2
    rows = math.ceil(n / cols)
    size = (200 if rows <= 2 else 150) if long else (360 if rows <= 4 else 300)
    fs = 34 if long else 40
    gapx = 90 if long else 80
    gapy = 60 if long else 60
    L = []
    tiles = []
    for i, ch in enumerate(chs):
        icon = ctx.img(ch.get("icon"))
        label = ch.get("label") or ch.get("name", "")
        if icon:
            t = assets.tile(icon, size, label, font(fs))
        else:
            ph = Image.new("RGB", (size, size), (235, 235, 235))
            t = assets.tile(ph, size, label, font(fs))
        tiles.append(t)
    tw, th = tiles[0].size
    gw = cols * tw + (cols - 1) * gapx
    gh = rows * th + (rows - 1) * gapy
    x0 = (ctx.W - gw) / 2 + tw / 2
    y0 = (ctx.H - gh) / 2 + th / 2 + (0 if long else 40)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        # posledny riadok centrovany ak neuplny
        in_row = min(cols, n - r * cols)
        off = (cols - in_row) * (tw + gapx) / 2
        L.append((t, x0 + c * (tw + gapx) + off, y0 + r * (th + gapy), i))
    return L


def chapter_card_layers(ctx, ch, idx, total):
    long = ctx.mode == "long"
    label = ch.get("label") or ch.get("name", "")
    L = []
    icon = ctx.img(ch.get("icon"))
    if icon:
        fr = assets.framed(icon, 420 if long else 560, 420 if long else 560, "soft")
        L.append((fr, ctx.W / 2 - (330 if long else 0), ctx.H / 2 + (0 if long else -140), 0))
        L.append((_text_layer(label, 700 if long else 900, 300 if long else 260, 120 if long else 110),
                  ctx.W / 2 + (330 if long else 0), ctx.H / 2 - (30 if long else -330), 1))
        L.append((_text_layer(f"{idx + 1} / {total}", 300, 80, 40, min_size=28, fill=GREY),
                  ctx.W / 2 + (330 if long else 0), ctx.H / 2 + (110 if long else 470), 2))
    else:
        L.append((_text_layer(label, 1400 if long else 900, 400, 140), ctx.W / 2, ctx.H / 2 - 30, 0))
        L.append((_text_layer(f"{idx + 1} / {total}", 300, 80, 40, min_size=28, fill=GREY),
                  ctx.W / 2, ctx.H / 2 + 200, 1))
    return L


def outro_layers(ctx, spec):
    long = ctx.mode == "long"
    o = spec.get("outro") or {}
    show = o.get("show", "Subscribe for more.")
    sm = ctx.stick("wave", 620 if long else 560, "smile")
    if long:
        return [(sm, 470, ctx.H / 2 + 30, 0), (_text_layer(show, 980, 520, 84), 1350, ctx.H / 2, 1)]
    return [(_text_layer(show, 920, 460, 80), ctx.W / 2, 540, 1), (sm, ctx.W / 2, 1180, 0)]


def endcard_layers(ctx, spec):
    """Reel koncovka: 'Full video on YouTube -> link in bio'."""
    e = ctx.e
    sm = ctx.stick("point_right", 520, "smile")
    txt = e.get("cta_footer", "Full video on YouTube → link in bio")
    title = spec.get("series", "")
    return [(_text_layer(title, 920, 300, 76, min_size=36), ctx.W / 2, 460, 0),
            (_text_layer(txt, 900, 260, 64, min_size=32, fill=assets.BLUE), ctx.W / 2, 800, 1),
            (sm, ctx.W / 2, 1250, 2)]


# ---------------------------------------------------------------- casova os + snimky
class Seq:
    """Zbiera snimky (PNG) s dlzkami a audio kusky; nakoniec spoji ffmpeg-om."""

    def __init__(self, ctx, name):
        self.ctx = ctx
        self.name = name
        self.dir = os.path.join(ctx.out_dir, f"_frames_{name}")
        os.makedirs(self.dir, exist_ok=True)
        self.entries = []      # (png_path, duration)
        self.audio = []        # numpy kusky (24k) v poradi
        self.t = 0.0
        self.n = 0
        self.marks = []        # (label, t) pre YouTube kapitoly

    def _save(self, im):
        p = os.path.join(self.dir, f"f{self.n:05d}.png")
        im.convert("RGB").save(p, compress_level=1)
        self.n += 1
        return p

    def add_silence(self, dur):
        if dur <= 0:
            return
        self.audio.append(np.zeros(int(dur * tts.SR), dtype=np.float32))

    def add_voice(self, wav_path):
        a, sr = sf.read(wav_path, dtype="float32")
        if a.ndim > 1:
            a = a.mean(axis=1)
        self.audio.append(a)
        return len(a) / sr

    def add_slide(self, layers, dur, hud=None, animate=True):
        """Pop-in animacia + hold. dur = celkova dlzka slajdu."""
        fps = self.ctx.fps
        fd = 1.0 / fps
        used = 0.0
        if animate and layers:
            for i in range(ANIM_FRAMES):
                p = (i + 1) / ANIM_FRAMES
                self.entries.append((self._save(compose(self.ctx, layers, p, hud)), fd))
                used += fd
        hold = max(fd, dur - used)
        self.entries.append((self._save(compose(self.ctx, layers, 1.0, hud)), hold))
        self.t += used + hold

    def finish(self, out_mp4, music=None, music_vol=0.06):
        ctx = self.ctx
        # audio
        a = np.concatenate(self.audio) if self.audio else np.zeros(int(tts.SR * 1), dtype=np.float32)
        total_v = sum(d for _, d in self.entries)
        need = int(total_v * tts.SR)
        if len(a) < need:
            a = np.concatenate([a, np.zeros(need - len(a), dtype=np.float32)])
        a = a[:need]
        # jemna normalizacia
        peak = float(np.abs(a).max() or 1.0)
        a = a * min(1.0, 0.89 / peak)
        wav = os.path.join(self.dir, "audio.wav")
        sf.write(wav, a, tts.SR)
        # concat list
        lst = os.path.join(self.dir, "list.txt")
        with open(lst, "w", encoding="utf-8") as f:
            for p, d in self.entries:
                f.write(f"file '{os.path.basename(p)}'\nduration {d:.4f}\n")
            f.write(f"file '{os.path.basename(self.entries[-1][0])}'\n")
        dur = total_v
        vf = (f"fps={ctx.fps},format=rgba,"
              f"drawbox=x=0:y=0:w='iw*min(t/{dur:.3f}\\,1)':h={7 if ctx.mode == 'long' else 9}"
              f":color=0x1e1e1e@0.9:t=fill,format=yuv420p")
        cmd = [ctx.ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", wav]
        if music and os.path.exists(music):
            cmd += ["-stream_loop", "-1", "-i", music,
                    "-filter_complex",
                    f"[0:v]{vf}[v];[2:a]volume={music_vol},afade=t=out:st={max(0, dur - 2.5):.2f}:d=2.5[m];"
                    f"[1:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
                    "-map", "[v]", "-map", "[a]"]
        else:
            cmd += ["-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart",
                "-t", f"{dur:.3f}", out_mp4]
        run(cmd)
        return dur


# ---------------------------------------------------------------- dlhe video
def render_long(spec, cfg, out_dir, voices, images, use_images=True):
    ctx = Ctx(cfg, "long", spec, out_dir, use_images, images)
    seq = Seq(ctx, "long")
    chs = spec["chapters"]
    # cold open: mriezka + hook
    if "open" in voices:
        L = grid_layers(ctx, spec)
        d = voices["open"][1]
        seq.add_voice(voices["open"][0])
        seq.add_silence(0.5)
        seq.add_slide(L, d + 0.5, None)
    for ci, ch in enumerate(chs):
        seq.marks.append((ch.get("name") or ch.get("label"), seq.t))
        hud = hud_layer(ctx, ch)
        seq.add_silence(CHAPTER_CARD)
        seq.add_slide(chapter_card_layers(ctx, ch, ci, len(chs)), CHAPTER_CARD, None)
        for bi, b in enumerate(ch["beats"]):
            uid = f"c{ci}_b{bi}"
            if uid not in voices:
                continue
            L = layers_for_beat(ctx, b, bi)
            d = seq.add_voice(voices[uid][0])
            seq.add_silence(BEAT_GAP)
            seq.add_slide(L, d + BEAT_GAP, hud)
        seq.add_silence(CHAPTER_GAP)
        seq.entries[-1] = (seq.entries[-1][0], seq.entries[-1][1] + CHAPTER_GAP)
        seq.t += CHAPTER_GAP
    if "outro" in voices:
        L = outro_layers(ctx, spec)
        d = seq.add_voice(voices["outro"][0])
        seq.add_silence(OUTRO_HOLD)
        seq.add_slide(L, d + OUTRO_HOLD, None)
    out = os.path.join(out_dir, "long.mp4")
    e = cfg["explainer"]
    dur = seq.finish(out, e.get("music") or None, float(e.get("music_volume", 0.06)))
    print(f"  dlhe video: {out} ({dur / 60:.1f} min)")
    return out, seq.marks, dur


# ---------------------------------------------------------------- reels
def render_reels(spec, cfg, out_dir, voices, images, use_images=True, only=None):
    ctx = Ctx(cfg, "reel", spec, out_dir, use_images, images)
    outs = []
    chs = spec["chapters"]
    for ci, ch in enumerate(chs):
        if only is not None and ci not in only:
            continue
        seq = Seq(ctx, f"reel{ci + 1:02d}")
        hud = hud_layer(ctx, ch)
        for bi, b in enumerate(ch["beats"]):
            uid = f"c{ci}_b{bi}"
            if uid not in voices:
                continue
            L = layers_for_beat(ctx, b, bi)
            d = seq.add_voice(voices[uid][0])
            seq.add_silence(BEAT_GAP)
            seq.add_slide(L, d + BEAT_GAP, hud)
        seq.add_silence(ENDCARD_REEL)
        seq.add_slide(endcard_layers(ctx, spec), ENDCARD_REEL, None)
        name = f"reel_{ci + 1:02d}_{common.slug(ch.get('label') or ch.get('name'))}.mp4"
        out = os.path.join(out_dir, name)
        e = cfg["explainer"]
        dur = seq.finish(out, e.get("music") or None, float(e.get("music_volume", 0.06)))
        print(f"  reel {ci + 1}: {name} ({dur:.0f}s)")
        outs.append({"path": out, "chapter": ci, "label": ch.get("label") or ch.get("name"),
                     "name": ch.get("name"), "hook": ch.get("hook", ""), "duration": dur})
    return outs


# ---------------------------------------------------------------- thumbnail
def make_thumbnail(spec, cfg, out_dir, images):
    W, H = 1280, 720
    im = assets.background(W, H)
    hero = None
    for key in ([spec.get("thumb_image")] + [c.get("icon") for c in spec["chapters"]]):
        if key and images.get(key):
            hero = images[key]
            break
    if hero:
        fr = assets.framed(hero, 520, 400, "blue", border=8, offset=16, radius=14)
        paste_center(im, fr, 320, 360)
    sm = assets.stickman("point_left", 260, "surprised")
    paste_center(im, sm, 1120, 560)
    title = spec.get("thumb_text") or spec.get("series", "")
    draw_block(im, title, (640, 70, 600, 340), start=104, min_size=48, align="left", valign="top")
    p = os.path.join(out_dir, "thumb.jpg")
    im.convert("RGB").save(p, quality=90)
    return p


# ---------------------------------------------------------------- main
def render_all(script_path, do_long=True, do_reels=True, use_images=True):
    common.ensure_dirs()
    cfg = common.load_cfg()
    spec = common.load_json(script_path, None)
    if not spec:
        raise SystemExit(f"Skript nenajdeny: {script_path}")
    sl = common.slug(spec.get("series") or spec.get("title"))
    out_dir = os.path.join(common.OUT_ROOT, sl)
    os.makedirs(out_dir, exist_ok=True)
    print(f"== {spec.get('series')} -> {out_dir}")
    images = prefetch_images(spec, cfg, use_images)
    voices = build_voice(spec, cfg, os.path.join(out_dir, "_voice"))
    meta = common.load_json(os.path.join(out_dir, "meta.json"), {})
    meta.update({"series": spec.get("series"), "title": spec.get("title"),
                 "description": spec.get("description", ""), "hashtags": spec.get("hashtags", []),
                 "script": os.path.relpath(script_path, common.ROOT)})
    if do_long:
        out, marks, dur = render_long(spec, cfg, out_dir, voices, images, use_images)
        meta["long"] = out
        meta["duration"] = dur
        meta["chapters_ts"] = [(n, common.hms(t)) for n, t in marks]
        meta["thumb"] = make_thumbnail(spec, cfg, out_dir, images)
    if do_reels:
        meta["reels"] = render_reels(spec, cfg, out_dir, voices, images, use_images)
    common.save_json(os.path.join(out_dir, "meta.json"), meta)
    return meta


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = set(a for a in sys.argv[1:] if a.startswith("--"))
    if not args:
        print(__doc__)
        sys.exit(1)
    do_long = "--reels" not in flags
    do_reels = "--long" not in flags
    render_all(args[0], do_long, do_reels, use_images="--no-images" not in flags)

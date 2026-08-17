#!/usr/bin/env python3
"""Vizualne stavebne kamene explainer stylu (biele pozadie, panacik, ramiky).

- stickman(pose, h)  -> procedurálne kresleny panacik v PIL (bez stock cliparts, vzdy rovnaky)
- gen_image(...)     -> AI obrazok (Pollinations/Flux, zadarmo) v jednotnom style + cache
- framed(...)        -> obrazok v ramiku s modrym posunutym tienom / v kruhu
- text helpers       -> zalamovanie, fit fontu, blok textu
"""
import hashlib
import math
import os
import threading
import time
import urllib.parse

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from common import CACHE_DIR, FONT_DIR

FONT_BOLD = os.path.join(FONT_DIR, "ComicNeue-Bold.ttf")
FONT_REG = os.path.join(FONT_DIR, "ComicNeue-Regular.ttf")
INK = (20, 20, 20)
BLUE = (28, 78, 216)
RED = (214, 40, 40)
GREY = (120, 120, 120)

_font_cache = {}


def font(size, bold=True):
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_BOLD if bold else FONT_REG, int(size))
    return _font_cache[key]


# ---------------------------------------------------------------- panacik
POSES = {
    # (lavy_lakt, lava_ruka, pravy_lakt, prava_ruka)  v jednotkach vysky, od ramien; +x doprava, +y dole
    "idle":         ((-0.09, 0.15), (-0.13, 0.30), (0.09, 0.15), (0.13, 0.30)),
    "point_right":  ((-0.09, 0.15), (-0.13, 0.30), (0.12, 0.05), (0.29, -0.03)),
    "point_left":   ((-0.12, 0.05), (-0.29, -0.03), (0.09, 0.15), (0.13, 0.30)),
    "arms_crossed": ((-0.11, 0.11), (0.09, 0.13), (0.11, 0.11), (-0.09, 0.15)),
    "shrug":        ((-0.11, 0.09), (-0.21, -0.03), (0.11, 0.09), (0.21, -0.03)),
    "think":        ((-0.09, 0.15), (-0.13, 0.30), (0.11, 0.12), (0.03, -0.05)),
    "present":      ((-0.09, 0.15), (-0.13, 0.30), (0.12, 0.10), (0.27, 0.05)),
    "celebrate":    ((-0.12, -0.05), (-0.16, -0.23), (0.12, -0.05), (0.16, -0.23)),
    "wave":         ((-0.09, 0.15), (-0.13, 0.30), (0.13, 0.02), (0.20, -0.16)),
}


def stickman(pose="idle", h=520, mood="smile"):
    """Vrati RGBA obrazok panacika (hlava, kravata, ruky, nohy). Kresli 2x a zmensi = hladke ciary."""
    S = 2
    H = h * S
    W = int(H * 0.75)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    st = max(3, int(H / 52))              # hrubka ciary
    cx = W // 2
    r = int(H * 0.105)                    # polomer hlavy
    head_c = (cx, r + st * 2)
    neck = (cx, head_c[1] + r)
    shoulder = (cx, neck[1] + int(H * 0.06))
    hip = (cx, int(H * 0.60))
    # hlava
    d.ellipse([head_c[0] - r, head_c[1] - r, head_c[0] + r, head_c[1] + r], outline=INK, width=st)
    # tvar
    ey = head_c[1] - int(r * 0.15)
    for sx in (-1, 1):
        ex = head_c[0] + sx * int(r * 0.36)
        d.ellipse([ex - st, ey - st, ex + st, ey + st], fill=INK)
    if mood == "smile":
        d.arc([head_c[0] - int(r * 0.45), head_c[1] - int(r * 0.1),
               head_c[0] + int(r * 0.45), head_c[1] + int(r * 0.6)], 20, 160, fill=INK, width=max(2, st - 1))
    elif mood == "surprised":
        d.ellipse([head_c[0] - int(r * 0.16), head_c[1] + int(r * 0.25),
                   head_c[0] + int(r * 0.16), head_c[1] + int(r * 0.55)], outline=INK, width=max(2, st - 1))
    else:  # neutral
        d.line([head_c[0] - int(r * 0.35), head_c[1] + int(r * 0.42),
                head_c[0] + int(r * 0.35), head_c[1] + int(r * 0.42)], fill=INK, width=max(2, st - 1))
    # telo
    d.line([neck, hip], fill=INK, width=st)
    # kravata
    kw = int(H * 0.028)
    kt = int(H * 0.012)
    d.polygon([(cx - kt, neck[1] + st), (cx + kt, neck[1] + st), (cx + kw, neck[1] + int(H * 0.16)),
               (cx, neck[1] + int(H * 0.19)), (cx - kw, neck[1] + int(H * 0.16))], fill=INK)
    d.polygon([(cx - kt, neck[1] + st), (cx + kt, neck[1] + st), (cx + kt, neck[1] + st + kt * 2),
               (cx - kt, neck[1] + st + kt * 2)], fill=INK)
    # ruky
    le, lh, re_, rh = POSES.get(pose, POSES["idle"])
    for elbow, hand in ((le, lh), (re_, rh)):
        e = (shoulder[0] + int(elbow[0] * H), shoulder[1] + int(elbow[1] * H))
        hh = (shoulder[0] + int(hand[0] * H), shoulder[1] + int(hand[1] * H))
        d.line([shoulder, e, hh], fill=INK, width=st, joint="curve")
        d.ellipse([hh[0] - st * 1.3, hh[1] - st * 1.3, hh[0] + st * 1.3, hh[1] + st * 1.3], fill=INK)
    # nohy
    spread = int(H * 0.12)
    foot_y = H - st * 2
    for sx in (-1, 1):
        knee = (cx + sx * int(spread * 0.4), hip[1] + int((foot_y - hip[1]) * 0.5))
        foot = (cx + sx * spread, foot_y)
        d.line([hip, knee, foot], fill=INK, width=st, joint="curve")
        d.line([foot, (foot[0] + sx * int(H * 0.05), foot_y)], fill=INK, width=st)
    return im.resize((W // S, H // S), Image.LANCZOS)


# ---------------------------------------------------------------- AI obrazky
_img_lock = threading.Lock()
_last_req = [0.0]
# Pollinations limit: anonym 1 request / 15 s, registrovany (zadarmo, auth.pollinations.ai) 1 / 5 s.
POLLI_TOKEN = os.environ.get("POLLINATIONS_TOKEN", "").strip()
MIN_GAP = float(os.environ.get("POLLI_MIN_GAP", "5.5" if POLLI_TOKEN else "15.5"))


def _mean_lum(path):
    try:
        return float(np.asarray(Image.open(path).convert("L").resize((64, 64))).mean())
    except Exception:
        return 128.0


def gen_image(prompt, w=1024, h=768, seed=1, style="", timeout=150, tries=4):
    """Pollinations Flux, zadarmo bez kluca. Jednotny styl = pevny suffix. Cache podla hashu.
    Vrati cestu k JPG alebo None (volajuci musi vediet padnut na slajd bez obrazka)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    full = (prompt.strip().rstrip(".") + ", " + style) if style else prompt
    for att in range(tries):
        sd = seed + att * 101
        key = hashlib.md5(f"{full}|{w}x{h}|{sd}".encode()).hexdigest()[:20]
        p = os.path.join(CACHE_DIR, f"ex_{key}.jpg")
        if os.path.exists(p) and os.path.getsize(p) > 8000:
            if _mean_lum(p) > 45:
                return p
            continue
        url = (f"https://image.pollinations.ai/prompt/{urllib.parse.quote(full[:900])}"
               f"?width={w}&height={h}&model=flux&nologo=true&enhance=false&seed={sd}")
        headers = {"Authorization": f"Bearer {POLLI_TOKEN}"} if POLLI_TOKEN else {}
        with _img_lock:
            gap = MIN_GAP - (time.time() - _last_req[0])
            if gap > 0:
                time.sleep(gap)
            _last_req[0] = time.time()
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                with open(p, "wb") as f:
                    f.write(r.content)
                if _mean_lum(p) > 45:
                    return p
                print(f"   [img] prilis tmavy -> re-gen ({att + 1}/{tries})")
                continue
            print(f"   [img] HTTP {r.status_code} ({att + 1}/{tries}) {prompt[:50]}")
            if r.status_code == 429:
                time.sleep(MIN_GAP + 5 * att)   # limit: pockaj cely interval navyse
                continue
        except Exception as e:
            print(f"   [img] {str(e)[:80]} ({att + 1}/{tries})")
        time.sleep(6 + 8 * att)
    return None


# ---------------------------------------------------------------- ramiky
def _cover(im, w, h):
    """Zmensi/oreze obrazok tak, aby presne vyplnil w x h."""
    iw, ih = im.size
    sc = max(w / iw, h / ih)
    im = im.resize((max(1, int(iw * sc + 0.5)), max(1, int(ih * sc + 0.5))), Image.LANCZOS)
    x = (im.size[0] - w) // 2
    y = (im.size[1] - h) // 2
    return im.crop((x, y, x + w, y + h))


def framed(path_or_im, w, h, style="blue", border=6, offset=None, radius=10):
    """Obrazok v ramiku ako v referencii: biely okraj + modry tien posunuty vpravo dole.
    style: 'blue' | 'circle' | 'soft'. Vrati RGBA (vratane miesta na tien)."""
    im = Image.open(path_or_im).convert("RGB") if isinstance(path_or_im, str) else path_or_im.convert("RGB")
    if offset is None:
        offset = max(6, int(min(w, h) * 0.035))
    if style == "circle":
        d_ = min(w, h)
        im = _cover(im, d_, d_)
        S = 2
        mask = Image.new("L", (d_ * S, d_ * S), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, d_ * S - 1, d_ * S - 1], fill=255)
        mask = mask.resize((d_, d_), Image.LANCZOS)
        pad = border + offset
        out = Image.new("RGBA", (d_ + pad * 2, d_ + pad * 2), (0, 0, 0, 0))
        # makky sedy tien
        sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([pad + offset // 2, pad + offset, pad + d_ + offset // 2, pad + d_ + offset],
                                   fill=(0, 0, 0, 90))
        sh = sh.filter(ImageFilter.GaussianBlur(offset * 0.8))
        out.alpha_composite(sh)
        ring = Image.new("RGBA", out.size, (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse([pad - border, pad - border, pad + d_ + border, pad + d_ + border],
                                     fill=(255, 255, 255, 255))
        out.alpha_composite(ring)
        pic = Image.new("RGBA", (d_, d_), (0, 0, 0, 0))
        pic.paste(im, (0, 0), mask)
        out.alpha_composite(pic, (pad, pad))
        return out
    im = _cover(im, w, h)
    pad = border
    out = Image.new("RGBA", (w + pad * 2 + offset, h + pad * 2 + offset), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    if style == "blue":
        d.rounded_rectangle([offset, offset, offset + w + pad * 2 - 1, offset + h + pad * 2 - 1],
                            radius=radius, fill=BLUE + (255,))
    else:  # soft
        sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([offset // 2, offset, offset // 2 + w + pad * 2, offset + h + pad * 2],
                                             radius=radius, fill=(0, 0, 0, 80))
        out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(offset * 0.7)))
        d = ImageDraw.Draw(out)
    d.rounded_rectangle([0, 0, w + pad * 2 - 1, h + pad * 2 - 1], radius=radius, fill=(255, 255, 255, 255))
    # zaoblene rohy obrazka
    S = 2
    mask = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=max(1, (radius - 3) * S), fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)
    pic = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pic.paste(im, (0, 0), mask)
    out.alpha_composite(pic, (pad, pad))
    return out


def tile(path_or_im, size, label, label_font, bg=(255, 255, 255), radius=28):
    """Dlazdica pre cold-open mriezku: zaobleny stvorec s obrazkom + popisok pod nim."""
    im = Image.open(path_or_im).convert("RGB") if isinstance(path_or_im, str) else path_or_im.convert("RGB")
    im = _cover(im, size, size)
    S = 2
    mask = Image.new("L", (size * S, size * S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size * S - 1, size * S - 1], radius=radius * S, fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    lh = int(label_font.size * 1.5)
    out = Image.new("RGBA", (size + 20, size + lh + 20), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([12, 14, 12 + size, 14 + size], radius=radius, fill=(0, 0, 0, 70))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    pic = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pic.paste(im, (0, 0), mask)
    out.alpha_composite(pic, (10, 6))
    d = ImageDraw.Draw(out)
    tw = d.textlength(label, font=label_font)
    d.text(((out.size[0] - tw) / 2, size + 12), label, font=label_font, fill=INK)
    return out


# ---------------------------------------------------------------- text
def wrap_text(text, fnt, max_w, draw=None):
    if draw is None:
        draw = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_font(text, max_w, max_h, start=96, min_size=28, bold=True, line_gap=1.15):
    """Najvacsi font, pri ktorom sa text (zalomeny) vojde do max_w x max_h."""
    draw = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    size = start
    while size >= min_size:
        f = font(size, bold)
        lines = wrap_text(text, f, max_w, draw)
        h = len(lines) * size * line_gap
        if h <= max_h and all(draw.textlength(l, font=f) <= max_w for l in lines):
            return f, lines
        size -= 4
    f = font(min_size, bold)
    return f, wrap_text(text, f, max_w, draw)


def draw_block(img, text, box, start=96, min_size=28, bold=True, fill=INK, align="center",
               valign="middle", line_gap=1.15):
    """Nakresli zalomeny text do boxu (x, y, w, h). Vrati (font, vysku)."""
    x, y, w, h = box
    f, lines = fit_font(text, w, h, start, min_size, bold, line_gap)
    d = ImageDraw.Draw(img)
    lh = f.size * line_gap
    total = lh * len(lines)
    if valign == "middle":
        cy = y + (h - total) / 2
    elif valign == "bottom":
        cy = y + h - total
    else:
        cy = y
    for ln in lines:
        tw = d.textlength(ln, font=f)
        if align == "center":
            cx = x + (w - tw) / 2
        elif align == "right":
            cx = x + w - tw
        else:
            cx = x
        d.text((cx, cy), ln, font=f, fill=fill)
        cy += lh
    return f, total


def paste_center(canvas, im, cx, cy, scale=1.0, alpha=1.0):
    """Vloz RGBA obrazok so stredom v (cx, cy), volitelne zmenseny (pop-in) a priesvitny."""
    if scale <= 0.01 or alpha <= 0.01:
        return
    w, h = im.size
    if scale != 1.0:
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        w, h = im.size
    if alpha < 1.0:
        a = im.getchannel("A").point(lambda v: int(v * alpha))
        im = im.copy()
        im.putalpha(a)
    canvas.alpha_composite(im, (int(cx - w / 2), int(cy - h / 2)))


def background(w, h):
    """Biele pozadie s jemnym sivym vinetovanim (ako referencia)."""
    base = Image.new("RGB", (w, h), (252, 252, 252))
    yy, xx = np.mgrid[0:h, 0:w]
    dx = (xx - w / 2) / (w / 2)
    dy = (yy - h / 2) / (h / 2)
    r = np.sqrt(dx * dx + dy * dy)
    v = np.clip((r - 0.55) / 0.9, 0, 1) ** 1.6
    arr = np.asarray(base).astype(np.float32)
    arr -= (v * 26)[:, :, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")

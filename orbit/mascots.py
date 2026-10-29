"""Postavicky-rozpravaci pre ORBIT (cista vektorova grafika v kode, ziadne AI obrazky).
draw(kind, mouth=0..1, blink=0..1, look=-1..1) -> RGBA PIL obrazok (vyska ~H_OUT px).
kind: "orbi" (satelit-robot), "astro" (astronaut), "pin" (mapovy spendlik)."""
from PIL import Image, ImageDraw, ImageFilter

S = 4                    # supersampling
H_OUT = 380
INK = (23, 33, 58, 255)
LW = 22


def _glow(im, color, blur=28):
    a = im.split()[3].filter(ImageFilter.GaussianBlur(blur))
    g = Image.new("RGBA", im.size, color); g.putalpha(a.point(lambda v: int(v * 0.9)))
    return Image.alpha_composite(g, im)


def orbi(mouth, blink, look, expr="normal"):
    w, h = 1600, 1520
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    cx, cy, r = 800, 860, 380
    # solarne panely + ramena
    for sx in (-1, 1):
        x0 = cx + sx * 430
        d.line((cx + sx * 300, cy, x0, cy), fill=INK, width=40)
        d.line((cx + sx * 300, cy, x0, cy), fill=(170, 180, 196, 255), width=16)
        px0, px1 = sorted((x0, x0 + sx * 300))
        d.rounded_rectangle((px0, cy - 150, px1, cy + 150), 18, fill=(29, 59, 143, 255), outline=INK, width=LW)
        for k in range(1, 3):
            xx = px0 + (px1 - px0) * k / 3
            d.line((xx, cy - 140, xx, cy + 140), fill=(70, 110, 220, 255), width=10)
        d.line((px0 + 10, cy, px1 - 10, cy), fill=(70, 110, 220, 255), width=10)
    # anténa
    d.line((cx, cy - r + 10, cx + 40, cy - r - 170), fill=INK, width=24)
    d.ellipse((cx + 40 - 46, cy - r - 170 - 46, cx + 40 + 46, cy - r - 170 + 46), fill=(255, 77, 77, 255), outline=INK, width=LW)
    # telo
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(214, 222, 234, 255))
    d.ellipse((cx - r + 30, cy - r + 10, cx + r - 70, cy + r - 90), fill=(247, 249, 252, 255))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK, width=LW)
    d.arc((cx - r + 70, cy - r + 60, cx + r - 70, cy + r - 60), 200, 250, fill=(255, 255, 255, 255), width=26)
    # obrazovka-tvar
    fx0, fy0, fx1, fy1 = cx - 250, cy - 150, cx + 250, cy + 170
    d.rounded_rectangle((fx0, fy0, fx1, fy1), 110, fill=(14, 24, 44, 255), outline=INK, width=LW)
    face = Image.new("RGBA", (w, h), (0, 0, 0, 0)); fd = ImageDraw.Draw(face)
    cyan = (78, 240, 255, 255)
    ox = look * 40
    eh = max(10, 120 * (1 - blink))
    for ex in (cx - 100 + ox, cx + 100 + ox):
        if expr == "happy":                                   # oci ako ^ ^
            fd.arc((ex - 46, cy - 70, ex + 46, cy + 10), 200, 340, fill=cyan, width=26)
        elif expr == "surprised":                             # velke okruhle oci
            fd.ellipse((ex - 48, cy - 30 - max(10, 150 * (1 - blink)) / 2, ex + 48,
                        cy - 30 + max(10, 150 * (1 - blink)) / 2), fill=cyan)
        else:
            fd.rounded_rectangle((ex - 34, cy - 30 - eh / 2, ex + 34, cy - 30 + eh / 2), 34, fill=cyan)
    if expr == "surprised":
        mr = 26 + 30 * mouth
        fd.ellipse((cx - mr + ox, cy + 92 - mr, cx + mr + ox, cy + 92 + mr), outline=cyan, width=18)
    else:
        mh = 18 + 80 * mouth
        mw = 110 if expr == "happy" else 80
        fd.rounded_rectangle((cx - mw + ox, cy + 85 - mh / 2, cx + mw + ox, cy + 85 + mh / 2), 20, fill=cyan)
    im = Image.alpha_composite(im, _glow(face, (78, 240, 255, 160), 22))
    return im


def astro(mouth, blink, look):
    w, h = 1400, 1560
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    cx = 700
    # telo + ruky
    d.rounded_rectangle((cx - 300, 1020, cx + 300, 1500), 150, fill=(240, 243, 248, 255), outline=INK, width=LW)
    d.rounded_rectangle((cx - 120, 1130, cx + 120, 1290), 30, fill=(255, 120, 50, 255), outline=INK, width=16)
    d.ellipse((cx - 40, 1170, cx + 40, 1250), fill=(255, 210, 90, 255), outline=INK, width=12)
    for sx in (-1, 1):
        ax0, ax1 = sorted((cx + sx * 260, cx + sx * 420))
        d.rounded_rectangle((ax0, 1060, ax1, 1360), 80, fill=(232, 236, 243, 255), outline=INK, width=LW)
    # prilba
    hr = 470; hy = 600
    d.ellipse((cx - hr, hy - hr, cx + hr, hy + hr), fill=(244, 246, 250, 255), outline=INK, width=LW)
    gr = 360
    d.ellipse((cx - gr, hy - gr + 20, cx + gr, hy + gr + 20), fill=(160, 205, 235, 255), outline=INK, width=LW)
    # tvar
    fr = 280; fy = hy + 50
    d.ellipse((cx - fr, fy - fr, cx + fr, fy + fr), fill=(246, 204, 168, 255))
    d.chord((cx - fr, fy - fr - 10, cx + fr, fy + fr), 180, 360, fill=(92, 58, 40, 255))      # vlasy
    d.ellipse((cx - fr, fy - fr, cx + fr, fy + fr), outline=(120, 80, 60, 255), width=10)
    ox = look * 30
    eh = max(8, 70 * (1 - blink))
    for ex in (cx - 105 + ox, cx + 105 + ox):
        d.ellipse((ex - 34, fy + 40 - eh / 2, ex + 34, fy + 40 + eh / 2), fill=INK)
        if blink < 0.5:
            d.ellipse((ex - 4, fy + 40 - eh / 2 + 10, ex + 16, fy + 40 - eh / 2 + 30), fill=(255, 255, 255, 255))
    for ex in (cx - 170, cx + 170):
        d.ellipse((ex - 45, fy + 110, ex + 45, fy + 150), fill=(240, 140, 130, 150))
    mh = 14 + 80 * mouth
    d.rounded_rectangle((cx - 55 + ox, fy + 150, cx + 55 + ox, fy + 150 + mh), 40, fill=(140, 40, 50, 255), outline=INK, width=10)
    # odlesk skla
    d.arc((cx - gr + 50, hy - gr + 70, cx + gr - 50, hy + gr), 200, 245, fill=(255, 255, 255, 220), width=34)
    return im


def pin(mouth, blink, look):
    w, h = 1300, 1560
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    cx, cy, r = 650, 620, 470
    red = (255, 75, 62, 255)
    d.polygon([(cx - r * 0.8, cy + r * 0.55), (cx + r * 0.8, cy + r * 0.55), (cx, cy + r + 470)], fill=red)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=red)
    d.line([(cx - r * 0.82, cy + r * 0.56), (cx, cy + r + 470), (cx + r * 0.82, cy + r * 0.56)], fill=INK, width=LW, joint="curve")
    d.arc((cx - r, cy - r, cx + r, cy + r), 145, 395, fill=INK, width=LW)
    d.arc((cx - r + 60, cy - r + 50, cx + r - 60, cy + r - 60), 200, 245, fill=(255, 160, 150, 255), width=34)
    ox = look * 40
    eh = 190 * (1 - blink) + 16
    for ex in (cx - 150, cx + 150):
        d.ellipse((ex - 105, cy - 40 - eh / 2, ex + 105, cy - 40 + eh / 2), fill=(255, 255, 255, 255), outline=INK, width=16)
        if blink < 0.6:
            d.ellipse((ex - 46 + ox, cy - 30 - 46, ex + 46 + ox, cy - 30 + 46), fill=INK)
            d.ellipse((ex - 22 + ox, cy - 62, ex + 2 + ox, cy - 38), fill=(255, 255, 255, 255))
    mh = 20 + 120 * mouth
    d.rounded_rectangle((cx - 90, cy + 150, cx + 90, cy + 150 + mh), 60, fill=(120, 20, 30, 255), outline=INK, width=14)
    return im


KINDS = {"orbi": orbi, "astro": astro, "pin": pin}


def draw(kind, mouth=0.0, blink=0.0, look=0.0, h_out=H_OUT, expr="normal"):
    im = KINDS[kind](mouth, blink, look, expr) if kind == "orbi" else KINDS[kind](mouth, blink, look)
    bb = im.getbbox(); im = im.crop(bb)
    w = int(im.width * h_out / im.height)
    return im.resize((w, h_out), Image.LANCZOS)

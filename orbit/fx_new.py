"""Curio ORBIT - dalsie efekty k slovam (variety_catalog.json -> visual_effects, engine "new").

Kazdy efekt je funkcia fn(c) nad kontextom snimky c (fr float32 BGR, t, dt od slova, cx/cy miesto, R polomer
utvaru v px, out = zanikanie s koncom beatu, f = zaznam z beat["fx"], cam, spec). Engine vola draw(kind, ...)
z draw_fx; write_spec vybera efekt podla slov (pick()). Vsetko deterministicke (pevne seedy, cas t).

Spec beat: {"text": "...", "fx": [{"kind": "lightning_flash", "on": "storm"}]}
"""
import math
import re

import cv2
import numpy as np

E = None                        # orbit_engine (nastavi engine pri importe: fx_new.E = modul)
W, H = 1080, 1920
YT, YB = 300, 1290              # bezpecna zona: pod vyhladavanim, nad titulkami/Orbim
CY_ = (255, 240, 78)            # BGR azurova (ako engine CYAN)
YL_ = (40, 214, 255)            # BGR zlta
_c = {}


class Ctx:
    __slots__ = ("fr", "t", "dt", "cx", "cy", "R", "rr", "out", "f", "cam", "spec")


def cache(key, fn):
    if key not in _c:
        _c[key] = fn()
    return _c[key]


def cl(v, a=0.0, b=1.0):
    return min(b, max(a, v))


def ease(u):
    u = cl(u)
    return u * u * (3 - 2 * u)


def eout(u):
    u = cl(u)
    return 1 - (1 - u) ** 3


def life(c, dur, fin=0.3, fout=0.5):
    """alfa efektu: nabeh fin, drzi do dur, potom zanik fout; krat zanik s koncom beatu."""
    return c.out * cl(c.dt / fin) * cl((dur + fout - c.dt) / fout)


def label(c, txt, y, sz=56, col=(255, 255, 255, 255), a=1.0, x=None, box=(0, 0, 0, 165)):
    lab = E.text_rgba(txt, sz, fill=col, box=box, pad=14)
    xx = int(W / 2 - lab.shape[1] / 2) if x is None else int(min(W - lab.shape[1] - 10, max(10, x)))
    E.paste_rgba(c.fr, lab, xx, int(y), a)
    return lab.shape


def add_layer(fr, lay, col, a, y0=0, x0=0):
    """fr += lay * col * a (lay 0..1 2D, moze byt v nizsom rozliseni -> zvacsi sa)."""
    h, w = fr.shape[0] - y0, fr.shape[1] - x0
    if lay.shape[:2] != (h, w):
        lay = cv2.resize(lay, (w, h), interpolation=cv2.INTER_LINEAR)
    fr[y0:, x0:] += lay[..., None] * (np.array(col, np.float32) * a)


def over_layer(fr, lay, col, a):
    """fr = fr*(1-m) + col*m, m = lay*a (lay v lubovolnom rozliseni, cely snimok)."""
    if lay.shape[:2] != (H, W):
        lay = cv2.resize(lay, (W, H), interpolation=cv2.INTER_LINEAR)
    m = (np.clip(lay, 0, 1) * a)[..., None]
    fr[:] = fr * (1 - m) + np.array(col, np.float32) * m


def noise(seed, h, w, scales=(4, 8, 16, 32)):
    """jemny fraktalny sum 0..1 (cachovany)."""
    def mk():
        rng = np.random.default_rng(seed); acc = np.zeros((h, w), np.float32); tot = 0
        for i, s in enumerate(scales):
            n = rng.random((max(2, h // s), max(2, w // s))).astype(np.float32)
            acc += cv2.resize(n, (w, h), interpolation=cv2.INTER_CUBIC) * (0.5 ** i); tot += 0.5 ** i
        acc /= tot
        return (acc - acc.min()) / (acc.max() - acc.min() + 1e-6)
    return cache(("noise", seed, h, w, scales), mk)


def ring_pts(x, y, rx, ry=None, n=90, a0=0.0):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False) + a0
    return np.stack([x + rx * np.cos(a), y + (ry or rx) * np.sin(a)], 1).astype(np.float32)


def fpoly(fr, pts, col):
    cv2.fillPoly(fr, [np.round(np.asarray(pts, np.float32) * 16).astype(np.int32)], col, cv2.LINE_AA, 4)


# ================================================================== pocasie / prostredie
def fx_lightning_flash(c):
    def bolt(seed):
        rng = np.random.default_rng(seed)
        def split(p0, p1, d, out):
            if d == 0:
                out.append(p1); return
            m = (p0 + p1) / 2; n = np.array([p1[1] - p0[1], p0[0] - p1[0]]); L = np.hypot(*n) + 1e-6
            m = m + n / L * rng.normal(0, 0.18) * L
            split(p0, m, d - 1, out); split(m, p1, d - 1, out)
        main = [np.array([0.35, -1.0])]; split(main[0], np.array([0.0, 0.0]), 6, main)
        main = np.array(main, np.float32); brs = []
        for k in (14, 25, 38, 47):
            p = main[k]; q = p + np.array([rng.uniform(-0.45, 0.45), rng.uniform(0.15, 0.35)])
            b = [p]; split(p, q, 4, b); brs.append(np.array(b, np.float32))
        return main, brs
    main, brs = cache(("bolt",), lambda: bolt(11))
    dt = c.dt; a_all = life(c, 2.2, 0.05, 0.6)
    gl = c.fr.mean(2, keepdims=True)                         # burkova atmosfera: tmavsie, modrejsie
    k = 0.45 * a_all
    c.fr[:] = c.fr * (1 - k) + gl * np.array([0.75, 0.62, 0.55], np.float32) * k
    sc = max(380.0, c.cy - 60)
    tr = lambda p: np.stack([c.cx + p[:, 0] * sc * 0.9, c.cy + p[:, 1] * sc], 1).astype(np.float32)
    for s in (0.0, 0.28, 0.5, 1.15, 1.35):
        u = dt - s
        if 0 <= u < 0.3:
            a = (1 - u / 0.3) ** 0.7 * c.out
            if u < 0.09:
                fl = (1 - u / 0.09) * (0.7 if s == 0 else 0.4) * c.out
                c.fr[:] = c.fr * (1 - fl) + np.array([255, 245, 235], np.float32) * fl
            E.glow_lines(c.fr, [tr(main)], (255, 200, 170), 14, core=(255, 255, 255), alpha=a)
            E.glow_lines(c.fr, [tr(b) for b in brs], (255, 200, 170), 7, core=(255, 250, 240), alpha=a * 0.8)
            bb = E.roi(np.array([[c.cx - 160, c.cy - 160], [c.cx + 160, c.cy + 160]], np.float32), 0)
            if bb:
                x0, y0, x1, y1 = bb
                g = np.clip(1 - np.hypot(E._xx[y0:y1, x0:x1] - c.cx, E._yy[y0:y1, x0:x1] - c.cy) / 160, 0, 1) ** 2
                c.fr[y0:y1, x0:x1] += (g * 230 * a)[..., None]


def fx_snow_fall(c):
    a = life(c, 2.6, 0.4)
    if a <= 0:
        return
    rng = np.random.default_rng(21); n = 280
    x0, y0 = rng.uniform(0, W, n), rng.uniform(0, H, n); sp = rng.uniform(90, 260, n); sz = rng.uniform(3, 9, n)
    ph = rng.uniform(0, 6.28, n)
    lay = np.zeros((H // 2, W // 2), np.float32)
    y = (y0 + sp * c.t) % (H + 40) - 20; x = (x0 + 35 * np.sin(c.t * 1.4 + ph) + 40 * c.t) % W
    for i in range(n):
        cv2.circle(lay, (int(x[i] / 2), int(y[i] / 2)), max(1, int(sz[i] / 2)), 1.0, -1, cv2.LINE_AA)
    lay = cv2.GaussianBlur(lay, (0, 0), 0.8)
    c.fr[:] = c.fr * (1 - 0.35 * a) + c.fr.mean(2, keepdims=True) * np.array([0.75, 0.7, 0.65], np.float32) * 0.35 * a   # zamracene, chladne
    over_layer(c.fr, lay, (255, 255, 255), a * 0.95)


def fx_rain_streaks(c):
    a = life(c, 2.6, 0.3)
    if a <= 0:
        return
    rng = np.random.default_rng(22); n = 320
    x0, y0 = rng.uniform(-200, W, n), rng.uniform(0, H, n); sp = rng.uniform(1500, 2300, n); L = rng.uniform(40, 95, n)
    lay = np.zeros((H // 2, W // 2), np.float32)
    y = (y0 + sp * c.t) % (H + 120) - 60; x = (x0 + 0.22 * sp * c.t) % (W + 200) - 100
    for i in range(n):
        cv2.line(lay, (int(x[i] / 2), int(y[i] / 2)), (int((x[i] - 0.22 * L[i]) / 2), int((y[i] - L[i]) / 2)),
                 0.5 + 0.5 * (i % 3) / 2, 1, cv2.LINE_AA)
    g = c.fr.mean(2, keepdims=True)
    k = 0.55 * a
    c.fr[:] = c.fr * (1 - k) + g * np.array([0.75, 0.66, 0.6], np.float32) * k     # mokro, sedo
    over_layer(c.fr, cv2.dilate(lay, np.ones((2, 1), np.uint8)), (235, 225, 215), a * 0.8)


def fx_sand_drift(c):
    a = life(c, 2.6, 0.4)
    if a <= 0:
        return
    c.fr *= 1 - 0.25 * a                                            # prach zatieni slnko
    nz = noise(5, H // 8, W // 4, (8, 16, 32))
    sh = int(c.t * 90) % (W // 4)
    haze = np.roll(nz, -sh, 1)
    haze = np.clip((haze - 0.35) * 1.6, 0, 1) * (0.4 + 0.6 * (E._yy[::8, ::4] / H))
    over_layer(c.fr, haze.astype(np.float32), (95, 150, 200), a * 0.65)
    rng = np.random.default_rng(23); n = 380
    x0, y0 = rng.uniform(0, W, n), rng.uniform(0, H, n); sp = rng.uniform(500, 1100, n); ph = rng.uniform(0, 6.28, n)
    lay = np.zeros((H // 2, W // 2), np.float32)
    x = (x0 + sp * c.t) % (W + 60) - 30; y = y0 + 25 * np.sin(c.t * 3 + ph + x / 120)
    for i in range(n):
        cv2.line(lay, (int(x[i] / 2), int(y[i] / 2)), (int((x[i] - 0.06 * sp[i]) / 2), int(y[i] / 2)), 1.0, 1, cv2.LINE_AA)
    over_layer(c.fr, cv2.GaussianBlur(lay, (0, 0), 0.7), (170, 215, 245), a * 0.9)


def fx_fog_roll(c):
    a = life(c, 2.8, 0.2)
    if a <= 0:
        return
    nz = noise(6, H // 8, W // 4 * 2, (16, 32, 64))
    off = int(c.t * 22) % (W // 4)
    f = nz[:, off:off + W // 4]
    front = (-0.2 + 1.5 * eout(c.dt / 1.6)) * (W // 4)            # mlha sa valí zlava
    xs = np.arange(W // 4, dtype=np.float32)
    m = np.clip((front - xs) / 50, 0, 1)[None, :]
    lay = np.clip(f * 1.3 - 0.05, 0, 1) * m
    over_layer(c.fr, lay.astype(np.float32), (232, 232, 228), a * 0.85)


def fx_aurora_ribbons(c):
    a = life(c, 2.8, 0.5)
    if a <= 0:
        return
    y1 = 1000; hh = y1 // 2
    g = np.clip(1 - E._yy[:y1, :1] / y1, 0, 1) ** 1.3                # nocna obloha hore
    c.fr[:y1] *= (1 - 0.8 * a * g)[..., None]
    ys = np.arange(hh, dtype=np.float32)[:, None] * 2; xs = np.arange(W // 2, dtype=np.float32)[None, :] * 2
    grow = ease(c.dt / 1.2)
    for i, (base, col) in enumerate(((560, (130, 255, 90)), (440, (210, 90, 190)), (660, (170, 255, 120)))):
        yc = base + 70 * np.sin(xs / 210 + c.t * 0.9 + i * 2.1) + 30 * np.sin(xs / 77 - c.t * 1.7 + i)
        d = yc - ys
        cur = np.where(d > 0, np.exp(-d / (170 * grow + 1)), np.exp(d / 10))
        cur *= 0.65 + 0.35 * np.sin(xs / 9 + c.t * 4 + i * 3) ** 2
        cur *= np.clip(np.sin(xs / W * math.pi * 1.1 + 0.2 * i), 0, 1)
        add_layer(c.fr[:y1], cur.astype(np.float32), col, a * (0.85 if i != 1 else 0.6))


def fx_star_field(c):
    a = life(c, 2.8, 0.6)
    if a <= 0:
        return
    g = (0.45 + 0.4 * (E._yy[:, :1] / H))
    c.fr[:] = c.fr * (1 - a * (1 - g[..., None])) * np.array([1.0, 0.92, 0.85], np.float32) ** a
    rng = np.random.default_rng(24); n = 520
    x, y, b, f, ph = rng.uniform(0, W, n), rng.uniform(0, H, n), rng.uniform(0.3, 1, n), rng.uniform(2, 7, n), rng.uniform(0, 6.28, n)
    lay = np.zeros((H, W), np.float32)
    tw = b * (0.55 + 0.45 * np.sin(c.t * f + ph))
    for i in range(n):
        cv2.circle(lay, (int(x[i]), int(y[i])), 2 if b[i] > 0.85 else 1, float(tw[i]), -1, cv2.LINE_AA)
    for i in np.nonzero(b > 0.93)[0]:                               # najjasnejsie: krizik
        L = int(14 * tw[i])
        cv2.line(lay, (int(x[i]) - L, int(y[i])), (int(x[i]) + L, int(y[i])), float(tw[i]) * 0.7, 1, cv2.LINE_AA)
        cv2.line(lay, (int(x[i]), int(y[i]) - L), (int(x[i]), int(y[i]) + L), float(tw[i]) * 0.7, 1, cv2.LINE_AA)
    lay = lay + cv2.GaussianBlur(lay, (0, 0), 3) * 2
    add_layer(c.fr, lay, (255, 245, 235), a * 1.1)


def fx_meteor_streak(c):
    a0 = life(c, 2.4, 0.05)
    for i, (s, x0, ang) in enumerate(((0.0, 1150, 128), (0.55, 900, 124), (1.05, 1250, 131))):
        u = (c.dt - s) / 0.9
        if not 0 <= u < 1.3:
            continue
        d = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
        p0 = np.array([x0, 120.0 + 80 * i]); dist = 1500 * min(u, 1)
        head = p0 + d * dist; tail = head - d * min(dist, 520)
        fade = cl((1.3 - u) / 0.3) * a0
        seg = np.linspace(0, 1, 12)
        pts = [np.array([tail + (head - tail) * seg[j], tail + (head - tail) * seg[j + 1]], np.float32) for j in range(11)]
        for j, p in enumerate(pts):
            E.glow_lines(c.fr, [p], (120, 200, 255), 2 + j, core=(220, 245, 255), alpha=fade * (j + 1) / 11)
        bb = E.roi(np.array([head - 90, head + 90], np.float32), 0)
        if bb and u < 1:
            x0_, y0_, x1_, y1_ = bb
            g = np.clip(1 - np.hypot(E._xx[y0_:y1_, x0_:x1_] - head[0], E._yy[y0_:y1_, x0_:x1_] - head[1]) / 90, 0, 1) ** 2.5
            c.fr[y0_:y1_, x0_:x1_] += g[..., None] * np.array([200, 240, 255], np.float32) * fade * 1.4


def fx_ash_cloud(c):
    a = life(c, 2.8, 0.2)
    if a <= 0:
        return
    rng = np.random.default_rng(25); n = 46
    birth = np.arange(n) * 0.055; jx = rng.normal(0, 1, n); sz = rng.uniform(0.8, 1.3, n)
    lay = np.zeros((H // 4, W // 4), np.float32); hi = np.zeros_like(lay)
    for i in range(n):
        age = c.dt - birth[i]
        if age <= 0:
            continue
        y = c.cy - 330 * age ** 0.75 - 40; x = c.cx + jx[i] * (14 + 55 * age) + 70 * age ** 1.5
        r = (28 + 85 * age ** 0.8) * sz[i]
        if y + r < YT - 250:
            continue
        cv2.circle(lay, (int(x / 4), int(y / 4)), max(1, int(r / 4)), 0.9, -1, cv2.LINE_AA)
        cv2.circle(hi, (int((x - r * 0.3) / 4), int((y - r * 0.35) / 4)), max(1, int(r / 7)), 0.5, -1, cv2.LINE_AA)
    lay = cv2.GaussianBlur(lay, (0, 0), 3); hi = cv2.GaussianBlur(hi, (0, 0), 3)
    over_layer(c.fr, lay, (52, 52, 58), a * 0.92)
    add_layer(c.fr, hi * lay, (60, 60, 60), a)
    bb = E.roi(np.array([[c.cx - 150, c.cy - 150], [c.cx + 150, c.cy + 150]], np.float32), 0)
    if bb:                                                          # zhava baza
        x0, y0, x1, y1 = bb
        g = np.clip(1 - np.hypot(E._xx[y0:y1, x0:x1] - c.cx, E._yy[y0:y1, x0:x1] - c.cy) / 150, 0, 1) ** 2
        c.fr[y0:y1, x0:x1] += g[..., None] * np.array([20, 110, 255], np.float32) * a * (0.8 + 0.2 * math.sin(c.t * 9))


def fx_heat_shimmer(c):
    a = life(c, 2.8, 0.4)
    if a <= 0:
        return
    y0 = YT
    yy, xx = E._yy[y0:], E._xx[y0:]
    A = 11 * a * (0.4 + 0.6 * (yy - y0) / (H - y0))
    mx = xx + A * np.sin(yy / 19 + c.t * 9 + np.sin(xx / 47) * 1.5)
    my = yy + A * 0.6 * np.sin(xx / 31 - c.t * 7)
    c.fr[y0:] = cv2.remap(c.fr, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    k = 0.35 * a
    c.fr[:] = c.fr * ((1 - k) + k * np.array([0.78, 0.98, 1.22], np.float32))       # teplo
    g = np.clip((E._yy[:, :1] - 700) / 1200, 0, 1)
    c.fr[:] += (g * 40 * a)[..., None] * np.array([0.4, 0.8, 1.0], np.float32)


def fx_wind_arrows(c):
    a = life(c, 2.6, 0.4)
    if a <= 0:
        return
    sp = 150; polys = []
    off = (c.t * 260) % sp
    for gy in range(YT + 40, YB - 20, sp):
        for gx in range(-sp, W + sp, sp):
            row = (gy // sp) % 2
            x = gx + off + row * sp / 2; y = gy + 30 * math.sin(x / 260 + gy / 200)
            th = 0.35 * math.sin(gy / 260 + x / 400 + c.t * 0.5)
            dx, dy = math.cos(th), math.sin(th)
            fade = cl(min(x + 50, W + 50 - x) / 160)
            if fade <= 0.05:
                continue
            L = 70
            tail = (x - dx * L, y - dy * L); head = (x + dx * 22, y + dy * 22)
            wing = [(head[0] - dx * 26 - dy * 18, head[1] - dy * 26 + dx * 18), head,
                    (head[0] - dx * 26 + dy * 18, head[1] - dy * 26 - dx * 18)]
            polys.append(np.array([tail, head], np.float32)); polys.append(np.array(wing, np.float32))
    E.glow_lines(c.fr, polys, CY_, 5, core=(255, 255, 255), alpha=a * 0.9)


def fx_terminator_sweep(c):
    a = c.out
    u = ease(c.dt / 2.2); night = c.f.get("dir", 1) >= 0
    xl = -300 + (W + 600) * u                                       # hranica den/noc (sikmo)
    d = (E._xx[::2, ::2] + (E._yy[::2, ::2] - H / 2) * 0.25) - xl
    m = np.clip(0.5 - d / 260, 0, 1) if night else np.clip(0.5 + d / 260, 0, 1)
    tw = np.exp(-(d / 110) ** 2)
    mf = cv2.resize(m.astype(np.float32), (W, H))
    c.fr[:] = c.fr * (1 - 0.78 * a * mf)[..., None] + (mf * 30 * a)[..., None] * np.array([1.0, 0.45, 0.2], np.float32)
    add_layer(c.fr, tw.astype(np.float32), (40, 120, 255), a * 0.45)
    label(c, "NIGHT FALLS" if night else "SUNRISE", 330, 54, a=a * cl(c.dt / 0.4))


def fx_night_lights_on(c):
    a = life(c, 3.0, 0.5)
    if a <= 0:
        return
    k = 0.72 * a
    c.fr[:] = c.fr * (1 - k) + c.fr * np.array([0.55, 0.32, 0.22], np.float32) * k
    def pts():
        rng = np.random.default_rng(26); P = []
        P += list(rng.normal(0, 1, (260, 2)) * 0.55)
        for _ in range(7):                                          # "cesty" z centra
            ang = rng.uniform(0, 6.28); L = rng.uniform(0.8, 1.8)
            for s in np.linspace(0.1, L, 26):
                P.append([math.cos(ang) * s + rng.normal(0, 0.03), math.sin(ang) * s + rng.normal(0, 0.03)])
        P = np.array(P, np.float32)
        return P, np.hypot(P[:, 0], P[:, 1]), rng.uniform(0.4, 1.0, len(P))
    P, dist, br = cache(("nl",), pts)
    rr = min(c.R, 360)
    on = cl((c.dt - 0.4) / 1.4)
    lay = np.zeros((H // 2, W // 2), np.float32)
    for i in np.nonzero(dist / 1.9 < on)[0]:
        x, y = c.cx + P[i, 0] * rr, c.cy + P[i, 1] * rr
        if YT - 100 < y < YB + 100:
            cv2.circle(lay, (int(x / 2), int(y / 2)), 1 + int(br[i] > 0.85), float(br[i]), -1, cv2.LINE_AA)
    glow = cv2.GaussianBlur(lay, (0, 0), 6) * 6 + cv2.GaussianBlur(lay, (0, 0), 1.2) * 1.5
    add_layer(c.fr, glow.astype(np.float32), (90, 200, 255), a)


def fx_lava_glow(c):
    a = life(c, 2.8, 0.5)
    if a <= 0:
        return
    rr = min(c.R, 420)
    ps = [np.array([c.cx, c.cy], np.float32) + p * rr * 0.95 for _, p in E.crack_paths()]
    bb = E.roi(np.vstack(ps), 50)
    if bb:
        x0, y0, x1, y1 = bb
        m = np.zeros((y1 - y0, x1 - x0), np.float32)
        cv2.polylines(m, [np.round((p - (x0, y0)) * 4).astype(np.int32) for p in ps], False, 1.0, 10, cv2.LINE_AA, 2)
        pul = 0.75 + 0.25 * math.sin(c.t * 6)
        c.fr[y0:y1, x0:x1] *= (1 - 0.7 * a * m)[..., None]
        add_layer(c.fr[y0:y1, x0:x1], cv2.GaussianBlur(m, (0, 0), 10), (20, 90, 255), a * 2.2 * pul)
        add_layer(c.fr[y0:y1, x0:x1], cv2.GaussianBlur(m, (0, 0), 2), (80, 200, 255), a * 1.6 * pul)
    rng = np.random.default_rng(27)                                 # zeravy popol stupa
    for i in range(30):
        b = rng.uniform(0, 1.5); px = c.cx + rng.normal(0, rr * 0.4)
        u = ((c.dt - b) % 1.5) / 1.5
        y = c.cy + rng.normal(0, rr * 0.3) - 320 * u
        x = px + 20 * math.sin(c.t * 4 + i)
        if c.dt > b:
            cv2.circle(c.fr, (int(x), int(y)), 3, tuple(v * a * (1 - u) for v in (90, 200, 255)), -1, cv2.LINE_AA)


def fx_season_swap(c):
    a = c.out
    u = ease((c.dt - 0.1) / 1.0)
    if u > 0:
        yl = YT - 200 + (H + 400 - YT) * u                           # zmena prechadza zhora nadol
        hsv = cv2.cvtColor(np.clip(c.fr, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
        hue = hsv[..., 0]
        green = np.clip(1 - np.abs(hue - 55) / 35, 0, 1)
        hsv[..., 0] = hue * (1 - green) + 14 * green
        hsv[..., 1] = np.minimum(255, hsv[..., 1] * (1 + 0.6 * green) + 30)
        aut = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)
        aut = aut * np.array([0.82, 0.95, 1.12], np.float32)      # teply ton aj tam, kde nie je zelen
        m = np.clip((yl - E._yy[:, :1]) / 150, 0, 1)[..., None] * a
        c.fr[:] = c.fr * (1 - m) + aut * m
    rng = np.random.default_rng(28)                                 # padajuce listy
    for i in range(36):
        b = rng.uniform(0, 1.2)
        if c.dt < b:
            continue
        age = c.dt - b
        x = rng.uniform(0, W) + 60 * math.sin(age * 2.5 + i); y = -40 + age * rng.uniform(260, 420)
        if y > YB:
            continue
        ang = age * 180 * rng.uniform(0.5, 1.5) + i * 40
        col = ((20, 90, 230), (30, 150, 245), (25, 60, 190))[i % 3]
        cv2.ellipse(c.fr, (int(x), int(y)), (16, 8), ang, 0, 360, tuple(v * a for v in col), -1, cv2.LINE_AA)
    label(c, c.f.get("label", "AUTUMN").upper(), 330, 56, col=(255, 200, 90, 255), a=a * cl(c.dt / 0.4))


def fx_tide_timelapse(c):
    a = life(c, 3.0, 0.3)
    if a <= 0:
        return
    ph = c.dt / 2.6 * 2 * math.pi
    lvl = 0.5 - 0.5 * math.cos(ph)                                  # nizka -> vysoka -> nizka
    ya, yb = 520.0, YB - 30
    y0 = yb + (ya - yb) * lvl
    xs = np.arange(0, W, 8, dtype=np.float32)
    edge = y0 + 10 * np.sin(xs / 50 + c.t * 5)
    iy = int(max(0, edge.min()))
    msk = (E._yy[iy:] >= np.interp(E._xx[0], xs, edge)[None, :]).astype(np.float32)
    m = (cv2.GaussianBlur(msk, (0, 0), 4) * 0.42 * a)[..., None]
    c.fr[iy:] = c.fr[iy:] * (1 - m) + np.array([200, 135, 40], np.float32) * m
    E.glow_lines(c.fr, [np.stack([xs, edge], 1)], CY_, 5, core=(255, 255, 240), alpha=a)
    hrs = int(6 + 12 * cl(c.dt / 2.6)) % 24
    label(c, f"{hrs:02d}:00", 330, 64, col=(255, 255, 255, 255), a=a)
    label(c, "HIGH TIDE" if lvl > 0.5 else "LOW TIDE", int(min(YB - 80, max(430, y0 - 100))), 48, col=(255, 240, 78, 255), a=a)


def fx_earthquake_shake(c):
    a = c.out
    amp = 30 * math.exp(-c.dt * 1.6) * cl(c.dt / 0.05)
    if amp > 0.5:
        ox = amp * math.sin(c.t * 61) * math.cos(c.t * 17); oy = amp * 0.8 * math.sin(c.t * 47 + 1)
        rot = amp * 0.03 * math.sin(c.t * 33)
        M = cv2.getRotationMatrix2D((W / 2, H / 2), rot, 1.03)
        M[:, 2] += (ox, oy)
        c.fr[:] = cv2.warpAffine(c.fr, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    for j in range(4):
        u = (c.dt - 0.18 * j) / 1.3
        if 0 <= u < 1:
            r = 25 + min(c.R, 520) * 1.2 * eout(u)
            E.glow_lines(c.fr, [ring_pts(c.cx, c.cy, r, r * 0.92)], (40, 120, 255), max(2, int(9 * (1 - u))), closed=True,
                         core=(150, 220, 255), alpha=a * (1 - u))
    if c.dt < 2.0:
        lab = f"M {c.f['n']:.1f}" if c.f.get("n") else "TREMOR"
        s = 1 + 0.06 * math.sin(c.t * 40) * math.exp(-c.dt * 2)
        E.paste_scaled(c.fr, E.text_rgba(lab, 72, fill=(255, 255, 255, 255), box=(30, 40, 200, 220), pad=16), W / 2, 380,
                       E.back_ease(c.dt, 0.3) * s, a * cl((2.0 - c.dt) / 0.3))


def fx_ice_crack_spread(c):
    a = life(c, 2.8, 0.05)
    if a <= 0:
        return
    k = 0.3 * a * cl(c.dt / 0.8)                                    # mrazivy nadych
    c.fr[:] = c.fr * (1 - k) + (c.fr.mean(2, keepdims=True) * 0.6 + np.array([255, 230, 200], np.float32) * 0.4) * k
    ps = []
    for j, (ox, oy, sc, rot, d0) in enumerate(((0, 0, 1.0, 0, 0.0), (-0.9, 0.7, 0.6, 1.1, 0.35), (0.85, -0.8, 0.65, 2.3, 0.6))):
        g = ease((c.dt - d0) / 0.7)
        if g <= 0:
            continue
        rr = min(c.R, 380) * 1.3 * sc
        ca, sa = math.cos(rot), math.sin(rot)
        o = np.array([c.cx + ox * min(c.R, 380), c.cy + oy * min(c.R, 380)], np.float32)
        for s0, p in E.crack_paths():
            u = (g - s0) / max(0.05, 1 - s0)
            if u > 0:
                q = E.open_part(p, u) @ np.array([[ca, sa], [-sa, ca]], np.float32)
                ps.append(o + q * rr)
    if not ps:
        return
    bb = E.roi(np.vstack(ps), 10)
    if bb:
        x0, y0, x1, y1 = bb
        m = np.zeros((y1 - y0, x1 - x0), np.float32)
        cv2.polylines(m, [np.round((p - (x0, y0)) * 4).astype(np.int32) for p in ps], False, 1.0, 7, cv2.LINE_AA, 2)
        c.fr[y0:y1, x0:x1] *= (1 - 0.6 * a * m)[..., None]
    E.glow_lines(c.fr, ps, (255, 230, 170), 4, core=(255, 255, 255), alpha=a)


# ================================================================== skener / data
def fx_radar_blips(c):
    a = life(c, 2.8, 0.3)
    if a <= 0:
        return
    rr = min(max(c.R * 1.1, 260), 440)
    bb = E.roi(np.array([[c.cx - rr, c.cy - rr], [c.cx + rr, c.cy + rr]], np.float32), 4)
    if not bb:
        return
    x0, y0, x1, y1 = bb
    dx, dy = E._xx[y0:y1, x0:x1] - c.cx, E._yy[y0:y1, x0:x1] - c.cy
    d = np.hypot(dx, dy); disc = np.clip((rr - d) / 4, 0, 1)
    sw = (c.dt * 2 * math.pi / 1.5 - math.pi / 2)
    diff = (sw - np.arctan2(dy, dx)) % (2 * math.pi)
    trail = np.exp(-diff / 0.7) * disc
    sub = c.fr[y0:y1, x0:x1]
    sub *= (1 - 0.45 * a * disc)[..., None]
    sub += (trail * a * 150)[..., None] * np.array([0.45, 1.0, 0.5], np.float32)
    G = (110, 255, 120)
    E.glow_lines(c.fr, [ring_pts(c.cx, c.cy, rr * k) for k in (0.33, 0.66, 1.0)], G, 3, closed=True, core=(200, 255, 200), alpha=a * 0.7)
    E.glow_lines(c.fr, [np.array([[c.cx - rr, c.cy], [c.cx + rr, c.cy]], np.float32),
                        np.array([[c.cx, c.cy - rr], [c.cx, c.cy + rr]], np.float32),
                        np.array([[c.cx, c.cy], [c.cx + rr * math.cos(sw), c.cy + rr * math.sin(sw)]], np.float32)],
                 G, 3, core=(220, 255, 220), alpha=a * 0.8)
    rng = np.random.default_rng(29)
    for i in range(6):
        ang = rng.uniform(0, 2 * math.pi); r = rr * rng.uniform(0.2, 0.85)
        dd = (sw - ang) % (2 * math.pi); passed = c.dt * 2 * math.pi / 1.5 > ((ang + math.pi / 2) % (2 * math.pi))
        if not passed:
            continue
        k = math.exp(-dd / 2.2)
        bx, by = c.cx + r * math.cos(ang), c.cy + r * math.sin(ang)
        cv2.circle(c.fr, (int(bx), int(by)), int(9 + 10 * k), tuple(v * a * (0.4 + 0.6 * k) * 1.4 for v in (90, 255, 120)), -1, cv2.LINE_AA)
    label(c, f"{6 if c.dt > 1.5 else int(c.dt / 0.25)} SIGNALS", y0 - 80 if y0 > YT + 80 else YT, 44, col=(140, 255, 150, 255), a=a)


def fx_scan_line_sweep(c):
    a = life(c, 2.6, 0.2)
    if a <= 0:
        return
    u = c.dt / 2.0
    y = YT + (YB - YT) * (ease(u * 2) if u < 0.5 else ease(2 - u * 2))
    ya = int(max(0, y - 160)); yb_ = int(min(H, y + 160))
    g = np.exp(-np.abs(E._yy[ya:yb_, :1] - y) / 55)
    c.fr[ya:yb_] += (g * 70 * a)[..., None] * np.array([1.0, 0.95, 0.35], np.float32)
    c.fr[YT:YB:6] *= 1 - 0.12 * a                                    # skenovacie riadky
    E.glow_lines(c.fr, [np.array([[0, y], [W, y]], np.float32)], CY_, 6, core=(255, 255, 240), alpha=a)
    pct = int(100 * cl(c.dt / 2.0))
    label(c, f"ANALYSIS {pct}%", y - 80, 40, col=(255, 240, 160, 255), x=W - 420, a=a)
    rng = np.random.default_rng(30)
    for i in range(4):
        bx, by = c.cx + rng.uniform(-300, 300), c.cy + rng.uniform(-300, 300)
        by = min(YB - 60, max(YT + 40, by))
        if (by < y) == (u < 0.5) or c.dt > 1.0 and u >= 0.5:
            s = rng.uniform(40, 80)
            box = [np.array([[bx - s, by - s], [bx + s, by - s], [bx + s, by + s], [bx - s, by + s], [bx - s, by - s]], np.float32)]
            E.glow_lines(c.fr, box, YL_, 3, core=(220, 255, 255), alpha=a * 0.9)


def fx_grid_overlay(c):
    a = life(c, 2.8, 0.5)
    if a <= 0:
        return
    lat, lon, z = c.cam
    dpp = 360 / (256 * 2 ** z)
    step = next((s for s in (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20) if s / dpp >= 230), 30)
    gx = []
    lo0 = math.floor((lon - W / 2 * dpp) / step) * step
    lo = lo0
    while lo < lon + W / 2 * dpp + step:
        x, _ = E.screen_xy(lat, lo, c.cam); gx.append((x, lo)); lo += step
    gy = []
    la = math.floor((lat - H * dpp) / step) * step
    while la < lat + H * dpp:
        _, y = E.screen_xy(la, lon, c.cam)
        if -10 < y < H + 10:
            gy.append((y, la))
        la += step
    polys = []
    for i, (x, _) in enumerate(gx):
        u = cl((c.dt - 0.05 * abs(x - W / 2) / 100) / 0.6)
        if u > 0:
            polys.append(np.array([[x, c.cy - 900 * u], [x, c.cy + 900 * u]], np.float32))
    for y, _ in gy:
        u = cl((c.dt - 0.05 * abs(y - c.cy) / 100) / 0.6)
        if u > 0:
            polys.append(np.array([[W / 2 - 700 * u, y], [W / 2 + 700 * u, y]], np.float32))
    E.glow_lines(c.fr, polys, CY_, 2, core=(255, 255, 230), alpha=a * 0.75)
    fmt = (lambda v: f"{v:.2f}") if step < 0.1 else ((lambda v: f"{v:.1f}") if step < 1 else (lambda v: f"{v:.0f}"))
    for y, la in gy:
        if YT < y < YB - 60:
            label(c, f"{fmt(abs(la))}°{'N' if la >= 0 else 'S'}", y - 40, 30, col=(255, 240, 160, 255), x=12, a=a * 0.9, box=(0, 0, 0, 130))
    for x, lo in gx:
        if 60 < x < W - 160:
            label(c, f"{fmt(abs(lo))}°{'E' if lo >= 0 else 'W'}", YT + 10, 30, col=(255, 240, 160, 255), x=x + 6, a=a * 0.9, box=(0, 0, 0, 130))
    s = E.back_ease(c.dt - 0.4, 0.3)
    if s > 0.05:
        E.glow_lines(c.fr, [np.array([[c.cx - 60 * s, c.cy], [c.cx + 60 * s, c.cy]], np.float32),
                            np.array([[c.cx, c.cy - 60 * s], [c.cx, c.cy + 60 * s]], np.float32),
                            ring_pts(c.cx, c.cy, 34 * s)], YL_, 5, core=(220, 255, 255), alpha=a)


def fx_zoom_ruler_ticks(c):
    a = life(c, 2.8, 0.3)
    if a <= 0:
        return
    mpp = E.m_per_px(c.cam[0], c.cam[2])
    km = next((v for v in (0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000) if v * 1000 / mpp >= 420), 5000)
    L = km * 1000 / mpp; u = eout(c.dt / 1.0)
    x0 = W / 2 - L / 2; y = YB - 70
    E.paste_rgba(c.fr, np.dstack([np.zeros((60, int(L) + 60, 3), np.uint8), np.full((60, int(L) + 60), 120, np.uint8)]),
                 int(x0 - 30), int(y - 30), a * cl(c.dt / 0.3))
    polys = [np.array([[x0, y], [x0 + L * u, y]], np.float32)]
    for i in range(11):
        tx = x0 + L * i / 10
        if tx <= x0 + L * u + 1:
            h = 22 if i % 5 == 0 else 12
            polys.append(np.array([[tx, y - h], [tx, y]], np.float32))
    E.glow_lines(c.fr, polys, (255, 255, 255), 4, core=(255, 255, 255), alpha=a)
    v = km * u
    txt = (f"{v * 1000:.0f} M" if km < 1 else (f"{v:.0f} KM" if km >= 5 else f"{v:.1f} KM"))
    label(c, txt, y - 100, 44, a=a, x=x0 + L * u - 60, box=None)
    label(c, "0", y - 100, 44, a=a, x=x0 - 20, box=None)


def fx_label_arrow_pop(c):
    a = c.out
    s = E.back_ease(c.dt, 0.35)
    if s <= 0.03:
        return
    bob = 18 * math.sin(c.t * 6)
    tip = np.array([c.cx + 30, c.cy - 30 + bob * 0.3])
    d = np.array([0.6, -0.8]); n = np.array([0.8, 0.6])
    L = 230 * s
    p0 = tip + d * (20 + bob); p1 = tip + d * (20 + bob + L)
    head = [p0, p0 + d * 70 * s + n * 45 * s, p0 + d * 70 * s - n * 45 * s]
    shaft = [p0 + d * 60 * s + n * 16 * s, p1 + n * 16 * s, p1 - n * 16 * s, p0 + d * 60 * s - n * 16 * s]
    ov = c.fr.copy()
    for poly in (head, shaft):                                       # tien + sipka
        fpoly(ov, np.array(poly) + (5, 7), (30, 30, 30))
    fpoly(ov, head, (40, 214, 255)); fpoly(ov, shaft, (40, 214, 255))
    c.fr[:] = c.fr * (1 - a) + ov * a
    txt = c.f.get("label", "LOOK HERE").upper()
    lab = E.text_rgba(txt, 58, fill=(20, 20, 20, 255), box=(255, 214, 40, 245), pad=18)
    lx = min(W - lab.shape[1] / 2 - 20, max(lab.shape[1] / 2 + 20, p1[0]))
    ly = max(YT + 40, p1[1] - 40)
    E.paste_scaled(c.fr, lab, lx, ly, E.back_ease(c.dt - 0.15, 0.3), a)
    u = (c.dt % 1.2) / 1.2
    E.glow_lines(c.fr, [ring_pts(c.cx, c.cy, 20 + 70 * u)], YL_, max(2, int(6 * (1 - u))), closed=True, alpha=a * (1 - u))


def fx_silhouette_outline(c):
    a = c.out
    pts = E.feature_px(c.spec, c.cam)
    ctr = pts.mean(0)
    u = ease(c.dt / 0.8)
    if c.dt < 0.8:
        E.glow_lines(c.fr, [E.poly_part(pts, u)], YL_, 9, alpha=a)
    else:
        cl_ = np.vstack([pts, pts[:1]])
        seg = np.hypot(*np.diff(cl_, axis=0).T); cum = np.concatenate([[0], np.cumsum(seg)]); tot = cum[-1]
        dash, gap = 46.0, 26.0; off = (c.t * 120) % (dash + gap); ds = []
        s = -off
        while s < tot:
            s0, s1 = max(0, s), min(tot, s + dash)
            if s1 > s0:
                q = np.linspace(s0, s1, 6)
                ds.append(np.stack([np.interp(q, cum, cl_[:, 0]), np.interp(q, cum, cl_[:, 1])], 1).astype(np.float32))
            s += dash + gap
        E.glow_lines(c.fr, ds, YL_, 9, alpha=a)
        bb = E.roi(pts, 4)
        if bb:
            x0, y0, x1, y1 = bb
            m = np.zeros((y1 - y0, x1 - x0), np.float32)
            cv2.fillPoly(m, [np.round((pts - (x0, y0)) * 16).astype(np.int32)], 1.0, cv2.LINE_AA, 4)
            k = (0.12 + 0.08 * math.sin(c.t * 5)) * a
            c.fr[y0:y1, x0:x1] += (m * k)[..., None] * np.array(YL_, np.float32)
        e = (c.dt - 0.8) / 0.8                                       # ozvena obrysu
        if 0 <= e < 1:
            E.glow_lines(c.fr, [ctr + (pts - ctr) * (1 + 0.35 * eout(e))], YL_, 4, closed=True, alpha=a * (1 - e))
    if c.f.get("label"):
        label(c, c.f["label"].upper(), 330, 56, col=(255, 214, 40, 255), a=a * cl((c.dt - 0.6) / 0.3))


def fx_magnifier_lens(c):
    a = c.out
    u = eout(c.dt / 0.7)
    if u <= 0:
        return
    r = 200; zoom = 1 + 1.6 * ease((c.dt - 0.3) / 0.8)
    lx = c.cx + 260 * (1 - u) + 30 * math.sin(c.t * 1.3) * u; ly = c.cy + 360 * (1 - u) + 20 * math.cos(c.t * 1.1) * u
    ly = min(YB - r - 60, max(YT + r, ly)); lx = min(W - r - 10, max(r + 10, lx))
    src = c.fr.copy()
    sr = r / zoom
    x0, y0 = int(lx - sr), int(ly - sr)
    patch = cv2.getRectSubPix(src, (int(2 * sr) + 1, int(2 * sr) + 1), (lx, ly))
    big = cv2.resize(patch, (2 * r, 2 * r), interpolation=cv2.INTER_CUBIC)
    big = np.clip(big * 1.08 + 6, 0, 255)                              # sklo: jemne jasnejsie
    yy, xx = np.mgrid[0:2 * r, 0:2 * r].astype(np.float32)
    d = np.hypot(xx - r, yy - r)
    m = np.clip(r - d, 0, 1)[..., None] * a * u
    bx0, by0 = int(lx - r), int(ly - r)
    sub = c.fr[by0:by0 + 2 * r, bx0:bx0 + 2 * r]
    if sub.shape[:2] == (2 * r, 2 * r):
        hl = np.clip(1 - np.hypot(xx - r * 0.6, yy - r * 0.55) / (r * 0.5), 0, 1)[..., None] ** 2 * 60
        sub[:] = sub * (1 - m) + (big + hl) * m
    hx, hy = lx + r * 0.72, ly + r * 0.72                             # rucka
    cv2.line(c.fr, (int(hx + 6), int(hy + 10)), (int(hx + 150 + 6), int(hy + 150 + 10)), tuple(v * a for v in (20, 20, 20)), 40, cv2.LINE_AA)
    cv2.line(c.fr, (int(hx), int(hy)), (int(hx + 150), int(hy + 150)), tuple(v * a for v in (40, 70, 110)), 34, cv2.LINE_AA)
    cv2.circle(c.fr, (int(lx), int(ly)), r + 8, tuple(v * a for v in (25, 25, 25)), 18, cv2.LINE_AA)
    cv2.circle(c.fr, (int(lx), int(ly)), r + 8, tuple(v * a for v in (230, 230, 230)), 8, cv2.LINE_AA)
    if c.dt > 0.6:
        label(c, f"x{zoom:.1f}", ly - r - 70, 40, a=a, x=lx - 40)


def fx_pixel_reveal(c):
    a = c.out
    rr = int(min(max(c.R, 220), 430))
    x0, y0 = int(max(0, c.cx - rr)), int(max(YT - 40, c.cy - rr)); x1, y1 = int(min(W, c.cx + rr)), int(min(YB, c.cy + rr))
    if x1 - x0 < 20 or y1 - y0 < 20:
        return
    lv = (96, 64, 40, 24, 14, 8, 4, 2, 1)
    i = min(len(lv) - 1, int(cl(c.dt / 1.5) * len(lv)))
    b = lv[i]
    sub = c.fr[y0:y1, x0:x1]
    if b > 1:
        sm = cv2.resize(sub, (max(1, (x1 - x0) // b), max(1, (y1 - y0) // b)), interpolation=cv2.INTER_AREA)
        px = cv2.resize(sm, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
        sub[:] = sub * (1 - a) + px * a
    L = 60
    cs = [np.array([[px_, py_ + sy * L], [px_, py_], [px_ + sx * L, py_]], np.float32)
          for px_, py_, sx, sy in ((x0 + 6, y0 + 6, 1, 1), (x1 - 6, y0 + 6, -1, 1), (x0 + 6, y1 - 6, 1, -1), (x1 - 6, y1 - 6, -1, -1))]
    E.glow_lines(c.fr, cs, CY_, 6, core=(255, 255, 230), alpha=a)
    txt = "ENHANCING" + "." * (int(c.dt * 6) % 4) if b > 1 else "RESOLVED"
    label(c, txt, max(YT - 20, y0 - 80), 40, col=(255, 240, 160, 255) if b > 1 else (140, 255, 150, 255), x=x0, a=a)


def fx_flicker_glitch(c):
    a = c.out * cl((1.4 - c.dt) / 0.2)
    if a <= 0:
        return
    fi = int(c.t * E.FPS)
    rng = np.random.default_rng(fi * 13 + 5)
    if c.dt > 0.5 and rng.random() < 0.45:                          # vypadky: nie kazdy snimok
        return
    k = int(rng.integers(8, 26))
    c.fr[..., 0] = np.roll(c.fr[..., 0], -k, 1); c.fr[..., 2] = np.roll(c.fr[..., 2], k, 1)
    for _ in range(int(rng.integers(3, 8))):
        y = int(rng.integers(0, H - 40)); h = int(rng.integers(8, 70)); s = int(rng.integers(-120, 120))
        c.fr[y:y + h] = np.roll(c.fr[y:y + h], s, 1)
    for _ in range(int(rng.integers(1, 4))):
        x, y = int(rng.integers(0, W - 200)), int(rng.integers(0, H - 60))
        col = ((255, 0, 255), (255, 255, 0), (0, 255, 255))[int(rng.integers(0, 3))]
        c.fr[y:y + int(rng.integers(10, 40)), x:x + int(rng.integers(60, 260))] = col
    c.fr[::4] *= 0.8
    if rng.random() < 0.7:
        label(c, "SIGNAL ERROR", 360 + int(rng.integers(-6, 6)), 64, col=(255, 70, 70, 255), a=a)


def fx_color_shift(c):
    a = c.out
    src = c.fr.copy()
    def fcol():                                                     # falosne farby (termo): jas -> turbo, lokalny kontrast
        gr = cv2.cvtColor(np.clip(src, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY)
        gr = cv2.createCLAHE(3.0, (8, 8)).apply(gr)
        return cv2.applyColorMap(gr, cv2.COLORMAP_TURBO).astype(np.float32)
    fc = fcol()
    sw = ease((c.dt - 1.0) / 0.7)
    xl = -40 + (W + 80) * sw
    m = np.clip((E._xx[:1] - xl) / 30, 0, 1)[..., None]               # vpravo od ciary este falosne farby
    c.fr[:] = src * (1 - m * a) + fc * (m * a)
    if 0 < sw < 1:
        E.glow_lines(c.fr, [np.array([[xl, 0], [xl, H]], np.float32)], (255, 255, 255), 6, alpha=a)
    label(c, "FALSE COLOR" if sw < 0.5 else "TRUE COLOR", 330, 56, col=(255, 110, 110, 255) if sw < 0.5 else (140, 255, 150, 255), a=a)


def fx_heat_map_bloom(c):
    a = life(c, 2.8, 0.3)
    if a <= 0:
        return
    rr = min(max(c.R, 200), 440); q = 4
    rng = np.random.default_rng(31)
    blobs = [(rng.normal(0, 0.35), rng.normal(0, 0.35), rng.uniform(0.18, 0.4), rng.uniform(0.5, 1.0)) for _ in range(7)]
    blobs[0] = (0.0, 0.0, 0.35, 1.0)
    g = ease(c.dt / 1.2)
    ys = (E._yy[::q, ::q] - c.cy) / rr; xs = (E._xx[::q, ::q] - c.cx) / rr
    I = np.zeros_like(ys)
    for bx, by, s, w in blobs:
        I += w * np.exp(-((xs - bx) ** 2 + (ys - by) ** 2) / (2 * (s * (0.3 + 0.7 * g)) ** 2))
    I = np.clip(I / 1.3 * (0.92 + 0.08 * math.sin(c.t * 5)), 0, 1)
    cm = cv2.applyColorMap((I * 255).astype(np.uint8), cv2.COLORMAP_JET).astype(np.float32)
    al = np.clip((I - 0.06) * 1.4, 0, 0.72) * a * g
    al = cv2.resize(al, (W, H))[..., None]; cm = cv2.resize(cm, (W, H))
    c.fr[:] = c.fr * (1 - al) + cm * al
    lx, ly = W - 330, YT + 20                                       # legenda
    bar = cv2.applyColorMap(np.tile(np.linspace(0, 255, 260).astype(np.uint8), (24, 1)), cv2.COLORMAP_JET)
    E.paste_rgba(c.fr, np.dstack([bar[..., ::-1], np.full((24, 260), 230, np.uint8)]), lx, ly + 60, a)
    label(c, "LOW", ly + 88, 30, x=lx - 6, a=a, box=None); label(c, "HIGH", ly + 88, 30, x=lx + 200, a=a, box=None)
    label(c, c.f.get("label", "HOTSPOT").upper(), ly - 10, 40, x=lx, a=a)


def fx_population_dots_fx(c):
    a = c.out
    rr = min(max(c.R, 220), 420)
    def mk():
        rng = np.random.default_rng(32)
        P = rng.normal(0, 0.42, (260, 2)); P = P[np.hypot(P[:, 0], P[:, 1]) < 1.1]
        return P, rng.permutation(len(P))
    P, order = cache(("pop",), mk)
    u = eout(c.dt / 1.6); n = int(len(P) * u)
    lay = np.zeros((H // 2, W // 2), np.float32)
    for j in order[:n]:
        x, y = c.cx + P[j, 0] * rr, c.cy + P[j, 1] * rr
        cv2.circle(lay, (int(x / 2), int(y / 2)), 4, 1.0, -1, cv2.LINE_AA)
    glow = cv2.GaussianBlur(lay, (0, 0), 4) * 1.6
    add_layer(c.fr, glow, CY_, a * 0.8)
    over_layer(c.fr, cv2.GaussianBlur(lay, (0, 0), 0.6), (255, 255, 255), a)
    N = c.f.get("n")
    txt = f"{int(N * u):,} {c.f.get('label', 'PEOPLE')}" if N else c.f.get("label", "PEOPLE")
    label(c, txt, 330, 60, col=(255, 240, 78, 255), a=a * cl(c.dt / 0.3))


def fx_bar_race(c):
    a = c.out
    labs = [str(s).upper() for s in c.f.get("labels", ["THIS", "TYPICAL"])][:2]
    vals = [float(v) for v in c.f.get("values", [3, 1])][:2]
    mx = max(vals) or 1
    x0, wmax = 300, W - 300 - 70
    for i in range(2):
        u = eout((c.dt - 0.2 * i) / 1.3)
        if u <= 0:
            continue
        y = 380 + i * 130; w = max(8, wmax * vals[i] / mx * u)
        col = (40, 214, 255) if i == 0 else (200, 200, 200)
        sh = np.zeros((96, int(wmax) + 20, 4), np.uint8); sh[..., 3] = 140
        E.paste_rgba(c.fr, sh, x0 - 10, int(y - 8), a)
        cv2.rectangle(c.fr, (x0, int(y)), (int(x0 + w), int(y + 80)), tuple(v * a for v in col), -1, cv2.LINE_AA)
        label(c, labs[i], y + 6, 44, x=40, a=a, box=(0, 0, 0, 165))
        v = vals[i] * u
        vt = f"{v:,.0f}" if mx >= 10 else f"{v:.1f}".rstrip("0").rstrip(".") + "x"
        lab = E.text_rgba(vt + (" " + c.f["unit"] if c.f.get("unit") else ""), 42, fill=(20, 20, 20, 255) if i == 0 else (40, 40, 40, 255), box=None, pad=8)
        E.paste_rgba(c.fr, lab, int(max(x0 + 6, x0 + w - lab.shape[1] - 8)), int(y + 40 - lab.shape[0] / 2), a)


def fx_number_slot_roll(c):
    a = c.out
    n = int(c.f.get("n") or 0)
    digs = f"{n:,}"
    cw, ch = 96, 140; tot = len(digs) * cw
    x0 = W / 2 - tot / 2; y = 360
    s = E.back_ease(c.dt, 0.3)
    if s <= 0.05:
        return
    sh = np.zeros((ch + 40, tot + 40, 4), np.uint8); sh[..., :3] = (20, 20, 30); sh[..., 3] = 220
    E.paste_rgba(c.fr, sh, int(x0 - 20), int(y - 20), a)
    di = 0
    for i, chh in enumerate(digs):
        cx = x0 + i * cw + cw / 2
        if chh == ",":
            g = E.glyph(",", 100, (255, 255, 255, 255), sw=5)
            E.paste_rgba(c.fr, g, int(cx - g.shape[1] / 2), int(y + ch / 2 - g.shape[0] / 2 + 20), a); continue
        stop = 0.6 + 0.25 * di; di += 1
        u = cl(c.dt / stop)
        roll = (1 - eout(u)) * (20 + 6 * di)                         # kolko cifier este pretoci
        val = (int(chh) + roll) % 10
        base = int(val); fr_ = val - base
        bounce = 12 * math.sin(min(1.0, (c.dt - stop) / 0.25) * math.pi) * (c.dt > stop)
        for k, dd in ((0, 0), (1, 1)):
            d = (base + dd) % 10
            g = E.glyph(str(d), 120, (255, 214, 40, 255) if c.dt > stop else (255, 255, 255, 255), sw=6)
            yy = y + ch / 2 - g.shape[0] / 2 + (fr_ - dd) * ch * -1 + bounce
            if dd == 0:
                yy = y + ch / 2 - g.shape[0] / 2 - fr_ * ch + bounce
            else:
                yy = y + ch / 2 - g.shape[0] / 2 + (1 - fr_) * ch + bounce
            gg = g.copy()
            top, bot = int(y - yy), int(y + ch - yy)                  # orez na okienko
            gg[:max(0, top)] = 0; gg[max(0, bot):] = 0
            E.paste_rgba(c.fr, gg, int(cx - g.shape[1] / 2), int(yy), a)
    E.glow_lines(c.fr, [np.array([[x0 - 20, y - 20], [x0 + tot + 20, y - 20], [x0 + tot + 20, y + ch + 20],
                                  [x0 - 20, y + ch + 20], [x0 - 20, y - 20]], np.float32)], YL_, 4, alpha=a)
    if c.f.get("label"):
        label(c, c.f["label"].upper(), y + ch + 40, 46, a=a * cl((c.dt - 0.6) / 0.3))


def fx_time_counter(c):
    a = c.out
    n = float(c.f.get("n") or 1000); v = n * eout(c.dt / 1.6)
    s = E.back_ease(c.dt, 0.3)
    txt = f"{int(v):,}"
    lab = E.text_rgba(txt, 110, fill=(255, 214, 40, 255), box=(0, 0, 0, 0), pad=8)
    unit = c.f.get("unit", "YEARS AGO" if c.f.get("ago", True) else "YEARS")
    lab2 = E.text_rgba(unit.upper(), 50, fill=(255, 255, 255, 255), box=None, pad=8)
    wb = max(lab.shape[1], lab2.shape[1]) + 60
    bg = np.zeros((lab.shape[0] + lab2.shape[0] + 30, wb, 4), np.uint8); bg[..., 3] = 175
    E.paste_scaled(c.fr, bg, W / 2, 330 + bg.shape[0] / 2, s, a)
    jit = 0 if c.dt > 1.6 else 4 * math.sin(c.t * 60)
    E.paste_scaled(c.fr, lab, W / 2, 330 + lab.shape[0] / 2 + 10 + jit, s, a)
    E.paste_scaled(c.fr, lab2, W / 2, 330 + lab.shape[0] + lab2.shape[0] / 2 + 10, s, a)
    for i in range(5):                                             # rychle pasiky = cas leti
        u = (c.dt * 2.2 + i / 5) % 1
        if c.dt < 1.6:
            y = 330 + bg.shape[0] + 20 + i * 9
            E.glow_lines(c.fr, [np.array([[W / 2 - 200 + 400 * u, y], [W / 2 - 120 + 400 * u, y]], np.float32)], YL_, 2, alpha=a * 0.6)


def fx_clock_spin(c):
    a = c.out
    s = E.back_ease(c.dt, 0.35)
    if s <= 0.05:
        return
    OX, OY, r = W - 200, 470, 150 * s
    cv2.circle(c.fr, (OX + 6, OY + 8), int(r + 10), (20, 20, 20), -1, cv2.LINE_AA)
    x0, y0 = OX - 200, OY - 200
    sub = c.fr[y0:OY + 200, x0:OX + 200]
    ov = sub.copy(); ox, oy = OX - x0, OY - y0                     # kreslenie len vo vyreze (rychlost)
    cv2.circle(ov, (ox, oy), int(r + 10), (40, 40, 40), -1, cv2.LINE_AA)
    cv2.circle(ov, (ox, oy), int(r), (245, 245, 245), -1, cv2.LINE_AA)
    for i in range(12):
        an = i / 12 * 2 * math.pi; l = 0.18 if i % 3 == 0 else 0.1
        cv2.line(ov, (int(ox + r * (1 - l) * math.sin(an)), int(oy - r * (1 - l) * math.cos(an))),
                 (int(ox + r * 0.93 * math.sin(an)), int(oy - r * 0.93 * math.cos(an))), (30, 30, 30), 6 if i % 3 == 0 else 3, cv2.LINE_AA)
    u = eout(c.dt / 2.2); mt = 10 * 2 * math.pi * u; hr = mt / 12
    for k in range(4, -1, -1):                                       # rozmazanie pohybu
        dk = k * 0.05 * (1 - u) * 6
        al = 1.0 if k == 0 else 0.18
        for ang, ln, th, col in ((hr - dk / 12, 0.5, 12, (30, 30, 30)), (mt - dk, 0.78, 7, (48, 59, 230))):
            p = (int(ox + r * ln * math.sin(ang)), int(oy - r * ln * math.cos(ang)))
            o2 = ov.copy(); cv2.line(o2, (ox, oy), p, col, th, cv2.LINE_AA)
            ov = ov * (1 - al) + o2 * al
    cv2.circle(ov, (ox, oy), 12, (30, 30, 30), -1, cv2.LINE_AA)
    sub[:] = sub * (1 - a) + ov * a
    label(c, c.f.get("label", "24 H").upper(), OY + r + 30, 44, x=OX - 70, a=a)


def fx_thermometer(c):
    a = c.out
    n = float(c.f["n"]) if c.f.get("n") is not None else 50.0
    unit = c.f.get("unit", "C")
    lo, hi = (-40.0, 60.0) if unit == "C" else (-40.0, 140.0)
    s = E.back_ease(c.dt, 0.35)
    if s <= 0.05:
        return
    x, top, bot = W - 140, 430, 1060
    u = eout((c.dt - 0.3) / 1.4); v = lo + (min(max(n, lo), hi) - lo) * u
    hot = n >= 20
    col = (40, 50, 235) if hot else (235, 160, 40)
    ov = c.fr.copy()
    cv2.rectangle(ov, (x - 34, top - 20), (x + 34, bot), (25, 25, 25), -1, cv2.LINE_AA)
    cv2.circle(ov, (x, bot + 40), 66, (25, 25, 25), -1, cv2.LINE_AA)
    cv2.rectangle(ov, (x - 24, top - 10), (x + 24, bot), (235, 235, 235), -1, cv2.LINE_AA)
    cv2.circle(ov, (x, bot + 40), 56, col, -1, cv2.LINE_AA)
    ly = bot - (bot - top) * (v - lo) / (hi - lo)
    cv2.rectangle(ov, (x - 16, int(ly)), (x + 16, bot + 10), col, -1, cv2.LINE_AA)
    for i in range(11):
        ty = top + (bot - top) * i / 10
        cv2.line(ov, (x - 24, int(ty)), (x - 8 if i % 5 else x, int(ty)), (40, 40, 40), 3, cv2.LINE_AA)
    c.fr[:] = c.fr * (1 - a * cl(s)) + ov * a * cl(s)
    label(c, f"{v:.0f}°{unit}", ly - 40, 60, col=(255, 90, 80, 255) if hot else (120, 200, 255, 255), x=x - 260, a=a)


def fx_compass_spin(c):
    a = c.out
    s = E.back_ease(c.dt, 0.35)
    if s <= 0.05:
        return
    ox, oy, r = W - 200, 480, 150 * s
    ov = c.fr.copy()
    cv2.circle(ov, (ox, oy), int(r + 12), (30, 30, 30), -1, cv2.LINE_AA)
    cv2.circle(ov, (ox, oy), int(r), (70, 60, 45), -1, cv2.LINE_AA)
    cv2.circle(ov, (ox, oy), int(r), (200, 200, 210), 4, cv2.LINE_AA)
    for i in range(16):
        an = i / 16 * 2 * math.pi; l = 0.16 if i % 4 == 0 else 0.07
        cv2.line(ov, (int(ox + r * (1 - l) * math.sin(an)), int(oy - r * (1 - l) * math.cos(an))),
                 (int(ox + r * 0.95 * math.sin(an)), int(oy - r * 0.95 * math.cos(an))), (230, 230, 230), 3, cv2.LINE_AA)
    c.fr[:] = c.fr * (1 - a) + ov * a
    for t_, an in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
        g = E.glyph(t_, int(40 * s) + 4, (255, 90, 80, 255) if t_ == "N" else (255, 255, 255, 255), sw=3)
        E.paste_rgba(c.fr, g, int(ox + r * 0.66 * math.sin(math.radians(an)) - g.shape[1] / 2),
                     int(oy - r * 0.66 * math.cos(math.radians(an)) - g.shape[0] / 2), a)
    u = cl(c.dt / 2.0)
    ang = math.radians(c.f.get("deg", 0)) + 4 * math.pi * (1 - eout(u)) + 0.5 * math.exp(-5 * u) * math.sin(14 * u)
    sa, ca = math.sin(ang), math.cos(ang)
    tipN = (ox + r * 0.55 * sa, oy - r * 0.55 * ca); tipS = (ox - r * 0.55 * sa, oy + r * 0.55 * ca)
    w = (ox + 16 * ca, oy + 16 * sa); w2 = (ox - 16 * ca, oy - 16 * sa)
    fpoly(c.fr, [tipN, w, w2], tuple(v * a for v in (48, 59, 240)))
    fpoly(c.fr, [tipS, w, w2], tuple(v * a for v in (235, 235, 235)))
    cv2.circle(c.fr, (ox, oy), 10, tuple(v * a for v in (40, 214, 255)), -1, cv2.LINE_AA)


def fx_mini_globe_pin(c):
    a = c.out
    s = E.back_ease(c.dt, 0.35)
    if s <= 0.05:
        return
    st = c.spec.get("start") or c.spec["beats"][0]["cam"]
    lat0, lon0 = st["lat"], st["lon"]
    D = 300; R = D / 2 - 10
    rot = (1 - eout(c.dt / 1.2)) * 120
    def tex():
        t = E.globe_tex()
        return cv2.resize(t, (1024, 1024), interpolation=cv2.INTER_AREA)
    tx = cache(("gtex",), tex); n = tx.shape[0]
    yy, xx = np.mgrid[0:D, 0:D].astype(np.float32)
    x = (xx - D / 2) / R; y = -(yy - D / 2) / R
    rho = np.sqrt(x * x + y * y); inside = rho < 1
    cc = np.arcsin(np.clip(rho, 0, 1)); p0 = math.radians(max(-60, min(60, lat0))); l0 = math.radians(lon0 + rot)
    rs = np.where(rho == 0, 1e-9, rho)
    la = np.arcsin(np.clip(np.cos(cc) * math.sin(p0) + y * np.sin(cc) * math.cos(p0) / rs, -1, 1))
    lo = l0 + np.arctan2(x * np.sin(cc), rs * np.cos(cc) * math.cos(p0) - y * np.sin(cc) * math.sin(p0))
    mx = ((np.degrees(lo) + 180) % 360) / 360 * n
    my = (1 - np.arcsinh(np.tan(np.clip(la, -1.48, 1.48))) / math.pi) / 2 * n
    img = cv2.remap(tx, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP).astype(np.float32)
    img *= np.clip(np.cos(cc) * 0.6 + 0.55, 0, 1)[..., None]
    rim = np.exp(-np.abs(rho - 1) * R / 6)[..., None] * np.array([255, 170, 90], np.float32)
    al = np.clip((1 - rho) * R, 0, 1)
    rgba = np.dstack([np.clip(img + rim * 0.8, 0, 255)[..., ::-1], al * 255]).astype(np.uint8)
    gx, gy = W - 200, 500
    sh = np.zeros((D + 40, D + 40, 4), np.uint8); cv2.circle(sh, (D // 2 + 20, D // 2 + 20), int(R + 14), (0, 0, 0, 150), -1, cv2.LINE_AA)
    E.paste_scaled(c.fr, sh, gx, gy, s * 0.8, a)
    E.paste_scaled(c.fr, rgba, gx, gy, s * 0.8, a)
    # spendlik: lokalita je po dotoceni v strede glóbusu (posun podla lat0 vs p0)
    k = E.back_ease(c.dt - 1.1, 0.3)
    if k > 0.05:
        px, py = gx, gy - math.sin(math.radians(lat0) - p0) * R * 0.8
        py -= 30 * (1 - min(1.0, k))
        cv2.line(c.fr, (int(px), int(py)), (int(px), int(py - 46 * k)), tuple(v * a for v in (240, 240, 240)), 5, cv2.LINE_AA)
        cv2.circle(c.fr, (int(px), int(py - 46 * k)), int(15 * k), tuple(v * a for v in (48, 59, 255)), -1, cv2.LINE_AA)
        u = ((c.dt - 1.1) % 1.0)
        cv2.circle(c.fr, (int(px), int(py)), int(8 + 26 * u), tuple(v * a * (1 - u) for v in (48, 59, 255)), 3, cv2.LINE_AA)


def fx_orbit_path(c):
    a = c.out
    rx, ry, tilt = 470, 150, math.radians(-14)
    ct, st_ = math.cos(tilt), math.sin(tilt)
    ang = np.linspace(0, 2 * math.pi, 140)
    def P(an):
        x, y = rx * np.cos(an), ry * np.sin(an)
        return np.stack([c.cx + x * ct - y * st_, c.cy - 60 + x * st_ + y * ct], -1).astype(np.float32)
    pts = P(ang)
    u = ease(c.dt / 0.9)
    back = pts[(np.sin(ang) < 0)]; front = pts[(np.sin(ang) >= 0)]
    n = int(len(pts) * u)
    E.glow_lines(c.fr, [pts[:max(2, n)]], CY_, 4, core=(255, 255, 230), alpha=a * 0.9)
    sa = c.dt * 2 * math.pi / 2.2 + math.pi * 0.25
    sx, sy = P(np.array([sa]))[0]
    if c.dt > 0.5:
        k = cl((c.dt - 0.5) / 0.3) * a
        if math.sin(sa) > 0.75:                                      # nad miestom: luc
            tri = np.array([[sx, sy], [c.cx - 70, c.cy + 10], [c.cx + 70, c.cy + 10]], np.float32)
            ov = c.fr.copy(); fpoly(ov, tri, (255, 240, 120))
            c.fr[:] = c.fr * (1 - 0.22 * k) + ov * 0.22 * k
        cv2.rectangle(c.fr, (int(sx - 13), int(sy - 13)), (int(sx + 13), int(sy + 13)), tuple(v * k for v in (220, 220, 230)), -1, cv2.LINE_AA)
        for sgn in (-1, 1):
            x0 = sx + sgn * 18; x1 = sx + sgn * 62
            cv2.rectangle(c.fr, (int(min(x0, x1)), int(sy - 10)), (int(max(x0, x1)), int(sy + 10)), tuple(v * k for v in (170, 90, 30)), -1, cv2.LINE_AA)
            cv2.line(c.fr, (int(sx + sgn * 13), int(sy)), (int(x0), int(sy)), tuple(v * k for v in (200, 200, 200)), 3, cv2.LINE_AA)
        bl = 0.5 + 0.5 * math.sin(c.t * 12)
        cv2.circle(c.fr, (int(sx), int(sy - 18)), 5, tuple(v * k * bl for v in (60, 60, 255)), -1, cv2.LINE_AA)
    if c.dt > 0.3:
        label(c, c.f.get("label", "ORBIT PASS").upper(), 330, 50, col=(255, 240, 160, 255), a=a * cl((c.dt - 0.3) / 0.3))


def fx_depth_sounding(c):
    a = life(c, 2.8, 0.3)
    if a <= 0:
        return
    bot = min(YB - 40.0, c.cy + 560)
    ya, yb = int(c.cy), int(min(H, bot + 160))
    v_ = (E._yy[ya:yb, :1] - c.cy) / (bot - c.cy)
    g = np.clip(v_, 0, 1) * np.clip((1.3 - v_) / 0.3, 0, 1)            # tmavne do hlbky, dole makko zanikne
    g = g * np.clip(1 - np.abs(E._xx[:1] - c.cx) / 420, 0, 1)           # len stlpec pod miestom
    c.fr[ya:yb] *= (1 - 0.55 * a * g)[..., None]
    c.fr[ya:yb] += (g * 30 * a)[..., None] * np.array([1.0, 0.5, 0.1], np.float32)
    for j in range(6):
        u = (c.dt - 0.32 * j) / 1.6
        if 0 <= u < 1:
            y = c.cy + (bot - c.cy) * ease(u)
            rx = 220 * (1 - 0.55 * u) + 40
            E.glow_lines(c.fr, [ring_pts(c.cx, y, rx, rx * 0.28)], CY_, max(2, int(7 * (1 - u))), closed=True,
                         core=(255, 255, 230), alpha=a * (1 - u * 0.8))
    dashes = [np.array([[c.cx, y], [c.cx, y + 18]], np.float32) for y in np.arange(c.cy, bot, 34)]
    E.glow_lines(c.fr, dashes, CY_, 3, alpha=a * 0.7)
    v = eout(c.dt / 1.8)
    txt = f"-{int(c.f['n'] * v):,} {c.f.get('unit', 'M')}" if c.f.get("n") else "SOUNDING" + "." * (int(c.dt * 5) % 4)
    label(c, txt, c.cy + (bot - c.cy) * v - 30, 50, col=(255, 240, 78, 255), x=c.cx + 60, a=a)


def fx_shockwave_ring(c):
    a = c.out
    u = c.dt / 1.3
    if u >= 1:
        return
    r = 30 + 1000 * eout(u); wd = 60 + 40 * u; amp = 36 * (1 - u)
    pd = r + 2.6 * wd
    x0, y0 = int(max(0, c.cx - pd)), int(max(0, c.cy - pd)); x1, y1 = int(min(W, c.cx + pd)), int(min(H, c.cy + pd))
    if x1 - x0 > 4 and y1 - y0 > 4:
        dx, dy = E._xx[y0:y1, x0:x1] - c.cx, E._yy[y0:y1, x0:x1] - c.cy
        d = np.hypot(dx, dy) + 1e-3
        k = np.exp(-((d - r) / wd) ** 2)
        off = amp * k * np.sin((d - r) / wd * 3)
        mx = E._xx[y0:y1, x0:x1] - dx / d * off; my = E._yy[y0:y1, x0:x1] - dy / d * off
        sub = cv2.remap(c.fr, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        sub += (k * 60 * (1 - u) * a)[..., None]
        c.fr[y0:y1, x0:x1] = sub
    E.glow_lines(c.fr, [ring_pts(c.cx, c.cy, r, n=160)], (255, 255, 255), max(2, int(10 * (1 - u))), closed=True, alpha=a * (1 - u))
    if c.dt < 0.25:
        fl = (1 - c.dt / 0.25) * 0.55 * a
        c.fr[:] = c.fr * (1 - fl) + 255 * fl


def fx_ripple_water(c):
    a = life(c, 2.8, 0.1)
    if a <= 0:
        return
    rr = min(max(c.R, 250), 480)
    x0, y0 = int(max(0, c.cx - rr)), int(max(0, c.cy - rr)); x1, y1 = int(min(W, c.cx + rr)), int(min(H, c.cy + rr))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return
    dx, dy = E._xx[y0:y1, x0:x1] - c.cx, E._yy[y0:y1, x0:x1] - c.cy
    d = np.hypot(dx, dy) + 1e-3
    front = 380 * c.dt
    env = np.clip((front - d) / 60, 0, 1) * np.clip(1 - d / rr, 0, 1) * a
    w = np.sin(d / 22 - c.dt * 12)
    off = 7 * w * env
    sub = cv2.remap(c.fr, E._xx[y0:y1, x0:x1] - dx / d * off, E._yy[y0:y1, x0:x1] - dy / d * off, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    sub += (np.clip(w, 0, 1) ** 4 * env * 70)[..., None] * np.array([1.0, 0.95, 0.85], np.float32)
    c.fr[y0:y1, x0:x1] = sub
    if c.dt < 0.4:
        cv2.circle(c.fr, (int(c.cx), int(c.cy)), int(10 + 30 * c.dt), tuple(255 * a * (1 - c.dt / 0.4) for _ in range(3)), -1, cv2.LINE_AA)


def fx_xray_layers(c):
    a = c.out
    pw = 600; ph = 560
    x0 = int(W / 2 - pw / 2); y0 = int(min(YB - ph, max(YT + 60, c.cy - 40)))
    def bands():
        rng = np.random.default_rng(33)
        cols = [(50, 90, 120), (60, 130, 190), (130, 175, 205), (110, 110, 115), (70, 70, 80), (30, 70, 200)]
        hs = [70, 100, 90, 110, 100, 90]
        img = np.zeros((ph, pw, 3), np.float32); ys = np.arange(ph)[:, None]; xs = np.arange(pw)[None, :]
        edges = [0]; acc = 0
        for h_ in hs:
            acc += h_; edges.append(acc)
        lay_id = np.zeros((ph, pw), np.int32)
        for i in range(1, len(edges) - 1):
            e = edges[i] + 12 * np.sin(xs / (60 + 15 * i) + i * 1.7) + 6 * np.sin(xs / 23 + i)
            lay_id += (ys >= e).astype(np.int32)
        nz = noise(34, ph, pw, (2, 4, 8))
        for i, col in enumerate(cols):
            m = lay_id == i
            img[m] = np.array(col, np.float32)
        img *= (0.75 + 0.5 * nz)[..., None]
        for _ in range(140):                                         # kamienky
            x, y = rng.integers(0, pw), rng.integers(0, ph)
            cv2.circle(img, (int(x), int(y)), int(rng.integers(2, 6)), tuple(float(v) for v in img[y, x] * 0.6), -1, cv2.LINE_AA)
        return img, edges
    img, edges = cache(("xray",), bands)
    u = ease(c.dt / 1.0)
    hh = int(ph * u)
    if hh < 4:
        return
    sub = c.fr[y0:y0 + hh, x0:x0 + pw]
    sh = c.fr[y0 + 12:y0 + hh + 12, x0 + 14:x0 + pw + 14]
    sh *= 1 - 0.5 * a
    reveal = img[:hh].copy()
    lit = np.clip(1 - (np.arange(hh)[:, None] - (hh - 30)) / 30, 0, 1)   # hrana rezu svieti
    reveal += (1 - lit)[..., None] * 90
    sub[:] = sub * (1 - a) + reveal * a
    E.glow_lines(c.fr, [np.array([[x0, y0 + hh], [x0, y0], [x0 + pw, y0], [x0 + pw, y0 + hh]], np.float32)], CY_, 5,
                 core=(255, 255, 230), alpha=a)
    for i in range(1, len(edges) - 1):
        if edges[i] < hh and c.f.get("n"):                           # hlbky len zo skutocneho cisla
            label(c, f"-{edges[i] * int(c.f['n']) // ph:,} {c.f.get('unit', 'M')}", y0 + edges[i] - 26, 32,
                  x=x0 + pw + 12, a=a * cl((hh - edges[i]) / 60), box=(0, 0, 0, 150))
    label(c, "BENEATH THE SURFACE", y0 - 80, 46, col=(255, 240, 160, 255), a=a * cl(c.dt / 0.4))


def fx_split_then_now(c):
    a = c.out
    u = eout(c.dt / 0.7)
    xs = W - (W / 2) * u
    src = c.fr
    g = src.mean(2, keepdims=True)
    old = (g * 0.85 + 20) * np.array([0.62, 0.86, 1.12], np.float32)
    old = cv2.GaussianBlur(old, (0, 0), 1.6)
    m = np.clip((xs - E._xx[:1]) / 3, 0, 1)[..., None] * a
    c.fr[:] = src * (1 - m) + old * m
    E.glow_lines(c.fr, [np.array([[xs, 0], [xs, H]], np.float32)], (255, 255, 255), 6, alpha=a)
    hy = (YT + YB) / 2
    cv2.circle(c.fr, (int(xs), int(hy)), 40, tuple(v * a for v in (255, 255, 255)), -1, cv2.LINE_AA)
    for sg in (-1, 1):
        fpoly(c.fr, [(xs + sg * 30, hy), (xs + sg * 12, hy - 14), (xs + sg * 12, hy + 14)], tuple(v * a for v in (40, 40, 40)))
    labs = c.f.get("labels", ["THEN", "NOW"])
    if u > 0.5:
        label(c, str(labs[0]).upper(), 330, 54, x=xs / 2 - 80, a=a * cl((u - 0.5) * 4), col=(160, 200, 255, 255))
        label(c, str(labs[1]).upper(), 330, 54, x=xs + (W - xs) / 2 - 60, a=a * cl((u - 0.5) * 4))


def fx_tape_unroll(c):
    a = c.out
    L = min(2 * c.R, W - 140); L = max(L, 380)
    x0 = W / 2 - L / 2; y = min(YB - 100, max(YT + 120, c.cy + min(c.R, 400) + 40)) if c.R < 420 else c.cy
    u = eout(c.dt / 1.1); xe = x0 + L * u; th = 58
    if xe - x0 > 2:
        ov = c.fr.copy()
        cv2.rectangle(ov, (int(x0 + 4), int(y - th / 2 + 8)), (int(xe + 4), int(y + th / 2 + 8)), (15, 15, 15), -1)   # tien
        c.fr[:] = c.fr * (1 - 0.45 * a) + ov * 0.45 * a
        ov = c.fr.copy()
        cv2.rectangle(ov, (int(x0), int(y - th / 2)), (int(xe), int(y + th / 2)), (30, 200, 250), -1, cv2.LINE_AA)
        for i in range(int((xe - x0) / 12) + 1):
            tx = x0 + i * 12; h = 24 if i % 10 == 0 else (16 if i % 5 == 0 else 9)
            cv2.line(ov, (int(tx), int(y - th / 2)), (int(tx), int(y - th / 2 + h)), (30, 30, 30), 2, cv2.LINE_AA)
        cv2.rectangle(ov, (int(x0 - 26), int(y - th / 2 - 4)), (int(x0), int(y + th / 2 + 4)), (60, 60, 60), -1, cv2.LINE_AA)
        c.fr[:] = c.fr * (1 - a) + ov * a
    rr = 48 * (1 - 0.5 * u) + 20                                     # rolka na konci
    cv2.circle(c.fr, (int(xe + rr * 0.6), int(y)), int(rr), tuple(v * a for v in (30, 170, 230)), -1, cv2.LINE_AA)
    for k in range(3):
        cv2.circle(c.fr, (int(xe + rr * 0.6), int(y)), int(rr * (0.35 + 0.2 * k)), tuple(v * a for v in (20, 110, 160)), 2, cv2.LINE_AA)
    cv2.circle(c.fr, (int(xe + rr * 0.6), int(y)), int(rr * 0.22), tuple(v * a for v in (60, 60, 60)), -1, cv2.LINE_AA)
    km = float(c.spec.get("feature_km") or 0) if not c.f.get("label") else 0
    txt = c.f.get("label") or (f"{km * u:.1f} KM" if km < 10 else f"{km * u:.0f} KM")
    label(c, txt.upper(), y - th / 2 - 90, 52, a=a * cl(c.dt / 0.3), col=(255, 214, 40, 255))


def fx_footprint_trail(c):
    a = life(c, 2.8, 0.2)
    if a <= 0:
        return
    p0 = np.array([90.0, YB - 40]); p3 = np.array([c.cx, c.cy + 30])
    p1 = np.array([W * 0.75, YB - 200]); p2 = np.array([W * 0.15, (c.cy + YB) / 2])
    ts = np.linspace(0, 1, 400)[:, None]
    B = (1 - ts) ** 3 * p0 + 3 * (1 - ts) ** 2 * ts * p1 + 3 * (1 - ts) * ts ** 2 * p2 + ts ** 3 * p3
    seg = np.hypot(*np.diff(B, axis=0).T); cum = np.concatenate([[0], np.cumsum(seg)])
    step = 80.0; ns = int(cum[-1] / step)
    for i in range(ns):
        tb = i * 0.09
        if c.dt < tb:
            break
        s = i * step; j = int(np.searchsorted(cum, s)); j = min(j, len(B) - 2)
        d = B[j + 1] - B[j]; d /= (np.hypot(*d) + 1e-6); n = np.array([-d[1], d[0]])
        side = 1 if i % 2 else -1
        p = B[j] + n * side * 22
        ang = math.degrees(math.atan2(d[1], d[0]))
        k = cl((c.dt - tb) / 0.12) * a * (0.55 + 0.45 * i / max(1, ns))
        sole = p + d * 9; heel = p - d * 22
        for q, ax in ((sole, (24, 14)), (heel, (14, 11))):
            cv2.ellipse(c.fr, (int(q[0] + 3), int(q[1] + 4)), ax, ang, 0, 360, (0, 0, 0), -1, cv2.LINE_AA)
        ov = c.fr.copy()
        for q, ax in ((sole, (24, 14)), (heel, (14, 11))):
            cv2.ellipse(ov, (int(q[0]), int(q[1])), ax, ang, 0, 360, (245, 250, 255), -1, cv2.LINE_AA)
        x0, y0 = int(max(0, p[0] - 40)), int(max(0, p[1] - 40)); x1, y1 = int(min(W, p[0] + 40)), int(min(H, p[1] + 40))
        c.fr[y0:y1, x0:x1] = c.fr[y0:y1, x0:x1] * (1 - k) + ov[y0:y1, x0:x1] * k


# ================================================================== register
EFFECTS = {
    "lightning_flash": fx_lightning_flash, "shockwave_ring": fx_shockwave_ring, "earthquake_shake": fx_earthquake_shake,
    "radar_blips": fx_radar_blips, "magnifier_lens": fx_magnifier_lens, "xray_layers": fx_xray_layers,
    "split_then_now": fx_split_then_now, "pixel_reveal": fx_pixel_reveal, "flicker_glitch": fx_flicker_glitch,
    "meteor_streak": fx_meteor_streak, "ash_cloud": fx_ash_cloud, "lava_glow": fx_lava_glow,
    "night_lights_on": fx_night_lights_on, "terminator_sweep": fx_terminator_sweep, "aurora_ribbons": fx_aurora_ribbons,
    "star_field": fx_star_field, "snow_fall": fx_snow_fall, "rain_streaks": fx_rain_streaks, "sand_drift": fx_sand_drift,
    "fog_roll": fx_fog_roll, "heat_shimmer": fx_heat_shimmer, "wind_arrows": fx_wind_arrows,
    "ripple_water": fx_ripple_water, "ice_crack_spread": fx_ice_crack_spread, "season_swap": fx_season_swap,
    "tide_timelapse": fx_tide_timelapse, "heat_map_bloom": fx_heat_map_bloom, "color_shift": fx_color_shift,
    "scan_line_sweep": fx_scan_line_sweep, "grid_overlay": fx_grid_overlay, "zoom_ruler_ticks": fx_zoom_ruler_ticks,
    "label_arrow_pop": fx_label_arrow_pop, "silhouette_outline": fx_silhouette_outline,
    "population_dots_fx": fx_population_dots_fx, "bar_race": fx_bar_race, "number_slot_roll": fx_number_slot_roll,
    "time_counter": fx_time_counter, "clock_spin": fx_clock_spin, "thermometer": fx_thermometer,
    "compass_spin": fx_compass_spin, "mini_globe_pin": fx_mini_globe_pin, "orbit_path": fx_orbit_path,
    "depth_sounding": fx_depth_sounding, "tape_unroll": fx_tape_unroll, "footprint_trail": fx_footprint_trail,
}

# zvuk k efektu (engine mix_audio): whoosh / riser / pop / tick / boom / ping
SOUND = {
    "lightning_flash": "boom", "shockwave_ring": "boom", "earthquake_shake": "boom", "meteor_streak": "whoosh",
    "ash_cloud": "whoosh", "radar_blips": "ping", "depth_sounding": "ping", "magnifier_lens": "pop",
    "label_arrow_pop": "pop", "bar_race": "riser", "number_slot_roll": "tick", "time_counter": "tick",
    "clock_spin": "tick", "compass_spin": "tick", "pixel_reveal": "riser", "flicker_glitch": "glitch",
    "scan_line_sweep": "riser", "split_then_now": "whoosh", "color_shift": "whoosh", "terminator_sweep": "whoosh",
    "wind_arrows": "whoosh", "sand_drift": "whoosh", "fog_roll": "whoosh", "tape_unroll": "riser",
    "mini_globe_pin": "pop", "orbit_path": "riser", "xray_layers": "riser", "ripple_water": "pop",
    "ice_crack_spread": "crack", "population_dots_fx": "tick", "thermometer": "riser", "silhouette_outline": "riser",
}


def draw(kind, fr, t, dt, cx, cy, R, out, f, cam, spec):
    fn = EFFECTS.get(kind)
    if fn is None:
        return False
    c = Ctx()
    c.fr, c.t, c.dt, c.cx, c.cy, c.R, c.out, c.f, c.cam, c.spec = fr, t, dt, cx, cy, R, out, f, cam, spec
    c.rr = min(R, 420)
    fn(c)
    return True


# ================================================================== vyber podla slov (write_spec)
NUMW = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "twice": 2, "double": 2, "triple": 3, "hundred": 100}


def _num(s):
    m = re.search(r"(-?[\d][\d,.]*)", s or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "").rstrip("."))
    except ValueError:
        return None


def _stamp_num(nb):
    return _num((nb.get("stamp") or {}).get("label", ""))


# (kind, regex slova, extra) - poradie = priorita (specificke pred vseobecnymi)
TRIGGERS = [
    ("lightning_flash", r"\b(lightning|thunder\w*|storm\w*)\b"),
    ("aurora_ribbons", r"\b(auror\w*|northern lights)\b"),
    ("meteor_streak", r"\b(meteor\w*|comet\w*|shooting stars?)\b"),
    ("ash_cloud", r"\b(erupt\w*|ash|plume\w*|smoke)\b"),
    ("lava_glow", r"\b(lava|magma|molten|volcan\w*)\b"),
    ("earthquake_shake", r"\b(earthquake\w*|quake\w*|tremor\w*|seismic|fault line)\b"),
    ("shockwave_ring", r"\b(blast\w*|explo\w*|shock ?wave\w*|boom)\b"),
    ("ice_crack_spread", r"\b(glacier\w*|calving|ice sheet|ice shelf|frozen lake)\b"),
    ("snow_fall", r"\b(snow\w*|blizzard\w*)\b"),
    ("rain_streaks", r"\b(rain\w*|monsoon\w*|downpour\w*)\b"),
    ("sand_drift", r"\b(dunes?|sand\w*)\b"),
    ("fog_roll", r"\b(fog\w*|mist\w*|haze|hazy)\b"),
    ("heat_shimmer", r"\b(scorching|blistering|hottest|heat\w*|boiling)\b"),
    ("thermometer", r"\b(degrees?|celsius|fahrenheit|temperature\w*)\b"),
    ("wind_arrows", r"\b(winds?|gusts?|currents?|jet stream)\b"),
    ("tide_timelapse", r"\b(tides?|tidal)\b"),
    ("ripple_water", r"\b(ripple\w*|pond|still water|drops? into)\b"),
    ("night_lights_on", r"\b(city lights|lights up|at night|lit up)\b"),
    ("terminator_sweep", r"\b(sunrise|sunset|daylight|darkness|night)\b"),
    ("star_field", r"\b(stars|starry|night sky|cosmic|milky way)\b"),
    ("season_swap", r"\b(autumn|fall colou?rs?|seasons?)\b"),
    ("orbit_path", r"\b(orbit\w*|satellites?|overhead)\b"),
    ("radar_blips", r"\b(radar|signals?|detect\w*|hidden)\b"),
    ("xray_layers", r"\b(beneath|underground|layers?|underneath|buried)\b"),
    ("depth_sounding", r"\b(ocean floor|seabed|sea floor|trench\w*|sonar)\b"),
    ("compass_spin", r"\b(north\w*|south\w*|compass|magnetic|direction)\b"),
    ("footprint_trail", r"\b(walk\w*|footprints?|trail\w*|journey|hik\w*|steps)\b"),
    ("population_dots_fx", r"\b(people|residents|population|inhabitants|villagers)\b"),
    ("split_then_now", r"\b(used to|once was|back then|nowadays|decades ago)\b"),
    ("color_shift", r"\b(true colou?r|false colou?r|infrared|actually looks)\b"),
    ("pixel_reveal", r"\b(reveal\w*|unmask\w*|resolv\w*|blurr\w*|enhanc\w*)\b"),
    ("flicker_glitch", r"\b(glitch\w*|error|corrupt\w*|anomal\w*|censor\w*|blurred out)\b"),
    ("magnifier_lens", r"\b(closer|tiny|detail\w*|zoom\w*)\b"),
    ("silhouette_outline", r"\b(shape\w*|resembl\w*|looks like|outline\w*)\b"),
    ("heat_map_bloom", r"\b(hotspots?|concentrat\w*|densest)\b"),
    ("clock_spin", r"\b(hours?|daily|every day|per day)\b"),
    ("grid_overlay", r"\b(coordinates|latitude|longitude|located)\b"),
    ("mini_globe_pin", r"\b(continent|hemisphere|middle of nowhere|remote)\b"),
    ("tape_unroll", r"\b(stretch\w*|spans?|(?:kilomet\w*|miles?|met(?:er|re)s?) (?:long|wide|across))\b"),
    ("zoom_ruler_ticks", r"\b(kilomet\w*|miles?|scale)\b"),
    ("scan_line_sweep", r"\b(scann\w*|analy\w*|reading|survey\w*)\b"),
    ("label_arrow_pop", r"\b(notice|right here|that spot|this spot|look at)\b"),
]


def _extra(kind, txt, nb, m):
    """parametre efektu; None = efekt sa nehodi (chyba cislo a pod.). Ziadne vymyslene cisla."""
    n = _stamp_num(nb)
    st = (nb.get("stamp") or {}).get("label", "")
    w = m.group(0).lower()
    if kind == "thermometer":
        m2 = re.search(r"(-?\d+)\s*°?\s*(C|F)\b", st) or \
            re.search(r"(-?\d+)\s*(?:°|degrees?)\s*(c|f)?(?:elsius|ahrenheit)?\b", txt, re.I)
        return {"n": int(m2.group(1)), "unit": (m2.group(2) or "C").upper()} if m2 else None
    if kind == "population_dots_fx":
        lab = w.upper()
        tn = _num(txt)
        if (n or tn or 0) >= 10:
            return {"n": int(n or tn), "label": lab}
        return None if w == "people" else {"label": lab}            # "people say..." nie je pocet ludi
    if kind == "bar_race":
        v = int(m.group(1)) if m.group(1).isdigit() else NUMW[m.group(1).lower()]
        return {"labels": ["THIS", m.group(4).upper()[:12]], "values": [v, 1]}
    if kind in ("time_counter", "number_slot_roll"):
        tn = _num(txt)                                                # cislo z textu (peciatka uz cislo ukazuje sama)
        return {"n": int(tn)} if tn and tn >= 10 else None
    if kind == "clock_spin":
        return {"label": "HOURS"} if w.startswith("hour") else {"label": "24 H"}
    if kind == "season_swap":
        return {"label": "AUTUMN"} if re.match(r"autumn|fall", w) else {"label": "SEASONS"}
    if kind == "depth_sounding":
        m = re.search(r"([\d,.]+)\s*(M|METERS?|METRES?|FT|FEET)\b", st)
        return {"n": int(float(m.group(1).replace(",", ""))), "unit": "FT" if m.group(2).startswith("F") else "M"} if m else {}
    if kind == "terminator_sweep":
        return {"dir": -1} if re.search(r"\b(sunrise|daylight|dawn)\b", txt, re.I) else {"dir": 1}
    return {}


EXTRA_TRIGGERS = [                                                    # efekty len s cislom v texte / peciatke
    ("bar_race", r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten|twice)\s+(times\s+)?(bigger|larger|longer|wider|deeper|taller|higher|hotter|saltier) than (?:a |an |the |any )?([a-z]+)"),
    ("time_counter", r"\b(years|centuries|millenni\w*)\b"),
    ("number_slot_roll", r"\b(exactly|precisely|counted|total of)\b"),
]


TOP_LABEL = {"terminator_sweep", "season_swap", "tide_timelapse", "population_dots_fx", "bar_race", "number_slot_roll",
             "time_counter", "orbit_path", "split_then_now", "color_shift", "flicker_glitch", "earthquake_shake"}
ASK_OK = {"label_arrow_pop", "magnifier_lens", "grid_overlay", "radar_blips", "pixel_reveal", "mini_globe_pin", "scan_line_sweep"}


def pick(txt, nb, used=(), have=()):
    """Vrati jeden novy efekt {"kind","on",...} pre text beatu, alebo None. used = uz pouzite vo videu,
    have = druhy efektov uz v beate (nekombinovat s podobnymi)."""
    clash = {"rewind": TOP_LABEL, "sea": {"tide_timelapse"}, "water": {"ripple_water", "tide_timelapse"},
             "depth": {"depth_sounding", "xray_layers"}, "cracks": {"ice_crack_spread", "lava_glow"},
             "trace": {"silhouette_outline"}, "scan": {"scan_line_sweep", "radar_blips"}}
    banned = set(used)
    for k in have:
        banned |= clash.get(k, set())
    if "stamp" in nb:                                                 # peciatka v strede hore -> nie dalsi napis na tom istom mieste
        banned |= TOP_LABEL
    for kind, rx in EXTRA_TRIGGERS + TRIGGERS:
        if kind in banned:
            continue
        m = re.search(rx, txt, re.I)
        if not m:
            continue
        sent = re.search(r"[^.?!]*$", txt[:m.start()]).group(0) + re.match(r"[^.?!]*[.?!]?", txt[m.start():]).group(0)
        if sent.rstrip().endswith("?") and kind not in ASK_OK:
            continue                                                  # "A volcano? A river?" -> ziadna lava
        ex = _extra(kind, txt, nb, m)
        if ex is None:
            continue
        ws = re.findall(r"[a-z0-9']+", m.group(0).lower()); on = max(reversed(ws), key=len)   # "at night" -> "night", nie "at"
        return dict({"kind": kind, "on": on}, **ex)
    return None

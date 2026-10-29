"""Curio ORBIT engine - "Google Earth zahady" format (vzor: ulozeny reel C2SNZy0gL-x, fake drone/Earth prelet).
Ziadny stock, ziadne AI obrazky: skutocne satelitne snimky (Esri World Imagery dlazdice).
Glóbus z vesmiru -> let na suradnice -> plynuly satelitny zoom (prelínanie urovni dlazdic, ziadne preskakovanie),
vyhladavaci riadok s pisanim suradnic, citac vysky kamery, cerveny kruh / meranie / pin / peciatka presne na slove.
Hlas kokoro + whisper casy slov, titulky po 3 slovach (cisla a klucove slova zlte), klik pisania + whoosh pri prelete.

Pouzitie: python orbit/orbit_engine.py orbit/specs/<spec>.json [out.mp4]
"""
import difflib, json, math, os, re, subprocess, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import cv2
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
FF = CFG.get("ffmpeg", "ffmpeg")
W, H, FPS, SR = 1080, 1920, 30, 24000
PAUSE = 0.22
TILE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
UA = {"User-Agent": "Curio/1.0 (educational science channel)"}
TDIR = os.path.join(ROOT, "assets", "tiles_esri")
FONT = os.path.join(ROOT, "assets", "fonts", "Poppins-SemiBold.ttf")
RED = (48, 59, 255)          # BGR
YEL = (40, 214, 255)
GLOBE_T = 2.3                # trvanie glóbusu
GLOBE_ZEND = 5.3             # zoom, na ktorom glóbus prechadza do plochej mapy
GLOBE_LEVEL = 4              # textura glóbusu (16x16 dlazdic)


# ---------------------------------------------------------------- geo
def merc(lat, lon, z):
    wz = 256 * 2 ** z
    lat = max(-85.0, min(85.0, lat))
    return (lon + 180) / 360 * wz, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * wz


def m_per_px(lat, z):
    return 156543.03 * math.cos(math.radians(lat)) / 2 ** z


def ease(u):
    u = min(1.0, max(0.0, u))
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def dms(v, pos, neg):
    h = pos if v >= 0 else neg
    v = abs(v); d = int(v); m = int((v - d) * 60); s = int(round(((v - d) * 60 - m) * 60))
    if s == 60:
        m, s = m + 1, 0
    return f"{d}°{m:02d}'{s:02d}\"{h}"


# ---------------------------------------------------------------- dlazdice
_tiles = {}
def tile_path(z, x, y):
    return os.path.join(TDIR, str(z), str(y), f"{x}.jpg")


def fetch(key):
    z, x, y = key
    p = tile_path(z, x, y)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return
    os.makedirs(os.path.dirname(p), exist_ok=True)
    for a in range(4):
        try:
            d = urllib.request.urlopen(urllib.request.Request(TILE.format(z=z, x=x, y=y), headers=UA), timeout=30).read()
            open(p, "wb").write(d); return
        except Exception:
            time.sleep(2 + 3 * a)
    open(p, "wb").write(b"")                    # chyba -> prazdna (ciern) dlazdica, nezhodi render


def get_tile(z, x, y):
    n = 2 ** z
    x %= n
    if y < 0 or y >= n:
        return None
    k = (z, x, y)
    if k not in _tiles:
        p = tile_path(z, x, y)
        im = cv2.imread(p) if os.path.exists(p) and os.path.getsize(p) > 0 else None
        if len(_tiles) > 3000:
            _tiles.clear()
        _tiles[k] = im
    return _tiles[k]


def level_window(lat, lon, z, L):
    s = 2 ** (z - L)
    cx, cy = merc(lat, lon, L)
    hw, hh = W / 2 / s + 2, H / 2 / s + 2
    return int(math.floor((cx - hw) / 256)), int(math.floor((cy - hh) / 256)), \
        int(math.floor((cx + hw) / 256)), int(math.floor((cy + hh) / 256)), cx, cy, s


def levels_for(z):
    L = int(math.floor(z)); fr = z - L
    t = fr * fr * (3 - 2 * fr)                 # smoothstep prelinanie dvoch urovni
    out = []
    if 1 - t > 0.01:
        out.append((L, 1 - t))
    if t > 0.01:
        out.append((L + 1, t))
    return out


def render_level(lat, lon, z, L):
    tx0, ty0, tx1, ty1, cx, cy, s = level_window(lat, lon, z, L)
    mos = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 3), np.uint8)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            im = get_tile(L, tx, ty)
            if im is not None:
                mos[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = im[:256, :256]
    M = np.float32([[s, 0, s * (tx0 * 256 - cx) + W / 2], [0, s, s * (ty0 * 256 - cy) + H / 2]])
    return cv2.warpAffine(mos, M, (W, H), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT)


def render_flat(lat, lon, z):
    acc = None
    for L, w in levels_for(z):
        im = render_level(lat, lon, z, L).astype(np.float32) * w
        acc = im if acc is None else acc + im
    return acc


# ---------------------------------------------------------------- glóbus
_globe_tex = None
def globe_tex():
    global _globe_tex
    if _globe_tex is None:
        n = 2 ** GLOBE_LEVEL
        t = np.zeros((n * 256, n * 256, 3), np.uint8)
        for y in range(n):
            for x in range(n):
                im = get_tile(GLOBE_LEVEL, x, y)
                if im is not None:
                    t[y * 256:(y + 1) * 256, x * 256:(x + 1) * 256] = im[:256, :256]
        _globe_tex = t
    return _globe_tex


_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
_rng = np.random.default_rng(3)
STARS = np.zeros((H, W), np.float32)
for _ in range(420):
    sy, sx = int(_rng.integers(0, H)), int(_rng.integers(0, W))
    STARS[sy, sx] = float(_rng.uniform(0.25, 1.0)) * 255
STARS = cv2.GaussianBlur(STARS, (0, 0), 0.7)[..., None] * 1.6


def render_globe(lat0, lon0, R):
    tex = globe_tex(); n = tex.shape[0]
    x = (_xx - W / 2) / R; y = -(_yy - H / 2) / R
    rho = np.sqrt(x * x + y * y)
    inside = rho < 1.0
    c = np.arcsin(np.clip(rho, 0, 1))
    p0, l0 = math.radians(lat0), math.radians(lon0)
    rs = np.where(rho == 0, 1e-9, rho)
    lat = np.arcsin(np.clip(np.cos(c) * math.sin(p0) + y * np.sin(c) * math.cos(p0) / rs, -1, 1))
    lon = l0 + np.arctan2(x * np.sin(c), rs * np.cos(c) * math.cos(p0) - y * np.sin(c) * math.sin(p0))
    latc = np.clip(lat, -1.4844, 1.4844)
    mx = ((np.degrees(lon) + 180) % 360) / 360 * n
    my = (1 - np.arcsinh(np.tan(latc)) / math.pi) / 2 * n
    img = cv2.remap(tex, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    img = img.astype(np.float32)
    shade = np.clip(np.cos(c) * 0.55 + 0.6, 0, 1)[..., None]       # stmavnutie k okraju
    out = np.where(inside[..., None], img * shade, STARS)
    glow = np.exp(-np.clip(rho - 1, 0, None) * R / 28.0) * (rho >= 1)
    rim = np.exp(-np.abs(rho - 1) * R / 10.0)
    out = out + (glow * 0.85 + rim * 0.35)[..., None] * np.array([255, 170, 90], np.float32)
    return out


# ---------------------------------------------------------------- hlas + casy
def tts(spec, beats, work):
    from kokoro_onnx import Kokoro
    md = r"C:\Users\damia\kokoro" if os.path.exists(r"C:\Users\damia\kokoro\kokoro-v1.0.onnx") else os.path.join(ROOT, "kokoro")
    os.makedirs(md, exist_ok=True)
    for fn in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):          # GitHub runner: stiahni model, ak chyba
        if not os.path.exists(os.path.join(md, fn)):
            print("   stahujem", fn)
            urllib.request.urlretrieve("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/" + fn,
                                       os.path.join(md, fn))
    k = Kokoro(os.path.join(md, "kokoro-v1.0.onnx"), os.path.join(md, "voices-v1.0.bin"))
    parts, cur = [], 0.35                       # 0,35 s na nabeh pisania suradnic
    parts.append(np.zeros(int(cur * SR), np.float32))
    for b in beats:
        s, sr = k.create(b["text"], voice=spec.get("voice", "am_michael"), speed=float(spec.get("speed", 1.0)))
        b["t0"] = cur
        parts += [s, np.zeros(int(PAUSE * SR), dtype=s.dtype)]
        cur += len(s) / sr
        b["t_end_voice"] = cur
        cur += PAUSE
        b["t1"] = cur
    voice = np.concatenate(parts)
    sf.write(os.path.join(work, "voice.wav"), voice, SR)
    return voice, cur


def word_times(beats, work):
    from faster_whisper import WhisperModel
    m = WhisperModel("base.en", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(os.path.join(work, "voice.wav"), word_timestamps=True, language="en")
    ww = [(re.sub(r"[^a-z0-9]", "", w.word.lower()), w.start, w.end) for sg in segs for w in (sg.words or [])]
    orig = [{"t": t, "k": re.sub(r"[^a-z0-9]", "", t.lower()), "b": b} for b in beats for t in b["text"].split()]
    sm = difflib.SequenceMatcher(a=[o["k"] for o in orig], b=[w[0] for w in ww], autojunk=False)
    for a, bb, n in sm.get_matching_blocks():
        for j in range(n):
            orig[a + j]["s"], orig[a + j]["e"] = ww[bb + j][1], ww[bb + j][2]
    i = 0
    while i < len(orig):
        if "s" in orig[i]:
            i += 1; continue
        j = i
        while j < len(orig) and "s" not in orig[j]:
            j += 1
        lo = orig[i - 1]["e"] if i > 0 else orig[i]["b"]["t0"]
        hi = orig[j]["s"] if j < len(orig) else orig[i]["b"]["t_end_voice"]
        tot = sum(len(o["k"]) + 1 for o in orig[i:j]); t = lo
        for o in orig[i:j]:
            d = (hi - lo) * (len(o["k"]) + 1) / tot
            o["s"], o["e"] = t, t + d; t += d
        i = j
    return orig


def word_at(words, beat, needle, default):
    for w in words:
        if w["b"] is beat and needle and str(needle).lower() in w["k"]:
            return w["s"]
    return beat["t0"] + default


def ass_time(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def build_ass(words, keys, work):
    # titulky vedla Orbiho (ako keby hovoril on): zarovnane vlavo-stred od x=480, zalomenie do 560 px
    st = "Style: C,Poppins SemiBold,74,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,1,0,1,6,2,4,480,40,0,1"
    lines = ["[Script Info]", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
             st, "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) == 3 or cur[-1]["b"] is not w["b"] or re.search(r"[.,?!]$", cur[-1]["t"])):
            chunks.append(cur); cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    for i, ch in enumerate(chunks):
        end = chunks[i + 1][0]["s"] if i + 1 < len(chunks) and chunks[i + 1][0]["b"] is ch[0]["b"] else ch[-1]["e"] + 0.2
        txt = []
        for w in ch:
            t = re.sub(r"[^\w'’\-?]", "", w["t"]).upper()
            hot = any(c.isdigit() for c in t) or w["k"] in keys
            txt.append("{\\c&H0033D4FF&}" + t + "{\\c&H00FFFFFF&}" if hot else t)
        lines.append(f"Dialogue: 0,{ass_time(ch[0]['s'])},{ass_time(max(end, ch[0]['s'] + 0.2))},C,,0,0,0,,"
                     "{\\an4\\pos(480,1575)\\fscx108\\fscy108\\t(0,90,\\fscx100\\fscy100)}" + " ".join(txt))
    open(os.path.join(work, "caps.ass"), "w", encoding="utf-8").write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- kamera
def camera_track(spec, beats, total):
    """Pre kazdy snimok (lat, lon, z, globe_R alebo None, globe_mix)."""
    keys = []
    prev = None
    for i, b in enumerate(beats):
        c = b["cam"]
        if i == 0:
            t_fly0 = GLOBE_T - 0.3
            keys.append(("fly", t_fly0, b["t0"] + min(5.0, max(3.2, (b["t1"] - b["t0"]) * 0.7)),
                         (c["lat"], c["lon"], GLOBE_ZEND), (c["lat"], c["lon"], c["z"])))
        else:
            mv = min(1.7, max(0.9, 0.4 * (b["t1"] - b["t0"]))) if abs(c["z"] - prev["z"]) > 0.5 else 1.0
            keys.append(("fly", b["t0"] - 0.15, b["t0"] - 0.15 + mv, (prev["lat"], prev["lon"], prev["z"]),
                         (c["lat"], c["lon"], c["z"])))
        prev = c
    frames = []
    n = int(math.ceil(total * FPS))
    for f in range(n):
        t = f / FPS
        cur = None
        for kind, a, bnd, p0, p1 in keys:
            if t >= a:
                u = ease((t - a) / max(0.05, bnd - a))
                # z: pri velkej zmene "skok von a dnu" by bol prehnany - staci plynuly log-zoom
                lat = p0[0] + (p1[0] - p0[0]) * u
                lon = p0[1] + (p1[1] - p0[1]) * u
                z = p0[2] + (p1[2] - p0[2]) * u
                drift = max(0.0, t - bnd) * 0.035          # pomaly dych kamery po dolete
                cur = (lat, lon, z + drift)
        if cur is None:
            cur = (beats[0]["cam"]["lat"], beats[0]["cam"]["lon"], GLOBE_ZEND)
        frames.append(cur)
    return frames


def globe_params(spec, t):
    tgt = spec["beats"][0]["cam"]
    u = ease(t / GLOBE_T)
    lat = 8 + (tgt["lat"] - 8) * u
    lon = tgt["lon"] + 75 * (1 - u)
    zc = GLOBE_ZEND
    rend = 256 * 2 ** zc / (2 * math.pi * math.cos(math.radians(tgt["lat"])))
    r0 = 360
    ui = min(1.0, t / GLOBE_T) ** 2.2                       # rast najprv pomaly, potom ponor
    return lat, lon, r0 * (rend / r0) ** ui


# ---------------------------------------------------------------- UI vrstvy
_fcache = {}
def font(sz):
    if sz not in _fcache:
        _fcache[sz] = ImageFont.truetype(FONT, sz)
    return _fcache[sz]


def paste_rgba(frame, rgba, x, y, alpha=1.0):
    h, w = rgba.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sub = rgba[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    a = sub[..., 3:4] / 255.0 * alpha
    frame[y0:y1, x0:x1] = frame[y0:y1, x0:x1] * (1 - a) + sub[..., 2::-1] * a


_sb = {}
def search_bar(text, cursor):
    k = (text, cursor)
    if k not in _sb:
        im = Image.new("RGBA", (960, 110), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((4, 8, 955, 104), 48, fill=(255, 255, 255, 240))
        d.ellipse((44, 34, 78, 68), outline=(90, 90, 90, 255), width=5)
        d.line((74, 64, 88, 78), fill=(90, 90, 90, 255), width=6)
        d.text((112, 56), text + ("|" if cursor else ""), font=font(44), fill=(30, 30, 30, 255), anchor="lm")
        _sb[k] = np.array(im)
    return _sb[k]


def text_rgba(txt, sz, fill=(255, 255, 255, 255), box=None, pad=18):
    f = font(sz)
    l, t, r, b = f.getbbox(txt)
    w, h = r - l + 2 * pad, b - t + 2 * pad
    im = Image.new("RGBA", (w + 8, h + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if box:
        d.rounded_rectangle((0, 0, w, h), 14, fill=box)
    else:
        d.text((pad - l + 3, pad - t + 3), txt, font=f, fill=(0, 0, 0, 170))
    d.text((pad - l, pad - t), txt, font=f, fill=fill)
    return np.array(im)


def screen_xy(lat, lon, cam):
    cx, cy = merc(cam[0], cam[1], cam[2]); px, py = merc(lat, lon, cam[2])
    return px - cx + W / 2, py - cy + H / 2


def draw_overlays(fr, t, cam, spec, beats, words):
    # citac kamery (vlavo dole) + atribucia
    alt = 45.0 * 2 ** (11.8 - cam[2])
    alts = f"{alt:,.0f} km" if alt >= 10 else f"{alt:.1f} km"
    paste_rgba(fr, text_rgba(f"{dms(cam[0], 'N', 'S')}  {dms(cam[1], 'E', 'W')}   ALT {alts}", 30,
                             fill=(255, 255, 255, 230)), 40, 1770)
    paste_rgba(fr, text_rgba("Imagery: Esri, Maxar, Earthstar Geographics", 22, fill=(255, 255, 255, 150)), 40, 1830)
    # vyhladavaci riadok: pise suradnice 0,15-1,4 s, drzi do konca 1. beatu
    b0 = beats[0]
    if t < b0["t1"] + 0.3:
        s = spec["coords"]
        k = int(len(s) * min(1.0, max(0.0, (t - 0.15) / 1.25)))
        a = 1.0 if t < b0["t1"] - 0.1 else max(0.0, 1 - (t - b0["t1"] + 0.1) / 0.4)
        paste_rgba(fr, search_bar(s[:k], (int(t * 2.2) % 2 == 0) or k < len(s)), 60, 130, a)
    for b in beats:
        if not (b["t0"] - 0.1 <= t < b["t1"] + 0.1):
            continue
        if "ruler" in b:
            r = b["ruler"]; ts = word_at(words, b, r.get("on"), 0.4)
            if t >= ts:
                u = ease((t - ts) / 0.6)
                half = r["km"] * 500 / m_per_px(r["lat"], cam[2])
                x, y = screen_xy(r["lat"], r["lon"], cam)
                xa, xb = x - half, x - half + 2 * half * u
                yl = y + 60
                cv2.line(fr, (int(xa), int(yl)), (int(xb), int(yl)), (255, 255, 255), 6, cv2.LINE_AA)
                for xx in (xa, xb):
                    cv2.line(fr, (int(xx), int(yl - 24)), (int(xx), int(yl + 24)), (255, 255, 255), 6, cv2.LINE_AA)
                if u > 0.6:
                    lab = text_rgba(r["label"], 64, fill=(255, 255, 255, 255), box=(0, 0, 0, 160))
                    paste_rgba(fr, lab, int(x - lab.shape[1] / 2), int(yl - 150), min(1, (u - 0.6) / 0.3))
        if "rings" in b:
            r = b["rings"]; ts = word_at(words, b, r.get("on"), 0.3)
            if t >= ts:
                x, y = screen_xy(r["lat"], r["lon"], cam)
                for i, km in enumerate(r["km"]):
                    u = ease((t - ts - i * 0.18) / 0.55)
                    if u <= 0:
                        continue
                    rad = km * 1000 / m_per_px(r["lat"], cam[2])
                    cv2.ellipse(fr, (int(x), int(y)), (int(rad), int(rad)), -90, 0, 360 * u, RED, 7, cv2.LINE_AA)
        if "tag" in b:
            r = b["tag"]; ts = word_at(words, b, r.get("on"), 0.5)
            if t >= ts:
                u = ease((t - ts) / 0.35)
                x, y = screen_xy(r["lat"], r["lon"], cam)
                cv2.circle(fr, (int(x), int(y)), int(16 * u) + 1, RED, -1, cv2.LINE_AA)
                cv2.circle(fr, (int(x), int(y)), int(16 * u) + 1, (255, 255, 255), 4, cv2.LINE_AA)
                cv2.line(fr, (int(x), int(y - 20)), (int(x), int(y - 20 - 150 * u)), (255, 255, 255), 4, cv2.LINE_AA)
                lab = text_rgba(r["label"], 66, fill=(255, 255, 255, 255), box=(214, 40, 40, 235))
                paste_rgba(fr, lab, int(x - lab.shape[1] / 2), int(y - 20 - 150 * u - lab.shape[0]), u)
        if "stamp" in b:
            r = b["stamp"]; ts = word_at(words, b, r.get("on"), 0.5)
            if ts <= t:
                u = ease((t - ts) / 0.3)
                lab = text_rgba(r["label"], 70, fill=(255, 255, 255, 255), box=(0, 0, 0, 170))
                paste_rgba(fr, lab, int(W / 2 - lab.shape[1] / 2), 330 - int(30 * (1 - u)), u)


# ---------------------------------------------------------------- Orbi (rozpravac) + foto karty
sys.path.insert(0, HERE)
import mascots

ORBI_H, ORBI_X, ORBI_BOTTOM = 330, 30, 1745
CYAN = (255, 240, 78)                                        # BGR
ORBI = {}                                                    # env, blinks, events, photos (naplni prep_orbi)


def prep_orbi(spec, beats, words, work):
    v, _ = sf.read(os.path.join(work, "voice.wav"))
    hop = SR // FPS
    n = len(v) // hop + 1
    env = np.array([np.sqrt(np.mean(v[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(v) else 0 for i in range(n)])
    env = np.clip(env / (np.percentile(env[env > 1e-4], 90) + 1e-9), 0, 1)
    sm = np.zeros_like(env)
    for i in range(1, n):                                    # rychly nabeh, pomalsi dobeh (ako usta)
        sm[i] = env[i] if env[i] > sm[i - 1] else sm[i - 1] * 0.55 + env[i] * 0.45
    ORBI["env"] = sm
    rng = np.random.default_rng(11); t, bl = 1.2, []
    while t < 400:
        bl.append(t); t += rng.uniform(2.4, 4.8)
    ORBI["blinks"] = bl
    ev = []                                                  # (t0, t1, druh, data)
    for b in beats:
        r = b.get("react")
        if r:
            t0 = word_at(words, b, r.get("on"), 0.3)
            ev.append((t0, t0 + r.get("dur", 1.1), "expr", r["expr"]))
        for k in ("ruler", "rings", "tag"):
            if k in b:
                t0 = word_at(words, b, b[k].get("on"), 0.4)
                ev.append((t0, t0 + 1.0, "point", (b[k]["lat"], b[k]["lon"])))
    ORBI["events"] = ev
    cards = []
    for b in beats:
        p = b.get("photo")
        if p:
            t0 = word_at(words, b, p.get("on"), 0.3)
            cards.append((t0, t0 + p.get("dur", 2.8), photo_card(os.path.join(HERE, p["file"]), p["label"], p["credit"])))
    ORBI["cards"] = cards


_sprites = {}
def orbi_sprite(mouth, blink, look, expr):
    k = (round(mouth * 4) / 4, round(blink * 3) / 3, round(look * 2) / 2, expr)
    if k not in _sprites:
        _sprites[k] = np.array(mascots.draw("orbi", *k[:3], h_out=ORBI_H, expr=expr).convert("RGBA"))
    return _sprites[k]


def photo_card(path, label, credit):
    im = Image.open(path).convert("RGB")
    cw, ch = 820, 600                                        # vyrez 41:30 zo stredu
    s = max(cw / im.width, ch / im.height)
    im = im.resize((int(im.width * s + 1), int(im.height * s + 1)), Image.LANCZOS)
    x0, y0 = (im.width - cw) // 2, (im.height - ch) // 2
    im = im.crop((x0, y0, x0 + cw, y0 + ch))
    bw = 18
    card = Image.new("RGBA", (cw + 2 * bw, ch + 2 * bw + 56), (255, 255, 255, 255))
    card.paste(im, (bw, bw))
    ImageDraw.Draw(card).text((bw, ch + bw + 12), credit, font=font(30), fill=(90, 90, 90, 255))
    sh = Image.new("RGBA", (card.width + 80, card.height + 80), (0, 0, 0, 0))
    sh.paste(Image.new("RGBA", card.size, (0, 0, 0, 150)), (40, 52))
    from PIL import ImageFilter
    sh = sh.filter(ImageFilter.GaussianBlur(18))
    sh.alpha_composite(card, (40, 40))
    sh = sh.rotate(-3, resample=Image.BICUBIC, expand=True)
    lab = Image.fromarray(text_rgba(label, 46, fill=(255, 255, 255, 255), box=(214, 40, 40, 245)))
    out = Image.new("RGBA", (sh.width, sh.height + lab.height - 30), (0, 0, 0, 0))
    out.alpha_composite(sh, (0, lab.height - 30))
    out.alpha_composite(lab, (70, 0))
    return np.array(out)


def draw_orbi(fr, t, cam):
    f = int(t * FPS)
    env = ORBI["env"]
    mouth = float(env[f]) if f < len(env) else 0.0
    blink = 0.0
    for b in ORBI["blinks"]:
        if b <= t < b + 0.16:
            blink = 1 - abs((t - b) / 0.08 - 1)
    expr, look, target = "normal", 0.25 * math.sin(t * 0.7), None
    for t0, t1, kind, data in ORBI["events"]:
        if t0 <= t < t1:
            if kind == "expr":
                expr = data
            else:
                target = data
    pop = ease((t - 0.35) / 0.35) if t < 0.7 else 1.0
    if pop <= 0:
        return
    if target:
        look = 1.0
    sp = orbi_sprite(mouth, blink, look, expr)
    bob = 7 * math.sin(t * 2.4)
    jump = 0.0
    for t0, t1, kind, data in ORBI["events"]:
        if kind == "expr" and t0 <= t < t0 + 0.35:
            jump = -38 * math.sin((t - t0) / 0.35 * math.pi)
    if pop < 1:                                              # vyskoci zdola s prekmitom
        sc = max(0.05, pop * (1 + 0.15 * math.sin(pop * math.pi)))
        sp = cv2.resize(sp, (max(2, int(sp.shape[1] * sc)), max(2, int(sp.shape[0] * sc))))
    x = ORBI_X + (ORBI_H * 1.12 - sp.shape[1]) / 2
    y = ORBI_BOTTOM - sp.shape[0] + bob + jump
    if target:                                               # luc z oci na miesto, o ktorom hovori
        tx, ty = screen_xy(target[0], target[1], cam)
        ox, oy = x + sp.shape[1] * 0.5, y + sp.shape[0] * 0.55
        tt0 = [e for e in ORBI["events"] if e[2] == "point" and e[0] <= t < e[1]][0][0]
        u = ease((t - tt0) / 0.35); fade = min(1.0, (tt0 + 1.0 - t) / 0.25)
        ex, ey = ox + (tx - ox) * u, oy + (ty - oy) * u
        lay = np.zeros_like(fr)
        cv2.line(lay, (int(ox), int(oy)), (int(ex), int(ey)), CYAN, 14, cv2.LINE_AA)
        lay = cv2.GaussianBlur(lay, (0, 0), 6) * 1.4
        cv2.line(lay, (int(ox), int(oy)), (int(ex), int(ey)), (255, 255, 255), 4, cv2.LINE_AA)
        if u >= 1:
            rr = int(20 + 70 * ((t - tt0 - 0.35) % 0.6) / 0.6)
            cv2.circle(lay, (int(tx), int(ty)), rr, CYAN, 6, cv2.LINE_AA)
        fr += lay * fade
    paste_rgba(fr, sp, int(x), int(y))


def draw_cards(fr, t):
    for t0, t1, card in ORBI["cards"]:
        if t0 <= t < t1:
            u_in = ease((t - t0) / 0.35); u_out = ease((t - (t1 - 0.3)) / 0.3)
            x = int((W - card.shape[1]) / 2 + (1 - u_in) * W - u_out * W)
            paste_rgba(fr, card, x, 240)


# ---------------------------------------------------------------- zvuk
def sfx_click(rng):
    n = int(0.012 * SR); s = rng.normal(0, 1, n) * np.exp(-np.linspace(0, 9, n))
    return np.convolve(s, [1, -0.85], "same") * 0.12


def sfx_whoosh(dur, rng):
    n = int(dur * SR); s = rng.normal(0, 1, n)
    out = np.zeros(n); y = 0.0
    env = np.sin(np.linspace(0, math.pi, n)) ** 1.6
    cut = 0.02 + 0.18 * env                         # jednopolovy dolny priepust, otvara sa v strede
    for i in range(n):
        y += cut[i] * (s[i] - y); out[i] = y
    return out / (np.abs(out).max() + 1e-9) * env * 0.16


def mix_audio(spec, voice, total, beats, work):
    rng = np.random.default_rng(5)
    n = int(total * SR)
    v = np.pad(voice.astype(np.float64), (0, max(0, n - len(voice))))[:n]
    v = v / (np.sqrt(np.mean(v[np.abs(v) > 0.01] ** 2)) + 1e-9) * 0.16
    fx = np.zeros(n)
    s = spec["coords"]
    for i in range(len(s)):
        t = 0.15 + 1.25 * i / len(s)
        c = sfx_click(rng) * rng.uniform(0.6, 1.0); a = int(t * SR); fx[a:a + len(c)] += c[:max(0, n - a)]
    def put(t, x):
        a = int(t * SR); fx[a:a + len(x)] += x[:max(0, n - a)]
    put(GLOBE_T - 1.0, sfx_whoosh(1.8, rng) * 1.2)
    prev = beats[0]["cam"]
    for b in beats[1:]:
        if abs(b["cam"]["z"] - prev["z"]) > 1.2:
            put(b["t0"] - 0.35, sfx_whoosh(1.2, rng))
        prev = b["cam"]
    msrc = os.path.join(ROOT, "assets", "music", spec.get("music", "cine_616.mp3"))
    subprocess.run([FF, "-y", "-i", msrc, "-t", str(total + 3), "-ar", str(SR), "-ac", "1", "m.wav"],
                   cwd=work, check=True, capture_output=True)
    m, _ = sf.read(os.path.join(work, "m.wav"))
    m = np.pad(m, (0, max(0, n - len(m))))[:n]
    m = m / (np.sqrt(np.mean(m ** 2)) + 1e-9) * 0.03
    fo = int(1.2 * SR); m[-fo:] *= np.linspace(1, 0, fo)
    mix = np.tanh((v + m + fx) * 1.5) / 1.5
    sf.write(os.path.join(work, "mix.wav"), mix.astype(np.float32), SR)
    # TikTok verzia bez hudby: hudbu a jej hlasitost vyberie v appke ten, kto nahrava (user 29.10.)
    dry = np.tanh((v + fx) * 1.5) / 1.5
    sf.write(os.path.join(work, "mix_tt.wav"), dry.astype(np.float32), SR)


# ---------------------------------------------------------------- render
def prefetch(spec, cams):
    need = set()
    n = 2 ** GLOBE_LEVEL
    need |= {(GLOBE_LEVEL, x, y) for x in range(n) for y in range(n)}
    for i, (lat, lon, z) in enumerate(cams):
        if i * 1.0 / FPS < GLOBE_T - 0.35:
            continue
        for L, _ in levels_for(z):
            tx0, ty0, tx1, ty1, *_ = level_window(lat, lon, z, L)
            for ty in range(max(0, ty0), min(2 ** L - 1, ty1) + 1):
                for tx in range(tx0, tx1 + 1):
                    need.add((L, tx % 2 ** L, ty))
    todo = [k for k in need if not os.path.exists(tile_path(*k))]
    print(f"   dlazdice: {len(need)} (nove {len(todo)})")
    with ThreadPoolExecutor(4) as ex:              # 8 vlakien -> Esri obcas odmietne (prazdne dlazdice)
        list(ex.map(fetch, todo))


def render(spec, beats, words, cams, total, work, out):
    cmd = [FF, "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", "mix.wav", "-vf", "subtitles=caps.ass:fontsdir=fonts", "-c:v", "libx264", "-preset", "medium",
           "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-shortest", "-movflags", "+faststart", out]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    elog = open(os.path.join(work, "ffmpeg.log"), "wb")
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=work, stderr=elog)
    yy, xx = _yy, _xx
    vig = np.clip(1.12 - (((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2) * 1.1, 0.55, 1)[..., None]
    for f, cam in enumerate(cams):
        t = f / FPS
        if t < GLOBE_T:
            g = render_globe(*globe_params(spec, t))
            mix = min(1.0, max(0.0, (t - (GLOBE_T - 0.3)) / 0.3))
            fr = g if mix <= 0 else g * (1 - mix) + render_flat(*cam) * mix
        else:
            fr = render_flat(*cam)
        fr = fr * vig
        ocam = cam if t >= GLOBE_T - 0.3 else (globe_params(spec, t)[0], globe_params(spec, t)[1],
                                               math.log2(2 * math.pi * globe_params(spec, t)[2] / 256))
        draw_overlays(fr, t, ocam, spec, beats, words)
        draw_cards(fr, t)
        draw_orbi(fr, t, ocam)
        if t < 0.12:
            fr *= t / 0.12 * 0.6 + 0.4
        p.stdin.write(np.clip(fr, 0, 255).astype(np.uint8).tobytes())
        if f % 150 == 0:
            print(f"   {f}/{len(cams)}")
    p.stdin.close(); p.wait(); elog.close()
    if p.returncode:
        sys.exit("ffmpeg zlyhal: " + open(os.path.join(work, "ffmpeg.log"), encoding="utf-8", errors="replace").read()[-1500:])


def main():
    spec_path = sys.argv[1]
    spec = json.load(open(spec_path, encoding="utf-8"))
    slug = os.path.splitext(os.path.basename(spec_path))[0]
    work = os.path.join(ROOT, "temp", "orbit_" + slug)
    os.makedirs(os.path.join(work, "fonts"), exist_ok=True)
    fdst = os.path.join(work, "fonts", "Poppins-SemiBold.ttf")
    if not os.path.exists(fdst):
        open(fdst, "wb").write(open(FONT, "rb").read())
    out = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "output", f"orbit_{slug}.mp4"))
    beats = spec["beats"]
    print("1) hlas"); voice, total = tts(spec, beats, work); total += 0.6; print(f"   {total:.1f} s")
    print("2) casy slov"); words = word_times(beats, work)
    keys = set()
    for b in beats:
        for k in ("ruler", "rings", "tag", "stamp"):
            if k in b and b[k].get("on"):
                keys.add(re.sub(r"[^a-z0-9]", "", b[k]["on"].lower()))
    build_ass(words, keys, work)
    prep_orbi(spec, beats, words, work)
    print("3) kamera + dlazdice"); cams = camera_track(spec, beats, total); prefetch(spec, cams)
    print("4) zvuk"); mix_audio(spec, voice, total, beats, work)
    print("5) render"); render(spec, beats, words, cams, total, work, out)
    out_tt = os.path.splitext(out)[0] + "_tiktok.mp4"          # rovnaky obraz, zvuk bez hudby
    subprocess.run([FF, "-y", "-i", out, "-i", "mix_tt.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", out_tt],
                   cwd=work, check=True, capture_output=True)
    print("hotovo:", out, "+", out_tt)


if __name__ == "__main__":
    main()

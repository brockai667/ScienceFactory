# -*- coding: utf-8 -*-
"""PRO strih: per-scena multi-cut montaze (strih kazdych ~1.5-1.8s) + animovane logaa
(Google hook, Gemini scena). Vystupy -> assets/shots/scene_*.mp4 (video-asset pre engine)."""
import math, os, subprocess
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

SCIENCE = os.path.dirname(os.path.abspath(__file__))
FFDIR = r"C:\Users\damia\AppData\Local\Programs\Python\Python314\Lib\site-packages\static_ffmpeg\bin\win32"
FF = os.path.join(FFDIR, "ffmpeg.exe")
FONT = os.path.join(SCIENCE, "assets", "fonts", "Poppins-SemiBold.ttf")
PEXELS = "ViaEGnA1Ox2eYFtl1bdrxAi6akVJlGAiQNptLkH99Id8WYeoSvR4l1bZ"
SH = os.path.join(SCIENCE, "assets", "shots")
TMP = os.path.join(SCIENCE, "temp", "scenes")
os.makedirs(SH, exist_ok=True); os.makedirs(TMP, exist_ok=True)


def fetch(q, out):
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": PEXELS},
                     params={"per_page": 15, "orientation": "portrait", "query": q}, timeout=30)
    best = None
    for v in r.json().get("videos", []):
        for f in v.get("video_files", []):
            h = f.get("height") or 0
            if h >= 720 and (best is None or h > best[0]):
                best = (h, f["link"])
    if best:
        open(out, "wb").write(requests.get(best[1], timeout=120).content); return True
    return False


def clip(q, dur, out, ss="1.0"):
    raw = os.path.join(TMP, "raw.mp4")
    if not fetch(q, raw):
        return False
    p = subprocess.run([FF, "-y", "-ss", ss, "-t", f"{dur}", "-i", raw,
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,"
                               "eq=contrast=1.06:saturation=1.12",
                        "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out],
                       capture_output=True, text=True)
    return os.path.exists(out)


def logo_clip(logo_png, bg_q, dur, out):
    bg = os.path.join(TMP, "lbg.mp4")
    if not fetch(bg_q, bg):
        return False
    fc = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=brightness=-0.32:saturation=1.15,setsar=1[bg];"
          "[1:v]scale=860:-1[lg];[1:v]scale=930:-1,gblur=sigma=26[gl];"
          "[bg][gl]overlay=(W-w)/2:(H-h)/2[b1];[b1][lg]overlay=(W-w)/2:(H-h)/2[ov];"
          "[ov]fade=t=in:st=0:d=0.4,zoompan=z='if(lte(on,28),1.28-0.28*on/28,1.0)':d=1:fps=30:s=1080x1920:"
          "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',format=yuv420p[v]")
    p = subprocess.run([FF, "-y", "-stream_loop", "-1", "-i", bg, "-i", logo_png, "-filter_complex", fc,
                        "-map", "[v]", "-t", f"{dur}", "-r", "30", "-an",
                        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out], capture_output=True, text=True)
    return os.path.exists(out)


def concat(parts, out):
    lst = os.path.join(TMP, "l.txt")
    open(lst, "w", encoding="utf-8").write("".join(f"file '{p.replace(os.sep, '/')}'\n" for p in parts))
    subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-preset", "veryfast",
                    "-pix_fmt", "yuv420p", out], capture_output=True, text=True)


# --- Google wordmark PNG (4 farby) ---
def google_word():
    out = os.path.join(TMP, "google_word.png")
    LET = [("G", "#4285F4"), ("o", "#EA4335"), ("o", "#FBBC05"), ("g", "#4285F4"), ("l", "#34A853"), ("e", "#EA4335")]
    f = ImageFont.truetype(FONT, 230); pad = 60
    ws = [f.getbbox(c)[2] - f.getbbox(c)[0] for c, _ in LET]
    img = Image.new("RGBA", (sum(ws) + 5 * (len(LET) - 1) + 2 * pad, 350), (0, 0, 0, 0))
    d = ImageDraw.Draw(img); x = pad
    for (c, col), w in zip(LET, ws):
        bb = f.getbbox(c); d.text((x - bb[0], pad - bb[1] + 20), c, font=f, fill=col); x += w + 5
    img.save(out); return out


# --- Gemini logo PNG (sparkle + text) ---
def gemini_logo():
    out = os.path.join(TMP, "gemini_logo.png")
    W, H = 1000, 460
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cx, cy, R, r = 190, 230, 165, 46
    pts = []
    for k in range(8):
        a = math.radians(k * 45 - 90); rad = R if k % 2 == 0 else r
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    yv = np.linspace(0, 1, H); c0 = np.array([70, 130, 246]); c1 = np.array([158, 92, 204])
    grad = Image.fromarray(np.repeat((c0[None, :] + (c1 - c0)[None, :] * yv[:, None])[:, None, :], W, axis=1).astype("uint8"))
    mask = Image.new("L", (W, H), 0); ImageDraw.Draw(mask).polygon(pts, fill=255)
    img.paste(grad, (0, 0), mask)
    f = ImageFont.truetype(FONT, 150); ImageDraw.Draw(img).text((400, 130), "Gemini", font=f, fill="white")
    img.save(out); return out


gw = google_word(); gl = gemini_logo()
D = 2.6   # dlzka klipu -> montaze > rozpravanie (ZIADNY loop) + cistejsi 1 strih (nie chaos)


def scene(parts_spec, out):
    p = []
    for kind, arg in parts_spec:
        o = os.path.join(TMP, f"{os.path.basename(out)}_{len(p)}.mp4")
        ok = logo_clip(arg[0], arg[1], D, o) if kind == "logo" else clip(arg, D, o)
        if ok:
            p.append(o)
    concat(p, out)
    print(os.path.basename(out), "ok")


# scena 0: Google logo -> tech (suredne, nie chaos)
scene([("logo", (gw, "futuristic digital technology blue")), ("clip", "modern technology innovation"),
       ("clip", "futuristic city technology")], os.path.join(SH, "scene_hook.mp4"))

# scena 1: Gemini logo -> AI zabery
scene([("logo", (gl, "abstract purple technology background")), ("clip", "artificial intelligence visualization glow"),
       ("clip", "futuristic robot assistant")], os.path.join(SH, "scene_gemini.mp4"))

# scena 2: 1M tokens / zero cost
scene([("clip", "digital data network fast"), ("clip", "counting money cash hands"),
       ("clip", "technology speed motion")], os.path.join(SH, "scene_tokens.mp4"))

# scena CTA: phone / social
scene([("clip", "person using phone social media"), ("clip", "scrolling smartphone screen"),
       ("clip", "happy person using phone")], os.path.join(SH, "scene_cta.mp4"))
print("DONE scenes")

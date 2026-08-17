# -*- coding: utf-8 -*-
"""Cool futuristicke animovane Google logo na hook: wordmark (4 Google farby) na tech pozadi
+ glow + reveal (fade + zoom). Vystup: assets/shots/google_intro.mp4 (1080x1920)."""
import os, subprocess
import requests
from PIL import Image, ImageDraw, ImageFont

SCIENCE = os.path.dirname(os.path.abspath(__file__))
FFDIR = r"C:\Users\damia\AppData\Local\Programs\Python\Python314\Lib\site-packages\static_ffmpeg\bin\win32"
FF = os.path.join(FFDIR, "ffmpeg.exe")
FONT = os.path.join(SCIENCE, "assets", "fonts", "Poppins-SemiBold.ttf")
PEXELS = "ViaEGnA1Ox2eYFtl1bdrxAi6akVJlGAiQNptLkH99Id8WYeoSvR4l1bZ"
TMP = os.path.join(SCIENCE, "temp")
os.makedirs(TMP, exist_ok=True)
WORD = os.path.join(TMP, "google_word.png")
BG = os.path.join(TMP, "techbg.mp4")
OUT = os.path.join(SCIENCE, "assets", "shots", "google_intro.mp4")

# 1) Google wordmark (per-letter farby) -> transparentne PNG
LETTERS = [("G", "#4285F4"), ("o", "#EA4335"), ("o", "#FBBC05"), ("g", "#4285F4"), ("l", "#34A853"), ("e", "#EA4335")]
fs = 230
font = ImageFont.truetype(FONT, fs)
pad = 60
# zmeraj sirky
widths = [font.getbbox(ch)[2] - font.getbbox(ch)[0] for ch, _ in LETTERS]
gap = 6
total_w = sum(widths) + gap * (len(LETTERS) - 1)
asc = font.getbbox("G")[3]
img = Image.new("RGBA", (total_w + 2 * pad, fs + 2 * pad), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
x = pad
for (ch, col), w in zip(LETTERS, widths):
    bb = font.getbbox(ch)
    d.text((x - bb[0], pad - bb[1] + 20), ch, font=font, fill=col)
    x += w + gap
img.save(WORD)
print("wordmark:", img.size)

# 2) futuristicke tech pozadie z Pexelsu
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

for q in ["futuristic digital technology particles", "abstract blue technology background", "digital network motion"]:
    if fetch(q, BG):
        print("techbg:", q); break

# 3) komposit: bg (tmavsie) + glow + wordmark + fade/zoom reveal
fc = (
    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=brightness=-0.30:saturation=1.15,setsar=1[bg];"
    "[1:v]scale=860:-1[lg];"
    "[1:v]scale=920:-1,gblur=sigma=26[gl];"
    "[bg][gl]overlay=(W-w)/2:(H-h)/2[b1];"
    "[b1][lg]overlay=(W-w)/2:(H-h)/2[ov];"
    "[ov]fade=t=in:st=0:d=0.45,"
    "zoompan=z='if(lte(on,30),1.30-0.30*on/30,1.0)':d=1:fps=30:s=1080x1920:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',"
    "format=yuv420p[v]")
subprocess.run([FF, "-y", "-stream_loop", "-1", "-i", BG, "-i", WORD, "-filter_complex", fc,
                "-map", "[v]", "-t", "4", "-r", "30", "-an",
                "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", OUT],
               capture_output=True, text=True)
print("DONE:", OUT, f"({os.path.getsize(OUT)/1e6:.1f} MB)" if os.path.exists(OUT) else "FAIL")

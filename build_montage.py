# -*- coding: utf-8 -*-
"""Micro-zostrih pre multimodalnu scenu: text -> foto -> zvuk -> video (~1s kazdy), cover 1080x1920."""
import os, subprocess
import requests

SCIENCE = os.path.dirname(os.path.abspath(__file__))
FFDIR = r"C:\Users\damia\AppData\Local\Programs\Python\Python314\Lib\site-packages\static_ffmpeg\bin\win32"
FF = os.path.join(FFDIR, "ffmpeg.exe")
PEXELS = "ViaEGnA1Ox2eYFtl1bdrxAi6akVJlGAiQNptLkH99Id8WYeoSvR4l1bZ"
TMP = os.path.join(SCIENCE, "temp", "mm")
os.makedirs(TMP, exist_ok=True)
OUT = os.path.join(SCIENCE, "assets", "shots", "multimodal.mp4")

CLIPS = [
    ("text", "typing keyboard closeup text"),
    ("image", "photographer browsing photos gallery"),
    ("audio", "sound wave music equalizer"),
    ("video", "video editing timeline screen"),
]


def fetch(query, out):
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": PEXELS},
                     params={"per_page": 15, "orientation": "portrait", "query": query}, timeout=30)
    r.raise_for_status()
    best = None
    for v in r.json().get("videos", []):
        for f in v.get("video_files", []):
            h = f.get("height") or 0
            if h >= 720 and (best is None or h > best[0]):
                best = (h, f["link"])
    if not best:
        return False
    open(out, "wb").write(requests.get(best[1], timeout=120).content)
    return True


parts = []
for name, q in CLIPS:
    raw = os.path.join(TMP, f"{name}_raw.mp4")
    if not fetch(q, raw):
        print("fetch FAIL:", q); continue
    seg = os.path.join(TMP, f"{name}.mp4")
    # zober ~1s zo stredu, cover 1080x1920
    subprocess.run([FF, "-y", "-ss", "1", "-t", "1.0", "-i", raw,
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                    "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", seg],
                   capture_output=True, text=True)
    if os.path.exists(seg):
        parts.append(seg); print(f"  {name}: OK ({q})")

lst = os.path.join(TMP, "list.txt")
open(lst, "w", encoding="utf-8").write("".join(f"file '{p.replace(os.sep, '/')}'\n" for p in parts))
subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-preset", "veryfast",
                "-pix_fmt", "yuv420p", OUT], capture_output=True, text=True)
print("DONE:", OUT, f"({os.path.getsize(OUT)/1e6:.1f} MB, {len(parts)} klipov)")

# -*- coding: utf-8 -*-
"""Pro animovane titulky: vyrenderuje engine vizual BEZ titulkov, potom navrch da
animovane pop titulky (slova vyskakuju, kluc. slova zltou, hruby obrys) - reel-pro styl."""
import os, re, subprocess, sys

SCIENCE = os.path.dirname(os.path.abspath(__file__))
FFDIR = r"C:\Users\damia\AppData\Local\Programs\Python\Python314\Lib\site-packages\static_ffmpeg\bin\win32"
FF, FP = os.path.join(FFDIR, "ffmpeg.exe"), os.path.join(FFDIR, "ffprobe.exe")
FONTDIR = os.path.join(SCIENCE, "assets", "fonts")
SPEC = "scripts/auto_google_free_tokens.json"
SLUG = "google_just_gave_developers_1_000_000_free_tokens"
OUT = os.path.join(SCIENCE, "output", SLUG + ".mp4")
FINAL = os.path.join(SCIENCE, "output", SLUG + "_PRO.mp4")

# 1) vizual bez titulkov
print("== render vizual (bez titulkov) ==")
r = subprocess.run([sys.executable, "make_video.py", SPEC, "--no-captions"], cwd=SCIENCE,
                   capture_output=True, text=True)
if not os.path.exists(OUT):
    print("render FAIL:\n", (r.stderr or r.stdout)[-1500:]); sys.exit(1)

# 2) audio -> whisper word timing
wav = os.path.join(SCIENCE, "temp", "pro_audio.wav")
os.makedirs(os.path.dirname(wav), exist_ok=True)
subprocess.run([FF, "-y", "-i", OUT, "-ar", "16000", "-ac", "1", wav], capture_output=True, text=True)
from faster_whisper import WhisperModel
m = WhisperModel("base.en", device="cpu", compute_type="int8")
wsegs, _ = m.transcribe(wav, word_timestamps=True)
NUM = {"0": "ZERO", "1": "ONE", "2": "TWO", "3": "THREE", "4": "FOUR", "5": "FIVE", "6": "SIX", "7": "SEVEN", "8": "EIGHT", "9": "NINE"}
EMPH = {"FREE", "MILLION", "ZERO", "BIGGEST", "EVERY", "MINUTE", "GEMINI", "GOOGLE", "AI", "KEY", "NOW", "FOLLOW", "DAILY"}
words = []
for s in wsegs:
    for w in (s.words or []):
        raw = re.sub(r"[^A-Za-z0-9'$.%-]", "", w.word).strip()
        up = NUM.get(raw.upper(), raw.upper())
        if up == "TOO":            # whisper pocuje cislo 2 ("two") ako "too" -> oprav na cislo
            up = "TWO"
        if up:
            emph = bool(re.search(r"\d", up)) or up in EMPH or "$" in up
            words.append((w.start, w.end, up, emph))
print("slov:", len(words))


def ts(t):
    return f"{int(t//3600)}:{int((t%3600)//60):02d}:{t%60:05.2f}"


# 3) PRO animovany ASS (pop-scale + farba na klucovych + hruby obrys/tien)
header = (
    "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
    "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
    "MarginL, MarginR, MarginV, Encoding\n"
    "Style: P,Poppins SemiBold,118,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,10,6,2,80,80,560,1\n\n"
    "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
ev = []
for (a, b, txt, emph) in words:
    b = max(b, a + 0.22)
    col = "00C2F2" if emph else "FFFFFF"   # zlta na klucove, inak biela (ASS BGR)
    tag = ("{\\fad(28,28)\\fscx48\\fscy48"
           "\\t(0,90,\\fscx112\\fscy112)\\t(90,150,\\fscx100\\fscy100)"
           "\\1c&H" + col + "&}")
    ev.append(f"Dialogue: 0,{ts(a)},{ts(b)},P,,0,0,0,,{tag}{txt}")
ass = os.path.join(SCIENCE, "temp", "pro_words.ass")
open(ass, "w", encoding="utf-8").write(header + "\n".join(ev) + "\n")

ass_e = ass.replace("\\", "/").replace(":", "\\:")
fd_e = FONTDIR.replace("\\", "/").replace(":", "\\:")
print("== burn pro titulky ==")
p = subprocess.run([FF, "-y", "-i", OUT, "-vf", f"subtitles='{ass_e}':fontsdir='{fd_e}'",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", FINAL], capture_output=True, text=True)
if p.returncode != 0 or not os.path.exists(FINAL):
    print("burn FAIL:\n", p.stderr[-1800:]); sys.exit(1)
print(f"\nDONE: {FINAL} ({os.path.getsize(FINAL)/1e6:.1f} MB) | pro animovane titulky")

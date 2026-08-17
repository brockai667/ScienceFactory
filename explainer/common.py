#!/usr/bin/env python3
"""Spolocne veci pre explainer pipeline (tyzdenne dlhe video + reels-kapitoly).

Cesty, config, LLM volanie (Groq cez MODELS_* env, rovnako ako ostatne fabriky),
robustne parsovanie JSON-u z odpovede.
"""
import json
import os
import re
import sys
import time

import requests

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(EXP_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SCRIPTS_DIR = os.path.join(EXP_DIR, "scripts")
BANK = os.path.join(EXP_DIR, "explainer_bank.json")
STATE = os.path.join(EXP_DIR, "explainer_used.json")
OUT_ROOT = os.path.join(ROOT, "output", "explainer")
CACHE_DIR = os.path.join(ROOT, "temp", "explainer_cache")
FONT_DIR = os.path.join(ROOT, "assets", "fonts")

MODEL = os.environ.get("MODELS_MODEL", "openai/gpt-oss-120b")
MODEL_FALLBACK = os.environ.get("MODELS_FALLBACK", "openai/gpt-oss-20b")
BASE = os.environ.get("MODELS_BASE_URL", "https://api.groq.com/openai/v1")
TOKEN = os.environ.get("MODELS_TOKEN") or os.environ.get("GROQ_API_KEY") or os.environ.get("GITHUB_TOKEN")

# defaulty explainer sekcie configu (config.json -> "explainer": {...} ich prekryje)
DEFAULTS = {
    "kokoro_voice": "am_michael",
    "kokoro_speed": 1.0,
    "fps": 30,
    "long_w": 1920, "long_h": 1080,
    "reel_w": 1080, "reel_h": 1920,
    "chapters_min": 6, "chapters_max": 8,
    "beats_per_chapter": 15,
    "series_tag": "Explained",
    "yt_publish_hour": 17,          # Europe/Bratislava, pondelok
    "reel_slot_hour": 18,           # denny cas reelu (Bratislava)
    "reels_start_offset_days": 0,   # 0 = prvy reel v den publikovania dlheho videa
    "music": "",                    # cesta k mp3 (prazdne = bez hudby)
    "music_volume": 0.06,
    # Flux kresli produktove foto ovela spolahlivejsie nez "ilustraciu"; referencia pouziva realne fotky
    "image_style": ("isolated single object, clean studio product photograph on a plain white background, "
                    "soft shadow, centered, sharp focus, realistic, no text, no letters, no logos, "
                    "no watermark, no people, no hands"),
    "cta_footer": "Full video on YouTube: link in bio",   # bez sipky - Comic Neue nema glyf
    "channel_url": "",              # URL YT kanala (do popisu); prazdne = len link na konkretne video
}


def load_cfg():
    import appconfig
    cfg = appconfig.load()
    exp = dict(DEFAULTS)
    exp.update(cfg.get("explainer", {}) or {})
    cfg["explainer"] = exp
    return cfg


def slug(t):
    return re.sub(r"[^a-z0-9]+", "_", str(t).lower()).strip("_")[:60] or "video"


def ensure_dirs():
    for d in (SCRIPTS_DIR, OUT_ROOT, CACHE_DIR):
        os.makedirs(d, exist_ok=True)


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- LLM
def _extract_json(txt):
    txt = txt.strip()
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt, flags=re.S)
    try:
        return json.loads(txt)
    except Exception:
        pass
    # najdi prvy { ... } alebo [ ... ] blok
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = txt.find(opener), txt.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(txt[i:j + 1])
            except Exception:
                continue
    raise ValueError("LLM nevratil validny JSON: " + txt[:200])


def llm_json(prompt, system, temperature=0.7, max_tokens=6000, tries=3):
    """Zavolaj chat model, vrat parsovany JSON. Skusa hlavny model, potom fallback."""
    if not TOKEN:
        raise RuntimeError("Chyba MODELS_TOKEN (Groq) v prostredi.")
    last = None
    for model in (MODEL, MODEL_FALLBACK):
        for att in range(tries):
            try:
                r = requests.post(
                    BASE.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                    json={"model": model, "temperature": temperature, "max_tokens": max_tokens,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}]},
                    timeout=180)
                if r.status_code == 429:
                    wait = 20 + 20 * att
                    print(f"   [llm] 429 rate limit ({model}) - cakam {wait}s")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                txt = r.json()["choices"][0]["message"]["content"]
                return _extract_json(txt)
            except Exception as e:
                last = e
                print(f"   [llm] {model} pokus {att + 1}/{tries}: {str(e)[:120]}")
                time.sleep(3 + 4 * att)
    raise RuntimeError(f"LLM zlyhalo: {last}")


def hms(sec):
    sec = int(round(sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

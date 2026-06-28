#!/usr/bin/env python3
"""Doplni banku tem cez GitHub Models (zadarmo). Nika: VEDA & TECHNOLOGIE (fascinujuce fakty, ako veci funguju)."""
import json
import os
import re
import sys

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(ROOT, "topics_bank.json")
STATE = os.path.join(ROOT, "used_topics.json")

TARGET = int(os.environ.get("TOPICS_TARGET", "15"))
MODEL = os.environ.get("MODELS_MODEL", "openai/gpt-4o-mini")
BASE = os.environ.get("MODELS_BASE_URL", "https://models.github.ai/inference")
TOKEN = os.environ.get("MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN")

SYSTEM = ("You are a viral short-form scriptwriter for a SCIENCE & TECHNOLOGY brand called Curio. You explain "
          "fascinating, true science and tech: how everyday things actually work, space, physics, the human "
          "body & brain, inventions, AI and future technology, and mind-blowing 'did you know' facts. Every "
          "claim must be ACCURATE and widely accepted. NO invented statistics, NO pseudoscience, NO conspiracy, "
          "NO sensational misinformation. Awe-inspiring but honest. You output strict JSON, nothing else.")

EXAMPLE = {
    "title": "Why Your Brain Tricks You Every Day",
    "segments": [
        {"text": "Your brain edits reality before you ever see it.", "keywords": "brain neurons animation"},
        {"text": "And it does it about half a second early.", "keywords": "clock ticking macro"},
        {"text": "Your eyes only send raw light, your brain predicts the rest.", "keywords": "human eye macro"},
        {"text": "That's exactly why optical illusions fool everyone.", "keywords": "optical illusion pattern"},
        {"text": "You never see the world, only your brain's best guess of it.", "keywords": "person thinking dark"},
        {"text": "So reality is basically a controlled hallucination.", "keywords": "abstract neon lights"},
        {"text": "Follow Curio for your daily dose of science.", "keywords": "galaxy stars space"},
    ],
    "description": "You don't see reality, you see your brain's prediction of it. Follow for daily science & tech! 🧠",
    "hashtags": ["#science", "#brain", "#psychology", "#didyouknow", "#facts", "#tech", "#shorts", "#fyp"],
}


def build_prompt(n, existing_titles):
    return (
        f"Generate {n} NEW faceless short-form video topics for a SCIENCE & TECHNOLOGY brand called Curio "
        "(TikTok / Reels / YouTube Shorts).\n"
        "Niche: fascinating TRUE facts about how things work, space, physics, the human body & brain, "
        "inventions, AI and future tech, and surprising 'did you know' science.\n"
        "Return ONLY a JSON array (no markdown). Each item EXACTLY this schema:\n"
        f"{json.dumps(EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Rules (make it feel PRO and VIRAL):\n"
        "- title: a curiosity gap, like 'Why Space Is Completely Silent' or 'Your Phone Beats NASA's Moon Computer'.\n"
        "- 6 to 9 segments. Segment 1 is THE HOOK: one surprising, true claim under 12 words. "
        "Never start with 'Did you know'.\n"
        "- segment 2 deepens the curiosity (e.g. 'And the reason is stranger than you think.').\n"
        "- EVERYTHING must be scientifically accurate and mainstream. NO made-up numbers, NO pseudoscience, "
        "NO conspiracy, NO health/medical advice. If you cite a number, it must be a real, well-known one.\n"
        "- write for a clear, confident SPOKEN voiceover: short, simple, punchy sentences that build wonder.\n"
        "- each segment 'keywords': 1-3 ENGLISH words for real Pexels footage that VISUALLY MATCHES the line "
        "(e.g. 'galaxy stars space', 'circuit board macro', 'lightning storm night', 'human brain scan'). "
        "Concrete and visual, never abstract.\n"
        "- the SECOND-TO-LAST segment should loop back to the opening hook so a rewatch feels seamless.\n"
        "- the LAST segment text MUST be exactly: 'Follow Curio for your daily dose of science.'\n"
        "- description: one intriguing sentence ending with 'Follow for daily science & tech!'.\n"
        "- About half the time, add ONE fitting emoji at the very END of the description (e.g. 🔬, 🧠, 🚀, ⚡, 🌌). "
        "Emoji ONLY in the description text, NEVER inside any segment 'text' (spoken captions).\n"
        "- hashtags: 6-8 tags including #science #tech #shorts #fyp.\n"
        f"- Do NOT reuse any of these existing titles: {existing_titles}\n"
        "Return ONLY the JSON array."
    )


def call_model(user_text):
    r = requests.post(
        BASE.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json={"model": MODEL, "temperature": 0.95,
              "messages": [{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": user_text}]},
        timeout=180,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Models API {r.status_code}: {r.text[:500]}")
    return r.json()["choices"][0]["message"]["content"]


def extract_json(s):
    s = s.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    a, b = s.find("["), s.rfind("]")
    if a != -1 and b != -1:
        s = s[a:b + 1]
    return json.loads(s)


def valid(t):
    if not isinstance(t, dict) or "title" not in t or "segments" not in t:
        return False
    if not isinstance(t["segments"], list) or len(t["segments"]) < 4:
        return False
    for seg in t["segments"]:
        if "text" not in seg or "keywords" not in seg:
            return False
    t.setdefault("description", t["title"] + " Follow for daily science & tech!")
    t.setdefault("hashtags", ["#science", "#tech", "#shorts", "#fyp"])
    return True


def main():
    if not TOKEN:
        print("CHYBA: chyba MODELS_TOKEN/GITHUB_TOKEN"); sys.exit(1)
    bank = json.load(open(BANK, encoding="utf-8"))
    used = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else []
    titles = {t["title"] for t in bank}
    unused = [t for t in bank if t["title"] not in used]
    need = TARGET - len(unused)
    if need <= 0:
        print(f"Banka OK: {len(unused)} nepouzitych tem."); return
    print(f"Generujem ~{need} novych tem cez {MODEL}...")
    items = extract_json(call_model(build_prompt(need + 3, sorted(titles))))
    added = 0
    for t in items:
        if not valid(t) or t["title"] in titles:
            continue
        bank.append(t); titles.add(t["title"]); added += 1
    json.dump(bank, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Pridanych {added} tem. Banka ma {len(bank)} tem.")


if __name__ == "__main__":
    main()

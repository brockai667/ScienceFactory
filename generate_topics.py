#!/usr/bin/env python3
"""Doplni banku tem cez GitHub Models (zadarmo). Nika: VEDA & TECHNOLOGIE (fascinujuce fakty, ako veci funguju)."""
import json
import os
import re
import sys

import requests
try:
    import trends                      # trend scanner (Reddit + YouTube), volitelny
except Exception:
    trends = None

ROOT = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(ROOT, "topics_bank.json")
STATE = os.path.join(ROOT, "used_topics.json")

TARGET = int(os.environ.get("TOPICS_TARGET", "15"))
MODEL = os.environ.get("MODELS_MODEL", "openai/gpt-4o-mini")
BASE = os.environ.get("MODELS_BASE_URL", "https://models.github.ai/inference")
TOKEN = os.environ.get("MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN")

# Nika: VEDA & TECH -> kde ludia realne diskutuju / co pozeraju
TREND_SUBREDDITS = ['space', 'science', 'askscience', 'Physics', 'spaceporn']
TREND_YT_QUERIES = ['mind blowing science facts', 'space facts', 'how the universe works']

SYSTEM = ("You are a viral short-form scriptwriter for a SCIENCE & TECHNOLOGY brand called Curio. You explain "
          "fascinating, true science and tech: how everyday things actually work, space, physics, the human "
          "body & brain, inventions, AI and future technology, and mind-blowing 'did you know' facts. Every "
          "claim must be ACCURATE and widely accepted. NO invented statistics, NO pseudoscience, NO conspiracy, "
          "NO sensational misinformation. Awe-inspiring but honest. You output strict JSON, nothing else. THE HOOK (the very first line / segment 1) is the single most important thing in the whole video: it MUST stop the scroll within 2 seconds. Make it concrete and specific (a number, a name, a vivid image, or a sharp contradiction) and open a curiosity gap that can ONLY be closed by watching to the end. Lead with the most shocking part FIRST, never a slow setup. Forbidden hook openers: 'Did you know', 'Have you ever', 'Imagine', 'Here are', 'In this video', 'Let me tell you'.")

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


import random  # CTAS_ROTATE

CTAS = [
    "Follow for a new science fact every day.",
    "Follow if curiosity runs your brain.",
    "Follow for the science they never taught you.",
    "Follow to feed your curious mind daily.",
    "Follow for daily science that blows your mind.",
]


def build_prompt(n, existing_titles, trending=None):
    trend_block = ""
    if trending:
        joined = chr(10).join("- " + t for t in trending)
        trend_block = (
            " WHAT REAL PEOPLE DISCUSS AND WATCH THIS WEEK (live headlines from Reddit communities and "
            "top YouTube videos in this niche - what the audience actually cares about right now): " + joined +
            " Let at least HALF of the new topics be directly inspired by a SPECIFIC item above, turned "
            "into a strong hook that STILL follows the style and safety rules described. Do NOT copy any "
            "headline word-for-word, and NEVER mention Reddit or YouTube. "
        )
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
        "- VARY THE TITLE FORMAT: do NOT start more than one in five titles with a number "
        "(avoid the repetitive 'N things' pattern). Mix a bold claim, a question, a "
        "'why/how' angle and a curiosity gap so titles never look the same.\n"
        "- ACCURACY IS CRITICAL: use ONLY widely-documented, verifiable facts. NEVER invent or "
        "guess numbers, percentages, dates, amounts or statistics. If a specific figure is not "
        "universally established, say it generally instead of making one up. Wrong facts kill the "
        "channel's credibility, so double-check every claim.\n"
        "- BE SPECIFIC: name the ACTUAL subject of the video (the exact place, case, event, person "
        "or thing) so it is never vague. Viewers complain when the location or subject is not named.\n"
        f"- Do NOT reuse any of these existing titles: {existing_titles}\n"
        "- Do NOT repeat the same SUBJECT, fact or concept as any existing title above, even reworded, "
        "renumbered or from a different angle. Every topic must be a genuinely DIFFERENT idea.\n"
        + trend_block +
        "STORYBOARD (visual directing, IMPORTANT): to EVERY segment ADD a field 'visual' = an object choosing HOW to visualize exactly what that line SAYS (never generic): {\"type\":\"kenburns\",\"prompt\":\"LITERAL ENGLISH image prompt naming ONE concrete, instantly recognizable subject/scene that depicts exactly what the line says (a real thing a camera could photograph; NEVER abstract, NEVER metaphors)\"} for normal lines; {\"type\":\"counter\",\"target\":1000,\"suffix\":\"x\",\"label\":\"3-4 WORD CAPTION\"} when the line contains a big number; {\"type\":\"compare\",\"small_prompt\":\"...\",\"big_prompt\":\"...\",\"small_label\":\"X\",\"big_label\":\"Y\",\"stat\":\"300x\"} for size/amount comparisons; {\"type\":\"callouts\",\"prompt\":\"subject image\",\"labels\":[\"SHORT LABEL\"]} to point at parts of a subject; {\"type\":\"lineup\",\"items\":[{\"name\":\"A\",\"prompt\":\"...\"}]} for listing 3-5 things; {\"type\":\"arrow\",\"from_prompt\":\"...\",\"to_prompt\":\"...\",\"label\":\"WHAT MOVES\"} for movement/flow. First segment gets {\"type\":\"hook\",\"prompt\":\"dramatic scene image\",\"big\":\"SHORT PUNCHY QUESTION OR CLAIM (max 5 words)\"}; last segment {\"type\":\"cta\",\"prompt\":\"iconic subject of the video\"}. Labels MUST describe what the narration says at that moment - never invent unrelated text. Image prompts must describe 3D RENDERED CGI assets in a modern 3D-explainer style - NEVER photographs, NEVER photorealistic people; if a person is needed, describe an elegant dark silhouette with dramatic rim light, or the relevant anatomy/object instead - NEVER cartoon characters, NEVER toys; prefer objects, anatomy, environments, close-up details; the subject must FILL the frame and be well lit. Return ONLY the JSON array."
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


_STOP = {"why", "your", "the", "is", "a", "of", "you", "that", "are", "and", "to", "in",
         "on", "how", "this", "for", "with", "it", "its", "can", "cant", "not", "be", "do",
         "than", "them", "their", "own", "what", "when", "was", "were", "has", "have", "from",
         "more", "most", "just", "every", "an", "as", "or", "but", "so", "hidden", "secret",
         "surprising", "truth", "facts", "fact", "these", "there", "they"}


def _sig(title):
    return set(w for w in re.findall(r"[a-z]+", str(title).lower()) if len(w) > 2 and w not in _STOP)


def _too_similar(sig, existing_sigs):
    if not sig:
        return False
    for es in existing_sigs:
        if not es:
            continue
        inter = len(sig & es)
        if inter >= 3:
            return True
        if inter >= 2 and inter / (len(sig | es) or 1) >= 0.5:
            return True
    return False



# --- ANTI-OPAKOVANIE (dedup): po behu odstrani z banky NEPOUZITE temy, ktore su subjektom
# prilis podobne inej teme. Signatura = title+description+hook + cisla/roky; caste niche-slova
# sa auto-ignoruju cez frekvenciu (df). Duale pravidlo: rovnaky ROK + prekrytie = dup;
# rozne roky = rozne pripady; bezrocnove niky -> silna slovna zhoda. Publikovane sa NIKDY nemazu.
_DD_STOP = set("""a an the this that these those and or but so of to in on for with at by from as is are was
were be been being it its you your they them their our we he she his her my me i do does did not no can cant
will just every most more than then there here what when why how who which while into over out up down off only
also very much many some any all if thing things way ways get make made youre follow daily wisdom mindset day
today need needs about like want wants nobody tells tell told never ever still story people world reveal
revealed discover""".split())


def _dd_sig(t):
    txt = (str(t.get("title", "")) + " " + str(t.get("description", "")) + " "
           + (t.get("segments", [{}])[0].get("text", "") if t.get("segments") else ""))
    low = txt.lower()
    toks = set(w for w in re.findall(r"[a-z]+", low) if len(w) > 2 and w not in _DD_STOP)
    toks |= set("#" + n for n in re.findall(r"\d{2,}", low))
    return toks


def _dd_years(s):
    return set(w for w in s if len(w) == 5 and w[0] == "#" and w[1] in "12")


def _dd_dup(si, sj):
    common = si & sj
    if len(common) < 3:
        return False
    yi, yj = _dd_years(si), _dd_years(sj)
    yc = yi & yj
    if yi and yj and not yc:
        return False                                   # rozne roky = rozne pripady
    jac = len(common) / (len(si | sj) or 1)
    if yc and len(common) >= 3:
        return True                                    # spolocny rok + prekrytie
    if not (yi or yj) and len(common) >= 4 and jac >= 0.5:
        return True                                    # bezrocnove niky -> silna slovna zhoda
    return False


def _clean_bank():
    """Odstrani NEPOUZITE temy prilis podobne inej teme (ziadne opakovanie videi).
    Publikovane (used_topics) sa nikdy nemazu. Best-effort, nikdy nezhodi denny beh."""
    from collections import Counter
    bank = json.load(open(BANK, encoding="utf-8"))
    used = set(json.load(open(STATE, encoding="utf-8"))) if os.path.exists(STATE) else set()
    raws = [_dd_sig(t) for t in bank]
    df = Counter()
    for s in raws:
        for w in s:
            df[w] += 1
    cutoff = max(2, int(len(bank) * 0.25))             # slovo vo >25% tem = niche-filler -> ignoruj
    sigs = [set(w for w in s if df[w] <= cutoff) for s in raws]
    ks = [s for t, s in zip(bank, sigs) if t.get("title") in used]   # seed: vsetky publikovane
    kept, removed = [], 0
    for t, s in zip(bank, sigs):
        if t.get("title") in used:
            kept.append(t)
            continue
        if s and any(_dd_dup(s, k) for k in ks):
            removed += 1
            continue
        kept.append(t)
        ks.append(s)
    if removed:
        json.dump(kept, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("Dedup: odstranenych %d podobnych nepouzitych tem (ziadne opakovanie)." % removed)
    else:
        print("Dedup: ziadne podobne nepouzite temy.")



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
    trending = []
    if trends is not None:
        try:
            trending, meta = trends.gather(TREND_SUBREDDITS, TREND_YT_QUERIES, top=18, return_meta=True)
            if trending:
                print(f"Trendy: {len(trending)} titulkov (Reddit={meta['reddit']}, YouTube={meta['youtube']}) -> temy z realneho dopytu.")
        except Exception as e:
            print("Trendy preskocene:", str(e)[:120])
    items = extract_json(call_model(build_prompt(need + 3, sorted(titles), trending)))
    added = 0
    existing_sigs = [_sig(x) for x in titles]
    for t in items:
        if not valid(t) or t["title"] in titles:
            continue
        _s = _sig(t["title"])
        if _too_similar(_s, existing_sigs):   # ta ista TEMA (iny nazov) -> preskoc (ziadne opakovanie)
            print("  preskocene (podobna tema):", t["title"]); continue
        if t.get("segments"):
            t["segments"][-1]["text"] = random.choice(CTAS)  # CTAS_ROTATE: nie vzdy rovnaka veta
        bank.append(t); titles.add(t["title"]); existing_sigs.append(_s); added += 1
    json.dump(bank, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Pridanych {added} tem. Banka ma {len(bank)} tem.")


if __name__ == "__main__":
    main()
    try:
        _clean_bank()
    except Exception as _e:
        print("Dedup preskoceny:", str(_e)[:150])

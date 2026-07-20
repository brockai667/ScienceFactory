#!/usr/bin/env python3
"""Doplni banku tem cez GitHub Models (zadarmo). Nika: VEDA & TECH.
NOVY FORMAT (PRO engine): tema = 5 scen (hook/fact/fact/callout/cta) s presnymi
subjektovymi queries, sync chipmi (len dolozitelne cisla) a kinetickym hookom.
Stare temy bez 'scenes' sa vyradia az ked su aspon 3 nove (den nikdy neostane bez videi)."""
import json
import os
import re
import sys

import requests
try:
    import trends
except Exception:
    trends = None

ROOT = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(ROOT, "topics_bank.json")
STATE = os.path.join(ROOT, "used_topics.json")

TARGET = int(os.environ.get("TOPICS_TARGET", "15"))
MODEL = os.environ.get("MODELS_MODEL", "openai/gpt-4o-mini")
BASE = os.environ.get("MODELS_BASE_URL", "https://models.github.ai/inference")
TOKEN = os.environ.get("MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN")

TREND_SUBREDDITS = ['space', 'science', 'askscience', 'biology', 'spaceporn']
TREND_YT_QUERIES = ['space discoveries', 'james webb telescope', 'human body facts', 'astronomy news']

SYSTEM = ("You are a scriptwriter for a short-form brand about fascinating SCIENCE and TECHNOLOGY: space, physics, engineering, computers, nature's mechanisms. "
          "ACCURACY IS CRITICAL: use ONLY widely-documented, verifiable facts. NEVER invent or guess "
          "numbers, percentages, dates or statistics - if a figure is not universally established, say "
          "it generally instead of making one up. You output strict JSON, nothing else.")

EXAMPLE = {
    "title": "The Machine That Left the Solar System",
    "place": "",
    "country": "",
    "scenes": [
        {
            "role": "hook",
            "text": "A machine launched in 1977 is still calling home, from beyond the solar system.",
            "hook_top": "STILL CALLING HOME SINCE 1977",
            "query": "deep space stars nebula",
            "query2": "night sky stars timelapse"
        },
        {
            "role": "fact",
            "text": "Voyager 1 is more than twenty four billion kilometers away, the most distant human-made object ever.",
            "query": "satellite space probe render",
            "query2": "space dark stars slow",
            "chips": [
                {
                    "t": "LAUNCHED 1977",
                    "on": "1977",
                    "style": "white"
                },
                {
                    "t": "24+ BILLION KM",
                    "on": "billion",
                    "style": "accent"
                }
            ],
            "punch": "billion"
        },
        {
            "role": "fact",
            "text": "Its signal takes over twenty two hours to reach Earth, traveling at the speed of light.",
            "query": "radio telescope dish night",
            "query2": "antenna satellite dish stars",
            "chips": [
                {
                    "t": "22 HOURS AT LIGHT SPEED",
                    "on": "hours",
                    "style": "accent"
                }
            ]
        },
        {
            "role": "callout",
            "text": "And it runs on less power than a light bulb, on technology older than the personal computer.",
            "query": "vintage computer electronics retro",
            "query2": "old circuit board macro",
            "label": "WEAKER THAN A BULB",
            "sub": "1970s tech, still running",
            "label_on": "power",
            "punch": "bulb"
        },
        {
            "role": "cta",
            "text": "Follow for the science that sounds impossible.",
            "query": "galaxy stars deep space",
            "query2": "milky way night timelapse"
        }
    ],
    "description": "Voyager 1 launched in 1977 and is now 24+ billion km away - still transmitting on less power than a light bulb. Follow for daily science!",
    "hashtags": [
        "#science",
        "#space",
        "#voyager",
        "#nasa",
        "#technology",
        "#universe",
        "#shorts",
        "#fyp"
    ]
}


import random  # CTAS_ROTATE

CTAS = [
    "Follow for a new science fact every day.",
    "Follow if curiosity runs your brain.",
    "Follow for the science they never taught you.",
    "Follow to feed your curious mind daily.",
    "Follow for daily science that blows your mind.",
]



PERFORMANCE = (
    "\nPERFORMANCE DATA (real results - obey this, it decides reach):\n"
    "- WHAT PERFORMS (strongly prefer these): concrete, real discoveries people can look up (James Webb, Mars, Titan, telescopes, recent space news) and surprising VERIFIED body and biology facts. Name a real thing.\n"
    "- WHAT KILLS REACH (avoid): vague hypotheticals ('what if you could fly to the moon'), speculative future scenarios, and abstract theory with no concrete named discovery - these die.\n"
)

# FORMATY: rozne kostry scen -> videa nie su vsetky rovnake sablona. Curio podpis (mix sa rotuje).
FORMATS = {
    "COUNTDOWN": ["hook", "count", "count", "count", "cta"],
    "MYTH":      ["hook", "myth", "truth", "callout", "cta"],
    "REVEAL":    ["hook", "fact", "fact", "reveal", "cta"],
    "CLASSIC":   ["hook", "fact", "fact", "callout", "cta"],
    "DEEP":      ["hook", "fact", "callout", "cta"],
}
FORMAT_MIX = ["COUNTDOWN", "REVEAL", "MYTH", "CLASSIC", "DEEP"]

_ROLE_SPEC = {
    "hook":    "hook: text (<14 words, opens a curiosity gap, never 'Did you know'); 'hook_top' = same idea in MAX 6 punchy UPPERCASE words.",
    "fact":    "fact: text (ONE concrete supporting fact); 'chips' = 1-2 {'t':'MAX 22 CHARS','on':'spoken trigger word','style':'white'|'accent'} using ONLY real documented numbers; optional 'punch' = one spoken word to zoom.",
    "callout": "callout: text; 'label' = 2-4 word on-screen takeaway; 'sub' = <=34 chars; 'label_on' = spoken trigger word.",
    "count":   "count: text (one distinct point); 'num' = item number (1,2,3); 'label' = that point in <=22 UPPERCASE chars; 'label_on' = spoken trigger word.",
    "myth":    "myth: text (states a COMMON BELIEF people wrongly hold); 'label' = that myth in <=28 chars.",
    "truth":   "truth: text (the CORRECTION / real fact busting the myth); 'label' = the real fact in <=28 chars.",
    "reveal":  "reveal: text (the surprising TWIST); 'reveal_top' = the twist in MAX 6 punchy UPPERCASE words.",
    "cta":     "cta: text (a short 'follow' line).",
}
_FMT_HINT = {
    "COUNTDOWN": "- Shape: a 3-point countdown. The three 'count' scenes are three DISTINCT facts about the topic, num=1,2,3.\n",
    "MYTH":      "- Shape: myth-buster. 'myth' states what people wrongly believe; 'truth' delivers the real documented fact.\n",
    "REVEAL":    "- Shape: build tension across the two 'fact' scenes, then 'reveal' drops the surprising twist.\n",
}



CHANNEL_ID = "UCmRfvAQKGLBRxpAF4A0b2Kw"


def own_channel_performance(top=5, bottom=5):
    """WINNERS/LOSERS z vlastneho kanala cez verejny RSS feed (ziadny kluc). Best-effort."""
    try:
        import urllib.request
        import datetime
        xml = urllib.request.urlopen("https://www.youtube.com/feeds/videos.xml?channel_id="
                                     + CHANNEL_ID, timeout=20).read().decode("utf-8", "replace")
        rows = []
        for e in re.findall(r"<entry>.*?</entry>", xml, re.S):
            t = re.search(r"<media:title>([^<]*)</media:title>", e)
            v = re.search(r'views="(\d+)"', e)
            p = re.search(r"<published>(\d{4}-\d{2}-\d{2})", e)
            if t and v:
                rows.append((int(v.group(1)), t.group(1), p.group(1) if p else ""))
        cut = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
        mature = [r for r in rows if r[2] and r[2] <= cut] or rows
        if len(mature) < 4:
            return ""
        mature.sort(key=lambda r: -r[0])
        win = " | ".join(t for _, t, _ in mature[:top])
        lose = " | ".join(t for _, t, _ in mature[-bottom:])
        return ("\nOUR CHANNEL'S LIVE RESULTS (make topics with the winners' subject-style and energy; "
                "avoid the losers' style):\nWINNERS: " + win + "\nLOSERS: " + lose + "\n")
    except Exception:
        return ""


def build_prompt_fmt(fmt, n, existing_titles, trending=None, perf=""):
    seq = FORMATS[fmt]
    roles_used = list(dict.fromkeys(seq))
    spec_lines = "\n".join("- " + _ROLE_SPEC[r] for r in roles_used)
    trend_block = ""
    if trending:
        joined = chr(10).join("- " + t for t in trending)
        trend_block = (" REAL headlines people watch this week (inspire some topics; do NOT copy "
                       "verbatim, never mention Reddit/YouTube): " + joined + " ")
    return (
        f"Generate {n} NEW faceless short-form SCIENCE/TECH video topics, ALL in the '{fmt}' format.\n"
        f"Each topic MUST have EXACTLY these scenes, in THIS order: {' -> '.join(seq)}.\n"
        "Return ONLY a JSON array. Each item = "
        "{'title':..., 'thumb':..., 'scenes':[{role fields...}], 'description':..., 'hashtags':[...]}.\n"
        "Scene field rules:\n" + spec_lines + "\n"
        "- EVERY scene needs 'query' = Pexels stock search naming the CONCRETE subject of that exact "
        "line (line about octopuses -> 'octopus underwater'; NEVER abstract) and 'query2' = fallback.\n"
        + _FMT_HINT.get(fmt, "") +
        "- hook MUST contain a concrete number, name or place; NEVER start with 'Imagine', 'What if', 'Did you know' or 'Have you ever'.\n"
        "- 'thumb' = 2-3 punchy UPPERCASE words for the thumbnail (most clickable phrase, NOT a sentence).\n"
        "- ACCURACY IS CRITICAL: only widely-documented facts and real numbers; never invent figures.\n"
        "- description: 1-2 sentences then 'Follow for daily science!'; hashtags: 6-9 incl #shorts #fyp.\n"
        "- VARY titles (bold claim / question / curiosity gap); don't start more than 1 in 5 with a number.\n"
        f"- Do NOT reuse or rephrase any of these existing titles: {existing_titles}\n"
        + PERFORMANCE + perf + trend_block +
        "Return ONLY the JSON array."
    )


def build_prompt(n, existing_titles, trending=None):
    trend_block = ""
    if trending:
        joined = chr(10).join("- " + t for t in trending)
        trend_block = (
            " WHAT REAL PEOPLE DISCUSS AND WATCH THIS WEEK (live headlines from Reddit communities and "
            "top YouTube videos in this niche): " + joined +
            " Let at least HALF of the new topics be directly inspired by a SPECIFIC item above, turned "
            "into a strong hook that STILL follows the rules. Do NOT copy any headline word-for-word, "
            "and NEVER mention Reddit or YouTube. "
        )
    return (
        f"Generate {n} NEW faceless short-form video topics for a brand about fascinating SCIENCE and TECHNOLOGY: space, physics, engineering, computers, nature's mechanisms. "
        "Each video is a punchy MICRO-DOC of ONE idea (TikTok / Reels / Shorts).\n"
        "Return ONLY a JSON array (no markdown). Each item EXACTLY this schema:\n"
        f"{json.dumps(EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Rules (PRO editing pipeline depends on these):\n"
        "- EXACTLY 5 scenes in this order: hook, fact, fact, callout, cta. Each scene 'text' = 1-2 "
        "short spoken sentences (energetic but natural voiceover).\n"
        "- hook: the single most surprising TRUE thing, under 14 words, opens a curiosity gap. "
        "'hook_top' = the same idea compressed to MAX 6 punchy words (big kinetic text on screen). "
        "Never start with 'Did you know'.\n"
        "- fact scenes: ONE concrete supporting fact each. 'chips' = 1-2 short TRUE fact-chips: "
        "{'t': 'MAX 22 CHARS', 'on': 'the spoken word that triggers it', 'style': 'white'|'accent'}. "
        "ONLY widely-documented numbers; if no reliable number exists, use a word chip.\n"
        "- callout scene: 'label' = 2-4 word on-screen label of the KEY takeaway, 'sub' = short "
        "sub-line (max 34 chars), 'label_on' = spoken trigger word.\n"
        "- 'punch' (optional): ONE spoken word where the shot subtly zooms.\n"
        "- EVERY scene needs 'query' = Pexels stock search naming the CONCRETE subject of that exact "
        "line (line about octopuses -> 'octopus underwater'; NEVER abstract) and 'query2' = visual "
        "fallback. The viewer must SEE what the line talks about.\n"
        "- prefer counterintuitive angles; include one concrete comparison a viewer can picture.\n"
        "- the video must work with sound OFF (hook text + chips tell the story) AND with eyes closed "
        "(voice explains everything).\n"
        "- description: 1-2 engaging sentences, then 'Follow for daily science!'\n"
        "- hashtags: 6-9 relevant tags including #shorts #fyp.\n"
        "- VARY THE TITLE FORMAT: mix a bold claim, a question and a curiosity gap; do NOT start more "
        "than one in five titles with a number.\n"
        f"- Do NOT reuse any of these existing titles: {existing_titles}\n"
        "- Do NOT repeat the same SUBJECT or fact as any existing title above, even reworded. Every "
        "topic must be a genuinely DIFFERENT idea.\n"
        + PERFORMANCE + trend_block +
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


_ALLOWED_ROLES = {"hook", "fact", "callout", "cta", "count", "myth", "truth", "reveal", "map", "archive"}


def valid(t):
    """Overi + doopravi temu (scenes, ROZNE formaty/role). Nevalidne odmietne, ostatne dooupravi."""
    if not isinstance(t, dict) or not t.get("title"):
        return False
    scenes = t.get("scenes")
    if not isinstance(scenes, list) or not (4 <= len(scenes) <= 7):
        return False
    for sc in scenes:
        if not isinstance(sc, dict) or not sc.get("text"):
            return False
        sc.setdefault("role", "fact")
        if sc["role"] not in _ALLOWED_ROLES:
            sc["role"] = "fact"
    scenes[0]["role"] = "hook"
    scenes[-1]["role"] = "cta"
    cnt = 0
    for sc in scenes:
        r = sc["role"]
        if r == "hook":
            top = re.sub(r"[^A-Za-z0-9' ]", "", str(sc.get("hook_top") or sc["text"]))
            sc["hook_top"] = " ".join(top.split()[:6]).upper()
        if not sc.get("query"):
            sc["query"] = str(t["title"])
        if not sc.get("query2"):
            sc["query2"] = "cinematic nature landscape"
        if r == "fact":
            chips = [c for c in (sc.get("chips") or []) if isinstance(c, dict) and c.get("t")]
            for c in chips:
                c["t"] = str(c["t"])[:24]
            sc["chips"] = chips[:2]
        elif r == "count":
            cnt += 1
            try:
                sc["num"] = int(sc.get("num") or cnt)
            except Exception:
                sc["num"] = cnt
            sc["label"] = str(sc.get("label") or sc.get("text", ""))[:22]
        elif r in ("myth", "truth"):
            sc["label"] = str(sc.get("label") or sc.get("text", ""))[:28]
        elif r == "reveal":
            rt = re.sub(r"[^A-Za-z0-9' ]", "", str(sc.get("reveal_top") or sc["text"]))
            sc["reveal_top"] = " ".join(rt.split()[:6]).upper()
    t.setdefault("place", "")
    t.setdefault("country", "")
    t.setdefault("description", t["title"] + " Follow for daily science!")
    t["thumb"] = " ".join(str(t.get("thumb") or "").split()[:4]).upper()
    t.setdefault("hashtags", ["#science", "#space", "#voyager", "#nasa"])
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



# --- ANTI-OPAKOVANIE (dedup): po behu odstrani z banky NEPOUZITE temy podobne inej teme.
_DD_STOP = set("""a an the this that these those and or but so of to in on for with at by from as is are was
were be been being it its you your they them their our we he she his her my me i do does did not no can cant
will just every most more than then there here what when why how who which while into over out up down off only
also very much many some any all if thing things way ways get make made youre follow daily wisdom mindset day
today need needs about like want wants nobody tells tell told never ever still story people world reveal
revealed discover""".split())


def _dd_sig(t):
    first = ""
    if t.get("scenes"):
        first = t["scenes"][0].get("text", "")
    elif t.get("segments"):
        first = t["segments"][0].get("text", "")
    txt = (str(t.get("title", "")) + " " + str(t.get("description", "")) + " " + str(first))
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
        return False
    jac = len(common) / (len(si | sj) or 1)
    if yc and len(common) >= 3:
        return True
    if not (yi or yj) and len(common) >= 4 and jac >= 0.5:
        return True
    return False


def _clean_bank():
    """Odstrani NEPOUZITE temy prilis podobne inej teme. Publikovane sa nikdy nemazu."""
    from collections import Counter
    bank = json.load(open(BANK, encoding="utf-8"))
    used = set(json.load(open(STATE, encoding="utf-8"))) if os.path.exists(STATE) else set()
    raws = [_dd_sig(t) for t in bank]
    df = Counter()
    for s in raws:
        for w in s:
            df[w] += 1
    cutoff = max(2, int(len(bank) * 0.25))
    sigs = [set(w for w in s if df[w] <= cutoff) for s in raws]
    ks = [s for t, s in zip(bank, sigs) if t.get("title") in used]
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
        print("Dedup: odstranenych %d podobnych nepouzitych tem." % removed)
    else:
        print("Dedup: ziadne podobne nepouzite temy.")



def main():
    if not TOKEN:
        print("CHYBA: chyba MODELS_TOKEN/GITHUB_TOKEN"); sys.exit(1)
    bank = json.load(open(BANK, encoding="utf-8"))
    used = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else []
    # MIGRACIA: stare temy vyrad az ked su aspon 3 nove PRO temy (den nikdy neostane bez videi)
    old = [t for t in bank if not t.get("scenes") and t["title"] not in used]
    new_unused = [t for t in bank if t.get("scenes") and t["title"] not in used]
    if old and len(new_unused) >= 3:
        bank = [t for t in bank if t.get("scenes") or t["title"] in used]
        print(f"Migracia: vyradenych {len(old)} nepouzitych tem stareho formatu.")
    titles = {t["title"] for t in bank}
    unused = [t for t in bank if t["title"] not in used]
    need = TARGET - len(unused)
    if need <= 0:
        json.dump(bank, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"Banka OK: {len(unused)} nepouzitych tem."); return
    print(f"Generujem ~{need} novych tem cez {MODEL}...")
    trending = []
    if trends is not None:
        try:
            trending, meta = trends.gather(TREND_SUBREDDITS, TREND_YT_QUERIES, top=18, return_meta=True)
            if trending:
                print(f"Trendy: {len(trending)} titulkov (Reddit={meta['reddit']}, YouTube={meta['youtube']}).")
        except Exception as e:
            print("Trendy preskocene:", str(e)[:120])
    # rozdel 'need' medzi formaty (rotuje sa mix) -> pestre videa, nie stale ta ista sablona
    perf = own_channel_performance()
    if perf:
        print("Live kanal-data: WINNERS/LOSERS zapracovane do promptu.")
    from collections import Counter
    plan = Counter(FORMAT_MIX[i % len(FORMAT_MIX)] for i in range(need + 2))
    items = []
    for fmt, cnt in plan.items():
        try:
            got = extract_json(call_model(build_prompt_fmt(fmt, cnt, sorted(titles), trending, perf)))
            items += got
            print(f"  format {fmt}: {len(got)} tem")
        except Exception as e:
            print(f"  format {fmt} preskoceny: {str(e)[:100]}")
    added = 0
    existing_sigs = [_sig(x) for x in titles]
    for t in items:
        if not valid(t) or t["title"] in titles:
            continue
        _s = _sig(t["title"])
        if _too_similar(_s, existing_sigs):
            print("  preskocene (podobna tema):", t["title"]); continue
        if t.get("scenes"):
            t["scenes"][-1]["text"] = random.choice(CTAS)  # CTAS_ROTATE
        bank.append(t); titles.add(t["title"]); existing_sigs.append(_s); added += 1
    json.dump(bank, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Pridanych {added} tem. Banka ma {len(bank)} tem.")


if __name__ == "__main__":
    main()
    try:
        _clean_bank()
    except Exception as _e:
        print("Dedup preskoceny:", str(_e)[:150])

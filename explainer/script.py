#!/usr/bin/env python3
"""Vyber temy + generovanie explainer scenara (Groq / GitHub Models, zadarmo).

Pouzitie:
  python explainer/script.py                       # dalsia nepouzita tema z explainer_bank.json
  python explainer/script.py "Every X Explained"   # konkretna seria (polozky vymysli model)
  python explainer/script.py --topup               # len doplni banku o nove temy-zoznamy

Vystup: explainer/scripts/<slug>.json  (format viď scripts/example_usb_colors.json)
Struktura kapitoly = referencny styl: title -> co to je + rok -> historia/preco vzniklo ->
cislo + prirovnanie zo zivota -> kde to zlyhava -> obrat ("but...") -> kde to zije dodnes ->
recnicka otazka.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

TYPES = {"title", "figure_text", "image_text", "image_only", "two_images", "three_images", "stat"}
POSES = {"idle", "point_right", "point_left", "arms_crossed", "shrug", "think", "present", "celebrate", "wave"}
MOODS = {"smile", "surprised", "neutral"}

SYSTEM = (
    "You are the scriptwriter for a faceless YouTube EXPLAINER channel in the style of short, punchy "
    "'Every X Explained' videos: white background, a stick figure narrator, simple pictures in frames. "
    "Voice: conversational, spoken English, second person, short sentences, like a smart friend explaining "
    "something over coffee. Every claim must be a real, widely-documented fact with real numbers and years; "
    "NEVER invent statistics. Turn abstract numbers into everyday comparisons ('that is about three seconds "
    "per photo'). Avoid brand bashing and legal claims. You output STRICT JSON only, no markdown."
)


def outline_prompt(series, items, n_min, n_max):
    items_line = (f"Use EXACTLY these items in this order as chapters: {', '.join(items)}.\n"
                  if items else f"Choose {n_min} to {n_max} items that together cover the whole topic, in a logical order (oldest to newest, or simplest to most advanced).\n")
    return (
        f"Plan a YouTube explainer video titled \"{series}\".\n" + items_line +
        "Return ONLY JSON with this schema:\n"
        "{\n"
        '  "title": "YouTube title, max 70 chars, curiosity + clarity",\n'
        '  "description": "2-3 sentences for the YouTube description",\n'
        '  "hashtags": ["#tech","#explained", "... 6-8 tags"],\n'
        '  "hook_say": "2-3 spoken sentences for the cold open: name a common wrong assumption, say it is wrong, promise the payoff. Under 45 words. Never start with Did you know.",\n'
        '  "thumb_text": "3-5 word thumbnail text, ALL CAPS on the key word",\n'
        '  "thumb_image": "prompt for ONE concrete hero object for the thumbnail (physical object, no people, no text)",\n'
        '  "chapters": [\n'
        '    {"name": "full chapter name", "label": "1-2 WORD UPPERCASE HUD label", '
        '"icon": "prompt: the ONE physical object that represents this chapter, front view, no people, no text", '
        '"hook": "one spoken sentence hook for this chapter as a standalone short video, under 20 words"}\n'
        "  ],\n"
        '  "outro_say": "2 spoken sentences: a practical takeaway + subscribe, mention next Monday",\n'
        '  "outro_show": "on-screen text for the outro, max 8 words"\n'
        "}\n"
        "Return ONLY the JSON."
    )


def chapter_prompt(series, ch, idx, total, n_beats, prev_names):
    prev = (f"Chapters already covered: {', '.join(prev_names)}. Do not repeat their content.\n"
            if prev_names else "")
    return (
        f"Video: \"{series}\". Write chapter {idx + 1} of {total}: \"{ch['name']}\".\n" + prev +
        f"Write EXACTLY {n_beats} beats. A beat = one slide + what the narrator says over it.\n"
        "Follow THIS ORDER of beats:\n"
        f"  1. type 'title': say just the chapter name ('{ch['name']}.'), show the same.\n"
        "  2. What it is + the year/era it appeared (real year).\n"
        "  3-4. Why it exists / what came before it / the problem it solved.\n"
        "  5-6. A real NUMBER (speed, size, price, temperature, ...) + an everyday comparison "
        "(a 'stat' beat with the number as 'stat' and a 3-6 word 'label').\n"
        "  7-8. Where it struggles or fails, concretely.\n"
        "  9-10. The twist: 'but that barely mattered because...' or 'but here is the catch...'.\n"
        "  11-12. Where it survives or is used today (concrete devices/places).\n"
        f"  {n_beats}. Closing line: a rhetorical question or a one-line verdict.\n"
        "Fill remaining beats with the most surprising real details.\n"
        "Beat schema (JSON object per beat):\n"
        '{"say": "12-30 spoken words", "show": "2-6 word on-screen text (a keyword, number or short phrase - NOT the whole sentence)", '
        '"type": "title|figure_text|image_text|image_only|two_images|three_images|stat", '
        '"image": "prompt for a concrete PHYSICAL OBJECT or scene (no people, no text, no logos)", '
        '"image2": "second object (only two_images/three_images)", "image3": "third (only three_images)", '
        '"label": "short caption under image / stat label", "label2": "...", "label3": "...", '
        '"stat": "the number as text, e.g. 60 MB/s (only type stat)", '
        '"pose": "point_right|shrug|think|present|arms_crossed|celebrate|idle (only figure_text)", '
        '"mood": "smile|surprised|neutral"}\n'
        "Rules: use image_text or image_only for at least half of the beats (pictures carry the video); "
        "figure_text for commentary/opinion beats; two_images to compare two things; three_images to list "
        "three devices; stat exactly once or twice. Image prompts must be simple objects that an image "
        "generator draws well (a port, a cable, a device, a machine, a landscape) - never diagrams, charts, "
        "text, screenshots or people. Real facts only.\n"
        'Return ONLY JSON: {"beats": [ ... ]}'
    )


TOPUP_PROMPT = (
    "Give me 12 NEW topics for 'Every X Explained' YouTube videos about technology, science, engineering, "
    "or everyday objects. Each topic must be a LIST of 6-8 concrete items that can each be explained in "
    "about 90 seconds with real facts, years and numbers (like 'Every USB Port Color Explained' with items "
    "White, Black, Blue...). Avoid these already used: {used}.\n"
    'Return ONLY JSON: {"topics": [{"series": "Every ... Explained", "items": ["...", "..."]}]}'
)


# ---------------------------------------------------------------- validacia
def _clean_beat(b, idx, name):
    typ = str(b.get("type", "figure_text")).strip().lower()
    if typ not in TYPES:
        typ = "image_text" if b.get("image") else "figure_text"
    out = {"say": str(b.get("say", "")).strip(), "show": str(b.get("show", "")).strip()[:60], "type": typ}
    if idx == 0:
        out["type"] = "title"
        out["show"] = out["show"] or name
        out["say"] = out["say"] or (name + ".")
    for k in ("image", "image2", "image3", "label", "label2", "label3", "stat"):
        v = b.get(k)
        if v:
            out[k] = str(v).strip()
    if typ in ("image_text", "image_only", "stat") and not out.get("image") and typ != "stat":
        out["type"] = "figure_text"
    if typ == "two_images" and not (out.get("image") and out.get("image2")):
        out["type"] = "image_text" if out.get("image") else "figure_text"
    if typ == "three_images" and not (out.get("image") and out.get("image2") and out.get("image3")):
        out["type"] = "image_text" if out.get("image") else "figure_text"
    if typ == "stat" and not out.get("stat"):
        out["stat"] = out["show"]
    pose = str(b.get("pose", "")).strip().lower()
    if pose in POSES:
        out["pose"] = pose
    mood = str(b.get("mood", "")).strip().lower()
    if mood in MOODS:
        out["mood"] = mood
    return out


def _words(s):
    return len(re.findall(r"\w+", s))


def gen_chapter(series, ch, idx, total, n_beats, prev_names, tries=3):
    for att in range(tries):
        data = common.llm_json(chapter_prompt(series, ch, idx, total, n_beats, prev_names), SYSTEM,
                               temperature=0.75, max_tokens=5000)
        beats = data.get("beats") if isinstance(data, dict) else data
        if not isinstance(beats, list):
            continue
        beats = [_clean_beat(b, i, ch["name"]) for i, b in enumerate(beats) if isinstance(b, dict)]
        beats = [b for b in beats if b["say"]]
        total_words = sum(_words(b["say"]) for b in beats)
        if len(beats) >= max(8, n_beats - 4) and total_words >= 120:
            return beats[:n_beats + 3]
        print(f"   [script] kapitola {idx + 1}: slaba odpoved ({len(beats)} beatov, {total_words} slov) - znova")
    raise RuntimeError(f"Kapitola '{ch['name']}' sa nepodarila vygenerovat.")


def generate(series, items=None):
    cfg = common.load_cfg()
    e = cfg["explainer"]
    common.ensure_dirs()
    print(f"== Osnova: {series}")
    ol = common.llm_json(outline_prompt(series, items, e["chapters_min"], e["chapters_max"]), SYSTEM,
                         temperature=0.7, max_tokens=3000)
    chapters = [c for c in ol.get("chapters", []) if isinstance(c, dict) and c.get("name")]
    if items:
        # drz poradie a pocet z banky
        by_idx = {i: c for i, c in enumerate(chapters)}
        chapters = [{"name": it, "label": (by_idx.get(i, {}).get("label") or it).upper()[:18],
                     "icon": by_idx.get(i, {}).get("icon") or f"a {it} object, front view, no people, no text",
                     "hook": by_idx.get(i, {}).get("hook", "")} for i, it in enumerate(items)]
    else:
        chapters = chapters[:e["chapters_max"]]
        for c in chapters:
            c["label"] = str(c.get("label") or c["name"]).upper()[:18]
    if len(chapters) < 3:
        raise RuntimeError("Osnova ma menej ako 3 kapitoly.")
    spec = {
        "series": series,
        "title": str(ol.get("title") or series)[:100],
        "description": str(ol.get("description", "")),
        "hashtags": [h if str(h).startswith("#") else "#" + str(h) for h in ol.get("hashtags", [])][:10]
                    or ["#explained", "#tech", "#science", "#didyouknow"],
        "hook_say": str(ol.get("hook_say", "")),
        "thumb_text": str(ol.get("thumb_text") or series)[:40],
        "thumb_image": str(ol.get("thumb_image", "")),
        "chapters": [],
        "outro": {"say": str(ol.get("outro_say") or "Subscribe, and see you next Monday."),
                  "show": str(ol.get("outro_show") or "See you next Monday.")},
    }
    names = []
    for i, ch in enumerate(chapters):
        print(f"   kapitola {i + 1}/{len(chapters)}: {ch['name']}")
        beats = gen_chapter(series, ch, i, len(chapters), int(e["beats_per_chapter"]), names)
        spec["chapters"].append({"name": ch["name"], "label": ch["label"], "icon": ch.get("icon", ""),
                                 "hook": ch.get("hook", ""), "beats": beats})
        names.append(ch["name"])
    words = sum(_words(b["say"]) for c in spec["chapters"] for b in c["beats"])
    print(f"   scenar: {len(spec['chapters'])} kapitol, {words} slov (~{words / 155:.1f} min)")
    path = os.path.join(common.SCRIPTS_DIR, common.slug(series) + ".json")
    common.save_json(path, spec)
    return path, spec


# ---------------------------------------------------------------- banka tem
def topup_bank():
    bank = common.load_json(common.BANK, [])
    used = common.load_json(common.STATE, [])
    known = {b["series"].lower() for b in bank} | {u.lower() for u in used}
    data = common.llm_json(TOPUP_PROMPT.format(used=", ".join(sorted(known))[:1500]), SYSTEM,
                           temperature=0.9, max_tokens=2500)
    added = 0
    for t in data.get("topics", []):
        s = str(t.get("series", "")).strip()
        it = [str(x).strip() for x in t.get("items", []) if str(x).strip()]
        if s and 5 <= len(it) <= 9 and s.lower() not in known:
            bank.append({"series": s, "items": it})
            known.add(s.lower())
            added += 1
    common.save_json(common.BANK, bank)
    print(f"   banka: +{added} tem (spolu {len(bank)})")


def pick_topic():
    bank = common.load_json(common.BANK, [])
    used = set(common.load_json(common.STATE, []))
    for t in bank:
        if t["series"] not in used:
            return t
    print("   banka prazdna -> doplnam")
    topup_bank()
    bank = common.load_json(common.BANK, [])
    for t in bank:
        if t["series"] not in used:
            return t
    raise RuntimeError("Ziadna nepouzita tema.")


def mark_used(series):
    used = common.load_json(common.STATE, [])
    if series not in used:
        used.append(series)
        common.save_json(common.STATE, used)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--topup" in sys.argv:
        topup_bank()
        sys.exit(0)
    if args:
        series, items = args[0], None
    else:
        t = pick_topic()
        series, items = t["series"], t.get("items")
    path, spec = generate(series, items)
    mark_used(series)
    print("OK:", path)

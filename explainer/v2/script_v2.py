#!/usr/bin/env python3
"""Generovanie explainer spec-u (v2 format) cez Groq.

  python explainer/v2/script_v2.py                         # dalsia tema z explainer_bank.json
  python explainer/v2/script_v2.py "Every HDMI Version Explained"
  python explainer/v2/script_v2.py --items "1.0,1.3,1.4,2.0,2.1" "Every HDMI Version Explained"

Vystup: explainer/v2/specs/<slug>.json  ->  python explainer/v2/engine.py <spec> <out_dir>

Principy (LEARNINGS.md): hook cez omyl, nie definicia; kazda veta = cue (kratke frazy, na ktore
sa odhaluju prvky); konkretne cisla + prirovnanie zo zivota; kazdy beat ma vizual (emoji);
struktura kapitoly: hook -> title -> focus (co+rok) -> list (pred/okolo) -> stat (cislo) ->
compare (obrat/dnes) [-> focus 2]. Intro serie: compare (omyl) + grid (vsetky polozky).
"""
import json
import os
import re
import sys

V2 = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(V2)
for p in (EXP, V2):
    if p not in sys.path:
        sys.path.insert(0, p)
import common  # noqa: E402
import icons  # noqa: E402

SPECS = os.path.join(V2, "specs")
TPLS = {"hook", "title", "focus", "list", "stat", "compare"}

SYSTEM = (
    "You write scripts for a faceless YouTube explainer channel in the 'Every X Explained' style: white paper "
    "background, flat icon illustrations, a stick-figure narrator, kinetic text. Voice: spoken, conversational, "
    "second person, short punchy sentences, like a smart friend. Every fact must be real and widely documented, "
    "with real years and numbers; never invent statistics. Turn numbers into everyday comparisons. "
    "You output STRICT JSON only, no markdown, no commentary."
)

OUTLINE_PROMPT = """Plan the video "{series}".
{items_line}
Return ONLY this JSON:
{{
 "title": "YouTube title, max 70 chars, curiosity + clarity",
 "description": "2-3 sentences",
 "hashtags": ["#...", 6-8 tags],
 "hero_emoji": "ONE emoji of the PHYSICAL OBJECT the video is about (the plug/cable/device itself, e.g. 🔌 for HDMI or USB, 💾 for storage, 🔋 for batteries; never a face, rocket, satellite or abstract symbol)",
 "intro": {{
   "compare": {{
     "say": "2 spoken sentences: name a common wrong assumption about two of the items, then 'They are not.' style denial. Under 40 words.",
     "left": {{"emoji": "emoji for item A", "label": "Item A"}},
     "right": {{"emoji": "emoji for item B", "label": "Item B"}},
     "line": "the wrong assumption as a 3-5 word question, e.g. Just a design choice?",
     "cues": {{"left": "2-3 words from say where item A is mentioned", "right": "2-3 words where item B is mentioned",
               "line": "2-3 words where the assumption is stated", "strike": "the denial words, e.g. They are not."}}
   }},
   "grid": {{
     "say": "3 spoken sentences: what the differences mean in general, 'This is every <topic>, explained.', and 'Starting with <first item>'. Under 45 words.",
     "cues": {{"grid": "first 2 words of say", "title": "the word explained", "mark": "2 words where the first item is announced"}},
     "pulse": [{{"cue": "a word from sentence 1 naming a property", "items": [indexes of items with that property]}}]
   }}
 }},
 "chapters": [ {{"name": "{{item}}", "label": "1-2 WORD UPPERCASE", "emoji": "ONE concrete OBJECT emoji that fits this item (for versions of the same product use the product emoji; never abstract symbols or faces)", "hook": "one spoken sentence hook for this item as a standalone short, under 18 words"}} ],
 "outro": {{"say": "2 spoken sentences: a practical takeaway, then a final 4-6 word verdict line, plus 'See you next Monday.'", "type_text": "the verdict line verbatim (max 5 words)", "cues": {{"key": "the key word of the verdict"}}}}
}}
CUE RULE: every cue must be an EXACT word-for-word substring (2-4 words) of the matching "say". Items in order. Return ONLY the JSON."""

FACTS_PROMPT = """Fact sheet for the video "{series}". Items, in order: {items}.
For EACH item return only facts you are highly confident are true and widely documented (Wikipedia-level).
Return ONLY this JSON:
{{"facts":[{{"name":"item","year":"release year or era","key_number":"the one headline number WITH unit (e.g. 10.2 Gbit/s, 480 Mbit/s)",
  "new":["up to 3 things it introduced"],"lacked":"one thing it could not do","still_used":"where it is still used today",
  "compare":"one sentence vs the previous item, with numbers only if certain"}}]}}
Never guess a number. If you are not sure, write "unknown"."""

CHAPTER_PROMPT = """Video "{series}", chapter {idx} of {total}: "{name}" (label {label}, emoji {emoji}).
{facts}{prev}Write 8 beats for THIS chapter, in this order. A beat = one animated scene + the narrator's words over it.
Below is a COMPLETE EXAMPLE for a different topic (white USB port). Copy the STRUCTURE and the level of detail,
NEVER the content. Every value must be written fresh for "{name}".

[
 {{"tpl":"hook","say":"The white one. On an old computer it looks like cheap plastic. It is not. White is the original. The very first USB ever made.",
  "slams":[{{"text":"THE WHITE USB PORT."}},{{"text":"“CHEAP PLASTIC”","cue":"cheap plastic","strike":true}},
           {{"text":"IT'S NOT.","cue":"It is not","color":"red","strike_on":"It is not"}},{{"text":"THE ORIGINAL.","cue":"the original","color":"blue"}}]}},
 {{"tpl":"title","say":"{name}.","title":"{name}","kicker":"{series_short}, PART {idx}"}},
 {{"tpl":"focus","say":"White means USB one point zero, straight from nineteen ninety six. Spot one, and you are looking at a real piece of computer history.",
  "head":"USB 1.0","label":"1996 — the first generation","stamp":"1996",
  "callouts":[["#c9a227","4 gold pins"],["#1c4ed8","power + data in one cable"]],
  "cues":{{"head":"White means","stamp":"ninety six","action":"Spot one","circle":"computer history","callouts":"Spot one"}}}},
 {{"tpl":"list","say":"Before USB, every device had its own plug. One port for the printer. Another for the keyboard. A third one for the mouse.",
  "head":"Before USB","sub":{{"text":"one plug per device","cue":"its own plug"}},"hub":{{"emoji":"🖥️"}},
  "items":[{{"emoji":"🖨️","label":"Printer","cue":"printer"}},{{"emoji":"⌨️","label":"Keyboard","cue":"keyboard"}},{{"emoji":"🖱️","label":"Mouse","cue":"mouse"}}]}},
 {{"tpl":"stat","say":"Top speed? One and a half megabytes per second. A single photo from your phone would take three whole seconds to copy.",
  "num_end":1.5,"decimals":1,"unit":"MB/s","label":"USB 1.0 top speed","sub":"3 seconds — one photo",
  "vis":{{"emoji":"📱"}},"travel":{{"to":{{"emoji":"🔌"}},"seconds":3}},"cues":{{"count":"and a half","sub":"whole seconds"}}}},
 {{"tpl":"focus","say":"Where it struggled was anything big. Copying a full CD of music took over an hour. But back then nobody moved files that way.",
  "head":"The weak spot","label":"700 MB — one hour","stamp":"SLOW",
  "callouts":[["#d62828","one CD = one hour"],["#7a7a7a","files lived on discs"]],
  "cues":{{"head":"Where it struggled","action":"full CD","circle":"over an hour","callouts":"nobody moved"}}}},
 {{"tpl":"list","say":"So people used white ports for three things. Keyboards. Mice. And the first digital cameras.",
  "head":"What it was for","sub":{{"text":"small data, no hurry","cue":"three things"}},"hub":null,
  "items":[{{"emoji":"⌨️","label":"Keyboards","cue":"Keyboards"}},{{"emoji":"🖱️","label":"Mice","cue":"Mice"}},{{"emoji":"📷","label":"Cameras","cue":"digital cameras"}}]}},
 {{"tpl":"compare","say":"But here is the twist. USB one never died. Car stereos and cheap MP3 players still use it today. Why pay for a faster chip, when the slow one does the job?",
  "head":"It never died","ekg":"never died",
  "left":{{"emoji":"📻","label":"Car stereo","cue":"stereos"}},"right":{{"emoji":"🎧","label":"MP3 player","cue":"players"}},
  "line":"Why pay for more?","cues":{{"line":"faster chip"}}}}
]

Rules for "{name}":
- Use the FACT SHEET above as ground truth: its numbers and years EXACTLY. Never contradict it, never add numbers not in it unless certain.
- When you mention ANOTHER version/item for comparison, cite its numbers only if you are certain; otherwise compare in words.
- Spoken sentences: short, conversational, second person. Hook under 35 words, others under 34 words.
- Every "cue" is an EXACT word-for-word substring (2-4 words) of that beat's "say". Cues must be WORDS, never numbers or units
  (write "and a half", not "1.5 MB/s"). Spell numbers in "say" the way a narrator says them (e.g. "ten point two gigabits").
- Slam texts are short real phrases in UPPERCASE (3-6 words). Never write placeholders like "THE TRUTH, 3-5 WORDS".
- emoji: standard Unicode OBJECTS related to the item (no flags, no faces, no abstract symbols).
- Exactly ONE hook (first) and ONE title (second). Never add another hook at the end.
- Output ONLY: {{"beats":[ ...8 beats... ]}}"""


def collect_beats(data):
    """Rekurzivne vyzbiera vsetky dict-y s klucom 'tpl' (model obcas vrati pokazenu strukturu)."""
    out = []

    def walk(x):
        if isinstance(x, dict):
            if "tpl" in x and "say" in x:
                out.append(x)
            else:
                for v in x.values():
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data)
    # dedup len presnych duplikatov (tpl + say); druhy focus/list je v 8-beatovej kapitole ziadany
    seen, uniq = set(), []
    for b in out:
        key = (str(b["tpl"]).lower(), str(b["say"]).strip().lower())
        if key not in seen:
            seen.add(key)
            uniq.append(b)
    return uniq


def _sub_ok(say, phrase):
    a, b = " ".join(common_norm(say)), " ".join(common_norm(phrase))
    return bool(b) and b in a


def common_norm(s):
    return re.sub(r"[^a-z0-9 ]", "", str(s).lower()).split()


def fix_cues(b):
    """Odstrani cue, ktore nie su v say (engine spravi fallback); vizualy emoji -> overi existenciu ikony."""
    say = b.get("say", "")
    cues = b.get("cues") or {}
    b["cues"] = {k: v for k, v in cues.items() if isinstance(v, str) and _sub_ok(say, v)}
    for key in ("slams", "items"):
        for it in b.get(key, []) or []:
            if isinstance(it, dict) and it.get("cue") and not _sub_ok(say, it["cue"]):
                it.pop("cue", None)
            if isinstance(it, dict) and it.get("strike_on") and not _sub_ok(say, it["strike_on"]):
                it.pop("strike_on", None)
    for key in ("left", "right"):
        it = b.get(key)
        if isinstance(it, dict) and it.get("cue") and not _sub_ok(say, it["cue"]):
            it.pop("cue", None)
    if b.get("sub") and isinstance(b["sub"], dict) and b["sub"].get("cue") and not _sub_ok(say, b["sub"]["cue"]):
        b["sub"].pop("cue", None)
    if b.get("ekg") and not _sub_ok(say, b["ekg"]):
        b["ekg"] = None
    return b


def vis_from(obj):
    """{'emoji': x} -> {'emoji': x} ak existuje ikona, inak {'query': label} alebo None."""
    if not isinstance(obj, dict):
        return None
    e = obj.get("emoji")
    if e and icons.path_for_emoji(e):
        return {"emoji": e}
    q = obj.get("label") or obj.get("query") or ""
    if q and icons.search(q, 1):
        return {"query": q}
    return None


def coerce_beat(b, name):
    tpl = str(b.get("tpl", "")).lower()
    if tpl not in TPLS:
        return None
    b["tpl"] = tpl
    b["say"] = str(b.get("say", "")).strip()
    if not b["say"]:
        return None
    if tpl == "hook":
        bad = ("3-5 WORDS", "4-6 WORD", "THE MISCONCEPTION", "THE TRUTH,", "WORDS IN SAY", "UPPERCASE")
        sl = [s for s in b.get("slams", []) if isinstance(s, dict) and s.get("text")
              and not any(x in str(s["text"]).upper() for x in bad)][:5]
        if len(sl) < 3:
            # malo slamov = dlho staticky text; doplnit z kratkych viet hovoreneho textu (cue = prve 2 slova)
            have = {str(x["text"]).strip().upper().rstrip(".!?") for x in sl}
            for sent in re.split(r"(?<=[.!?])\s+", b["say"]):
                w = sent.strip().rstrip(".!?").split()
                if 2 <= len(w) <= 6 and " ".join(w).upper() not in have:
                    sl.append({"text": " ".join(w).upper() + ".", "cue": " ".join(w[:2])})
                    have.add(" ".join(w).upper())
                if len(sl) >= 4:
                    break
        if not sl:
            sl = [{"text": name.upper()}]
        # poradie slamov podla miesta cue v texte (doplnene z viet mozu patrit na zaciatok)
        say_l = b["say"].lower()
        n_sl = max(1, len(sl))
        def _pos(k_x):
            k, x = k_x
            pos = say_l.find(str(x.get("cue", "")).lower()) if x.get("cue") else -1
            return pos if pos >= 0 else k * len(say_l) / n_sl
        sl = [x for _, x in sorted(enumerate(sl), key=_pos)]
        b["slams"] = sl[:5]
    elif tpl == "list":
        items = []
        for it in b.get("items", [])[:4]:
            if not isinstance(it, dict):
                continue
            it["vis"] = vis_from(it)
            items.append(it)
        b["items"] = items
        hub = b.get("hub")
        b["hub"] = vis_from(hub) if isinstance(hub, dict) and hub.get("emoji") else None
        if not items:
            return None
    elif tpl == "stat":
        try:
            b["num_end"] = float(b.get("num_end"))
        except (TypeError, ValueError):
            return None
        b["vis"] = vis_from(b.get("vis"))
        tr = b.get("travel")
        if isinstance(tr, dict) and vis_from(tr.get("to")):
            b["travel"] = {"to": vis_from(tr.get("to")), "seconds": int(tr.get("seconds", 3))}
        else:
            b["travel"] = None
    elif tpl == "compare":
        for key in ("left", "right"):
            it = b.get(key) or {}
            it["vis"] = vis_from(it)
            b[key] = it
    elif tpl == "focus":
        b["callouts"] = [c for c in b.get("callouts", []) if isinstance(c, list) and len(c) == 2][:3]
        if b.get("stamp"):
            b["stamp"] = str(b["stamp"])[:8]
    return fix_cues(b)


def generate(series, items=None):
    cfg = common.load_cfg()
    e = cfg["explainer"]
    os.makedirs(SPECS, exist_ok=True)
    icons.ensure()
    items_line = (f"Use EXACTLY these items in this order as chapters: {', '.join(items)}."
                  if items else f"Choose {e['chapters_min']} to {e['chapters_max']} items that cover the topic, oldest/simplest first.")
    print(f"== Osnova: {series}")
    ol = common.llm_json(OUTLINE_PROMPT.format(series=series, items_line=items_line), SYSTEM, temperature=0.7, max_tokens=3500)
    chapters = [c for c in ol.get("chapters", []) if isinstance(c, dict) and c.get("name")]
    if items:
        by = {i: c for i, c in enumerate(chapters)}
        chapters = [{"name": it, "label": str(by.get(i, {}).get("label") or it).upper()[:18],
                     "emoji": by.get(i, {}).get("emoji"), "hook": by.get(i, {}).get("hook", "")} for i, it in enumerate(items)]
    chapters = chapters[:int(e["chapters_max"])]
    if len(chapters) < 3:
        raise RuntimeError("Osnova ma menej ako 3 kapitoly.")
    seen = {}
    for c in chapters:
        c["label"] = str(c.get("label") or c["name"]).upper()[:18]
        seen[c["label"]] = seen.get(c["label"], 0) + 1
        if seen[c["label"]] > 1:
            c["label"] = (c["label"][:14] + " " + str(seen[c["label"]]))[:18]
        c["icon"] = vis_from(c) or {"query": c["name"]}
    hero = vis_from({"emoji": ol.get("hero_emoji")}) or chapters[0]["icon"]
    intro = ol.get("intro") or {}
    comp = intro.get("compare") or {}
    grid = intro.get("grid") or {}
    for key in ("left", "right"):
        it = comp.get(key) or {}
        it["vis"] = vis_from(it) or hero
        comp[key] = it
    comp = fix_cues(comp) if comp.get("say") else None
    if grid.get("say"):
        grid["stamp"] = "PART 1"
        pulse = []
        for pz in grid.get("pulse", []) or []:
            if isinstance(pz, dict) and _sub_ok(grid["say"], str(pz.get("cue", ""))):
                pulse.append({"cue": pz["cue"], "items": [int(k) for k in pz.get("items", []) if isinstance(k, (int, float)) and 0 <= int(k) < len(chapters)]})
        grid["pulse"] = pulse
        grid = fix_cues(grid)
    else:
        grid = None
    spec = {
        "series": series,
        "title": str(ol.get("title") or series)[:100],
        "description": str(ol.get("description", "")),
        "hashtags": [h if str(h).startswith("#") else "#" + str(h) for h in ol.get("hashtags", [])][:10] or ["#explained", "#tech"],
        "hero": hero,
        "cta": e.get("cta_footer", "Full video on YouTube: link in bio"),
        "intro": {"compare": comp, "grid": grid},
        "chapters": [],
        "outro": None,
    }
    series_short = re.sub(r",?\s*explained\.?$", "", series, flags=re.I).upper()
    # Verzie toho isteho produktu (HDMI 1.0, HDMI 1.3...) -> jedna ikona (hero) pre vsetky kapitoly, lisia sa labelom
    words0 = [c["name"].split()[0].lower() for c in chapters if c["name"].split()]
    if len(chapters) >= 3 and len(set(words0)) == 1 and spec["hero"]:
        for c in chapters:
            c["icon"] = spec["hero"]
    # Fact sheet = ground truth pre vsetky kapitoly (jedno volanie, konzistentne cisla)
    facts_txt = ""
    try:
        fx = common.llm_json(FACTS_PROMPT.format(series=series, items=", ".join(c["name"] for c in chapters)), SYSTEM,
                             temperature=0.2, max_tokens=1800)
        fl = [f for f in (fx.get("facts") or []) if isinstance(f, dict) and f.get("name")]
        if fl:
            facts_txt = "FACT SHEET (ground truth):\n" + "\n".join(
                f"- {f.get('name')}: year {f.get('year')}; key number {f.get('key_number')}; new: {', '.join(map(str, f.get('new') or []))}; "
                f"lacked: {f.get('lacked')}; still used: {f.get('still_used')}; vs previous: {f.get('compare')}" for f in fl) + "\n"
            spec["facts"] = fl
    except Exception as ex:  # noqa: BLE001
        print(f"   [script] fact sheet zlyhal: {ex}")
    names = []
    for i, ch in enumerate(chapters):
        print(f"   kapitola {i + 1}/{len(chapters)}: {ch['name']}")
        prev = f"Chapters already done: {', '.join(names)}. Do not repeat their facts.\n" if names else ""
        beats = None
        for att in range(3):
            data = common.llm_json(CHAPTER_PROMPT.format(series=series, idx=i + 1, total=len(chapters), name=ch["name"],
                                                         label=ch["label"], emoji=ch.get("emoji") or "", prev=prev, facts=facts_txt,
                                                         series_short=series_short), SYSTEM, temperature=0.75, max_tokens=3600)
            raw = collect_beats(data)
            if not raw:
                continue
            beats = [x for x in (coerce_beat(b, ch["name"]) for b in raw) if x]
            if len(beats) >= 7:
                break
            print(f"   [script] raw tpl: {[str(b.get('tpl')) for b in raw]} -> platne: {[b['tpl'] for b in beats]}")
            print(f"   [script] kapitola {i + 1}: len {len(beats)} platnych beatov - znova")
        if not beats or len(beats) < 4:
            raise RuntimeError(f"Kapitola '{ch['name']}' sa nepodarila.")
        # len prvy hook a jeden title; dalsie (model obcas prida hook na koniec) von
        seen_one = set()
        kept = []
        for b in beats:
            if b["tpl"] in ("hook", "title"):
                if b["tpl"] in seen_one:
                    continue
                seen_one.add(b["tpl"])
            kept.append(b)
        beats = kept
        # title beat vzdy s kickerom; ak chyba, vloz
        if not any(b["tpl"] == "title" for b in beats):
            beats.insert(1, {"tpl": "title", "say": ch["name"] + ".", "title": ch["name"], "kicker": f"{series_short}, PART {i + 1}"})
        spec["chapters"].append({"name": ch["name"], "label": ch["label"], "icon": ch["icon"], "hook": ch.get("hook", ""), "beats": beats})
        names.append(ch["name"])
    out = ol.get("outro") or {}
    if out.get("say"):
        o = {"say": str(out["say"]), "type_text": str(out.get("type_text", ""))[:40], "cues": out.get("cues") or {}}
        spec["outro"] = fix_cues(o)
    words = sum(len(b["say"].split()) for c in spec["chapters"] for b in c["beats"])
    print(f"   spec: {len(spec['chapters'])} kapitol, {words} slov (~{words / 155:.1f} min + intro/outro)")
    path = os.path.join(SPECS, common.slug(series) + ".json")
    common.save_json(path, spec)
    return path, spec


if __name__ == "__main__":
    argv = sys.argv[1:]
    items = None
    if "--items" in argv:
        k = argv.index("--items")
        items = [x.strip() for x in argv[k + 1].split(",") if x.strip()]
        del argv[k:k + 2]
    if argv:
        series = argv[0]
    else:
        import script as sc
        t = sc.pick_topic()
        series, items = t["series"], t.get("items")
    path, spec = generate(series, items)
    print("OK:", path)

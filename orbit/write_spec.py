"""ORBIT: napise spec videa z Wikipedie (Groq, zadarmo) + fotky z Wikimedia Commons + kontrola faktov.
python orbit/write_spec.py [slug]   (bez slugu = dalsia "todo" tema z topics/queue.json)
-> orbit/specs/<slug>.json, orbit/photos/<slug>/pN.jpg. Kameru (zoom) pocita kod z velkosti utvaru, nie model."""
import html, json, math, os, re, sys, time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.join(HERE, "topics")
UA = {"User-Agent": "CurioBot/1.0 (https://github.com/brockai667/ScienceFactory) python-requests"}
SIGNOFF = "Follow for the next scan. Orbi out."          # pevny koniec kazdeho dielu (seria)
NUMW = set("two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
           "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion".split())
COLORW = re.compile(r"\b(blue|green|red|white|black|pink|yellow|orange|purple|turquoise|golden|brown|gr[ae]y)\b", re.I)
Z_MAX = 17.0                  # Esri ma ostre snimky vsade len priblizne do z17 (nad 17 sa mieša z18, ta nie vsade je)


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- LLM (Groq, OpenAI-kompatibilne)
def llm(messages, temp=0.7):
    base = os.environ.get("MODELS_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    tok = os.environ["MODELS_TOKEN"]
    for model in (os.environ.get("MODELS_MODEL", "openai/gpt-oss-120b"), os.environ.get("MODELS_FALLBACK", "openai/gpt-oss-20b")):
        strict, effort = True, "medium"
        for a in range(5):
            wait = 8 * (a + 1)
            try:
                body = {"model": model, "messages": messages, "temperature": temp, "reasoning_effort": effort,
                        "max_completion_tokens": max(1500, 7600 - len(json.dumps(messages)) // 3)}   # prompt + strop <= 8000 TPM
                if strict:
                    body["response_format"] = {"type": "json_object"}
                r = requests.post(base + "/chat/completions", headers={"Authorization": "Bearer " + tok}, json=body, timeout=180)
                if r.status_code == 200:
                    ch = r.json()["choices"][0]
                    txt = ch["message"].get("content") or ""
                    if "{" not in txt:                           # cele tokeny zjedlo uvazovanie -> menej uvazovat
                        log(f"   llm {model}: prazdna odpoved ({ch.get('finish_reason')}, {r.json().get('usage', {}).get('completion_tokens')} tok)")
                        effort, wait = "low", 3
                        time.sleep(wait)
                        continue
                    return json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
                if "json_validate_failed" in r.text:             # Groq obcas vrati prazdny JSON rezim -> bez neho, JSON vyrezat z textu
                    strict, effort, wait = False, "low", 3
                m = re.search(r"try again in ([0-9.]+)s", r.text)     # Groq free: 8000 tokenov/min
                if r.status_code == 429 and m:
                    wait = float(m.group(1)) + 2
                log(f"   llm {model} {r.status_code}, cakam {wait:.0f} s" + ("" if r.status_code == 429 and m else ": " + r.text[:300]))
            except (requests.RequestException, ValueError, KeyError) as e:
                log(f"   llm {model} chyba: {e}")
            time.sleep(wait)
    sys.exit("LLM nedostupny")


# ---------------------------------------------------------------- Wikimedia Commons
OK_LIC = re.compile(r"^(public domain|pd|cc0|cc by(-sa)? [0-9.]+)", re.I)


def strip(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def commons_photos(title, lat, lon, n=6):
    api = "https://commons.wikimedia.org/w/api.php"
    base = {"action": "query", "format": "json", "formatversion": 2, "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1600}
    found = []
    for gen in ({"generator": "search", "gsrsearch": title, "gsrnamespace": 6, "gsrlimit": 25},
                {"generator": "geosearch", "ggscoord": f"{lat}|{lon}", "ggsradius": 10000, "ggsnamespace": 6, "ggslimit": 25}):
        try:
            j = requests.get(api, params={**base, **gen}, headers=UA, timeout=30).json()
        except (requests.RequestException, ValueError):
            continue
        for p in (j.get("query") or {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            md = ii.get("extmetadata") or {}
            lic = strip((md.get("LicenseShortName") or {}).get("value"))
            if ii.get("mime") != "image/jpeg" or ii.get("width", 0) < 1000 or not OK_LIC.match(lic) or re.search(r"\bN[CD]\b", lic):
                continue
            if any(f["name"] == p["title"] for f in found):
                continue
            artist = strip((md.get("Artist") or {}).get("value"))[:40] or "Wikimedia Commons"
            found.append({"name": p["title"], "url": ii.get("thumburl") or ii["url"],
                          "desc": strip((md.get("ImageDescription") or {}).get("value"))[:160] or p["title"][5:-4],
                          "credit": artist if lic.lower().startswith(("public", "pd")) else f"{artist}, {lic}"})
    return found[:n]


def download(photos, slug, idx):
    d = os.path.join(HERE, "photos", slug); os.makedirs(d, exist_ok=True)
    for i in sorted(idx):
        ph = photos[i]
        p = os.path.join(d, f"p{i}.jpg")
        if not os.path.exists(p):
            for a in range(3):
                r = requests.get(ph["url"], headers=UA, timeout=60)
                if r.status_code == 200:
                    open(p, "wb").write(r.content); break
                time.sleep(5 * (a + 1))
        ph["file"] = f"photos/{slug}/p{i}.jpg"
    json.dump([photos[i] for i in sorted(idx)], open(os.path.join(d, "credits.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- scenar
RULES = """Written for the ear (a voice reads it):
- Numbers as people say them: "about seventy kilometers", "two hundred fourteen million years ago", "almost a kilometer high". No decimals, no symbols or unit signs (no km, m, %, ³, ~), no brackets, no em dashes. Plain ASCII quotes and hyphens.

Facts:
- Use ONLY facts written in the article. Every number, date, name and claim must be in the article. No guessing, no rounding up to sound bigger.
- Never invent a myth, rumor or what "some people" say, think or wonder. If the article has no myth, use a question instead.
- No comparisons or analogies of your own ("enough to flood a city", "as big as a country"). The only allowed comparison is the computed scale fact in the user message.
- Do not describe colors (blue, green, white...) unless the article states that color. Satellite colors often look different from what you expect.
- No decorative adjectives the article does not support (crystal, pristine, glowing, eerie, ancient, massive, hidden). Plain words are better."""      # spolocne pre v1 aj v2

SYSTEM = """You write narration for a 30-35 second vertical video about a place seen on a satellite map.
A cute satellite robot called Orbi narrates while the camera flies from a globe down to the place.
Viewers swipe away in the first seconds, so the most surprising fact comes early (beat 3), and only the cause stays open until beat 6.

Structure, exactly 9 beats, 80 to 95 words in total. Short spoken sentences (max 14 words), plain English:
1. Hook (rules below). Write 3 different hook candidates in "hooks"; beat 1 text is your best one.
2. The question the viewer is now asking, as a real question ("So what carves a lake into a perfect ring?"). Do not answer it yet.
3. The surprise: the most surprising fact in the article that is not the cause (a record, a famous visitor, what lives there, who uses it; a nickname only if the article gives one), said plainly right now. Copy it from the article; never invent a name.
4-5. What you see and how big it is. Use the computed scale fact here if one is given.
6-7. The real answer, step by step. This is the first time the cause is named.
8. The twist: one more true fact from the article you have not used, best about the place today (what is there now, who uses it, what changed).
9. The last beat (exact rule given in the user message).
- Never tease a later fact ("wait till you hear", "stay to the end", "you'll see", "one more surprise"): say the fact itself.
- One number per beat at most, and never the same number twice in the video (the screen already shows sizes).
- Do not repeat a sentence, name or nickname you already used.

Hook rules (beat 1):
- One spoken sentence, 14 words max. It must work with sound on and eyes off the screen.
- Name one concrete thing the viewer sees (ring, island, crater, color, shape) in the first 6 words.
- Add tension with a specific number from the article (size, age) or an impossibility. Never a vague adjective.
- Never give away the answer or cause in the hook or the title (no "meteor", "volcano", "erosion" there). It is revealed in beats 5-7; the hook only makes people want it.
- Banned: "something strange", "weird", "mysterious", "you won't believe", "secret", "scientists are baffled", "Did you know", "Today we", any claim not in the article.
- Never say the coordinate numbers (they are typed on screen). "Search [name] on a satellite map and look at [feature]" is fine only with a specific feature.
- Patterns: "This [shape] is [size] wide, and [process] shouldn't make [shape]." / "A [size] [object] hit [place], and the scar is still there." / "Why is this [place] a perfect [shape]?" / "This [feature] is [age] old, and you can still see it from space." / "[Ordinary setting], and in the middle, [unexpected thing]."
- Each candidate has a "title": 2 to 4 words, ALL CAPS, max 22 characters, shown big from second 0. It shows the hook's own number in digits plus a plain noun, so screen and voice say the same thing (hook "A perfect ring seventy kilometers wide..." -> title "70 KM RING"; "PH ABOVE 12", "8 KM DEEP"). Never a different number than the hook, never the cause (IMPACT, METEOR, VOLCANO...), never invented, clipped or poetic words ("SKY PAINT", "ALKA RIFT", "COSMIC GAZE"). Digits are fine in the title only.
- A size in the hook is the size of the main feature (feature_km), the same number the ruler shows later. Do not give the lake, the rim and the crater three different sizes.

Example of the tone (a different place):
1 "This giant eye in the Sahara is forty kilometers wide, and no one built it."
2 "So what draws perfect rings into a desert?"
3 "Astronauts use it as a landmark, one of the few things they can spot."
4 "From orbit, ring sits inside ring, like a target."
5 "Paris would fit inside it."
6 "About a hundred million years ago, molten rock pushed the ground into a dome."
7 "Then wind and rain wore it down until only these rings were left."
8 "Today, nomads walk across the rings without even noticing them."
9 "Next target: a crater that has been burning for decades. Follow for the next scan. Orbi out."

""" + RULES + """

Visual cues (each "on" is ONE word copied exactly from that beat's text, where the cue appears):
- shot per beat: "feature" (whole place fills the screen), "close" (zoomed in on detail), "wide" (zoomed out to see the surroundings), "space" (far away, only for the last beat).
- overlay (at most one per beat, none in beat 1 or beat 9, use 4 or 5 in total so something new appears every few seconds; labels in plain words with a noun, never a bare number, no abbreviations like MYA or KM2):
  {"type":"ruler","on":word,"label":"40 KM"} for the size (label must match feature_km),
  {"type":"highlight","on":word} spotlights the outline of the place (good when you name its shape),
  {"type":"scale","on":word} draws the city from the scale fact on top, at the same scale ("on" = the city's first word; required when a scale fact is given),
  {"type":"rings","on":word} only if the place is round,
  {"type":"tag","on":word,"label":"SHORT WORDS"} to pin a named part,
  {"type":"stamp","on":word,"label":"SHORT DATE OR FACT"} for the key date or record.
  Tag and stamp labels show the fact itself, 2-4 words taken from that beat's text ("EYE OF QUEBEC", "214 MILLION YEARS AGO", "PH ABOVE 12"), never a category word (NICKNAME, NAME, IMPACT, FACT, DATE, RECORD, VOLUME, SIZE, AGE).
- No filler that only comments on the fact ("a name that fits perfectly", "which is amazing", "truly remarkable"). End each beat on the fact.
- react (2 or 3 in the whole video, the robot's face reacts): {"expr":"surprised" or "happy","on":word}. Surprised on the most shocking fact, happy on the beat 3 surprise or the last beat.
- photo (use 1 or 2 if the list has photos that clearly show this place, never in beat 1 or the last beat): {"index":N,"label":"SHORT CAPTION","on":word} using a photo from the list.

Return JSON: {"title": str, "feature_km": number (size of the main thing visible from above, in km, from the article),
"hooks": [{"text": str, "title": str}, {"text": str, "title": str}, {"text": str, "title": str}],
"beats": [{"text": str, "shot": str, "overlay": obj or null, "react": obj or null, "photo": obj or null}],
"description": str (2 sentences, facts only), "hashtags": [5 strings starting with #]}"""

# v2 (od #011): hak od 0. sekundy, kamera nikdy nestoji, dokaz (foto) v 3.-6. s, 7 beatov, ziadne rozlucenie, video sa zacykli
V2_WORDS = (62, 92)           # 10 rucnych dielov #011-#020 ma 72-89 slov (26-32 s reci)
V2_BEAT_MAX = 16              # najdlhsi beat v referenciach ma 16 slov
V2_CHARS = 500                # referencie maju 395-476 znakov; 473 znakov = 32,3 s videa, Pripjat s 570 hovorenymi = 39 s
SYSTEM_V2 = """You write narration for a 30 second vertical video about a place seen on a satellite map.
The camera lands on the place at second 0 and keeps moving all the time. A voice reads every word.
Viewers leave in seconds 4-8 if nothing proves the first sentence, and they leave at any goodbye. So the video starts with the claim, proves it at once, and ends on the strongest fact (it then loops back to the start).

Structure, exactly 7 beats, 64 to 78 short words in total (about 420 characters, never more than 460), one or two short spoken sentences per beat (max 16 words per beat), plain English:
1. Hook, spoken from second 0. Start by naming what the viewer sees right now ("This island...", "This lake...", "These three shapes...", "Thousands of people once lived on this tiny island.") and add the most surprising true fact: a number, an age or an impossibility. Write 3 different candidates in "hooks"; beat 1 text is your best one.
2. Proof: name the place and where it is, and back up the hook in plain words ("It is Surtsey, and it burst out of the sea off Iceland."). A photo of the place appears on this beat: give it a photo cue if the list has a photo that clearly shows the place.
3-6. One new concrete fact per beat, each about something the camera can show while it flies over the place: its size, its depth, one part of it, what happens there, who goes there, what changed.
7. The strongest fact you have left, best about the place today or a twist. This is the last line of the video: no goodbye, no summary, no question.
- No questions anywhere in the narration and no question marks. No intro ("Today", "Let's", "Welcome", "Did you know").
- Never sign off: no "follow", "subscribe", "next target", "next scan", "Orbi out", "see you".
- Never tease a later fact ("wait till you hear", "stay to the end", "you'll see"): say the fact itself.
- At most two numbers per beat, and never the same number twice in the video.
- Every beat is a different kind of fact. Never two beats about the same thing (two production records, two sizes).
- Beat 7 is not an award, a listing or a founding date: it is what happened to the place or what it is like today.
- Write every number and year in words ("nineteen seventy", "forty-nine thousand"), never in digits. Name at most two years in the whole video.
- Do not repeat a sentence, name or nickname you already used.

Hook rules (beat 1):
- One spoken sentence, 14 words max. It must work with sound on and eyes off the screen.
- The hook is a checkable fact (a number, a date, a record, a ban), never a mood ("lie silent", "frozen in time").
- Name the thing on screen (island, lake, ring, hole, shapes, color) in the first 6 words, with "this" or "these".
- Banned: "something strange", "weird", "mysterious", "you won't believe", "secret", "scientists are baffled", "Did you know", "Today we", any claim not in the article.
- Never say the coordinate numbers (they are typed on screen).
- Each candidate has a "title": 2 to 4 words, ALL CAPS, max 22 characters, shown big from second 0 ("BORN IN 1963", "BOILING RAINBOW", "MAN-MADE ISLAND", "525 M DEEP HOLE"). Plain words from the hook; if it has a number, it is the hook's own number in digits. Never invented or poetic words, never the cause (IMPACT, METEOR, VOLCANO).
- A size in the hook is the size of the main feature (feature_km), the same number the ruler shows later.

Example (a different place, 72 words):
1 "This island did not exist before nineteen sixty-three."
2 "It burst out of the sea off Iceland in a single eruption."
3 "The eruption began one hundred thirty meters under water."
4 "And it kept going for three and a half years."
5 "Today, landing here is banned. Only a few scientists may visit."
6 "They watch life arrive on brand new land."
7 "But the sea is winning. The island has already lost about half its size."

""" + RULES.replace(" If the article has no myth, use a question instead.", "").replace(
    " The only allowed comparison is the computed scale fact in the user message.", "") + """

Visual cues (each "on" is ONE word copied exactly from that beat's text, where the cue appears):
- beat 1 overlay: {"type":"rings","on":word} on the word that names what the viewer sees (the code draws a ring around the place).
- overlays in beats 3-7 (at most one per beat, use 1 to 3, only these three types; labels in plain words with a noun, never a bare number, no abbreviations like MYA or KM2):
  {"type":"ruler","on":word,"label":"40 KM"} for the size (label must match feature_km),
  {"type":"stamp","on":word,"label":"SHORT DATE OR FACT"} for the key date, record or a named part ("NO LANDING", "EMPTY SINCE 1974", "2016: NEW BRIDGE"),
  {"type":"highlight","on":word} spotlights the outline of the place.
  Tag and stamp labels show the fact itself, 2-4 words taken from that beat's text, never a category word (NICKNAME, NAME, IMPACT, FACT, DATE, RECORD, SIZE, AGE).
- No filler that only comments on the fact ("which is amazing", "truly remarkable"). End each beat on the fact.
- react (1 or 2 in the whole video, the robot's face reacts): {"expr":"surprised" or "happy","on":word} on the most shocking fact.
- photo (beat 2, plus at most one more in beats 3-6, never in beat 1 or beat 7): {"index":N,"label":"SHORT CAPTION","on":word} using a photo from the list.
- "question": ONE short question for the viewer (would they go there, live there, dare it) shown on the last frame, split over exactly 2 lines in ALL CAPS, max 16 characters each, the second ending with "?" (["WOULD YOU", "LAND HERE?"], ["HOW DID THEY", "BUILD THIS?"]).

Return JSON: {"title": str, "feature_km": number (size of the main thing visible from above, in km, from the article),
"hooks": [{"text": str, "title": str}, {"text": str, "title": str}, {"text": str, "title": str}],
"beats": [{"text": str, "overlay": obj or null, "react": obj or null, "photo": obj or null}],
"question": [str, str],
"description": str (2 sentences: the hook sentence, then one more fact with the place name and country; digits allowed here),
"hashtags": [5 strings starting with #, the place, the country, the topic]}"""

CHECK = """You are a fact checker for a short narrated video about a place seen on a satellite map.
Flag a sentence only if it states a FACT that is false or not in the article:
- a number, size, height, depth, date or age that differs from the article (rounding with "about"/"almost" is fine),
- a name, nickname, cause, record or event the article does not give,
- anything about what people or scientists say, call it, think, wonder or believe, unless the article says it,
- any comparison or analogy ("enough to flood a city", "bigger than...") that is not in the article, except the computed scale fact given below,
- a color the article does not state, or a describing word (crystal, glowing, pristine, forever) the article does not support,
- beat 3 only teases a fact ("wait till you hear what locals call it") instead of saying it.
Never flag: describing shapes on the satellite image ("looks like an eye", "a ring", "from space"), telling viewers to type coordinates,
questions, simple plain-language wording of what the article says, the computed scale fact,
the closing "Follow for the next scan. Orbi out." line. The "Next target" line is about a different place: check it only against the next-topic text.
Return JSON: {"problems": [str]}, one short line per false or invented fact. Empty list if there are none."""

JUDGE = """You pick the strongest opening line (hook) for a 30 second vertical video about a place seen on a satellite map.
Score each candidate 0-2 on each point:
1. Picture: names a concrete visual in the first 6 words.
2. Tension: a number, scale or impossibility that makes you ask a question, WITHOUT revealing the cause or answer (hook or title naming the cause scores 0 here).
3. Speed and sound: 14 words or fewer, clear without seeing the screen, no hype phrases, no coordinate numbers.
4. Truth and fit: every claim is in the article; the title is a plain fact with the hook's own number (not poetic or invented words, not the cause).
Highest total wins; a tie goes to the shorter one.
Return JSON: {"scores": [int per candidate], "best": index of the winner (0-based)}"""

BANNED = re.compile(r"something (strange|weird)|\bweird\b|mysterious|won't believe|\bsecret\b|baffled|did you know|today we", re.I)
CAUSE = re.compile(r"impact|meteor|asteroid|comet|volcan|erosion|erupt|eroded|glacier|collapse|tectonic", re.I)
METEOR = re.compile(r"\b(meteor\w*|asteroid\w*|comet\w*|impact\w*|from space)\b", re.I)
HIT = re.compile(r"\b(struck|strikes|hit|hits|slammed|smashed|crashed|landed|impact\w*)\b", re.I)
# stylove pravidla: model ich pri oprave casto pokazi inde -> od 4. pokusu nebrzdia (fakty a struktura ano)
TEASE = re.compile(r"\bwait (till|until|to)\b|\bstay (till|until|to the end)\b|\byou'll (soon )?(see|hear|find)\b"
                   r"|one more surprise|\bfind out\b|keep watching", re.I)
SOFT = re.compile(r"never repeat a number|one number per beat|numbers per beat|need \d+-\d+ words|react cues|not a bare number"
                  r"|longer than \d+ words|title '.*' needs a true number")
SIGNOFF_RX = re.compile(r"\bfollow\b|next target|next scan|orbi out|subscribe|see you|\bstay tuned\b", re.I)   # v2: ziadne rozlucenie


def fine(errs, att):
    return not errs or (att >= 3 and all(SOFT.search(e) for e in errs))


def numbers(text):
    """cisla napisane slovami ako fraza: 'two hundred fourteen million' (samotne 'one'/'a' nie)."""
    out, cur = [], []
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in NUMW or (cur and w in ("and", "one")):
            cur.append(w)
        elif cur:
            out.append(cur); cur = []
    out += [cur] if cur else []
    return [" ".join(c[:-1] if c[-1] == "and" else c) for c in out]


UNITS = dict(zip("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
                 "seventeen eighteen nineteen".split(), range(20)))
UNITS.update(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
MULT = {"hundred": 100, "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9}


def digits(label):
    """'ONE HUNDRED THIRTY EIGHT KM3' -> '138 KM3' (stitok je kratky, slova by sa zrezali)."""
    out, tot, cur, num = [], 0, 0, False
    for w in re.split(r"[\s-]+", label.strip()) + [""]:
        lw = w.lower()
        if lw in UNITS or lw in MULT or (num and lw == "and"):
            num = True
            if lw in UNITS:
                cur += UNITS[lw]
            elif lw == "hundred":
                cur = (cur or 1) * 100
            elif lw in MULT:
                tot, cur = tot + (cur or 1) * MULT[lw], 0
            continue
        if num:
            n = tot + cur
            out.append(f"{n // 10 ** 9} BILLION" if n >= 10 ** 9 and n % 10 ** 9 == 0 else
                       f"{n // 10 ** 6} MILLION" if n >= 10 ** 6 and n % 10 ** 6 == 0 else f"{n:,}")
            tot, cur, num = 0, 0, False
        if w:
            out.append(w)
    return " ".join(out)


def years(text):
    """roky povedane po anglicky: 'nineteen sixty-three' -> {'1963'}, 'twenty twenty five' -> {'2025'}"""
    ws, out = re.findall(r"[a-z]+", text.lower()), set()
    for k, w in enumerate(ws[:-1]):
        if 11 <= UNITS.get(w, 0) <= 20:
            v = UNITS.get(ws[k + 1], -1)
            if 20 <= v <= 90 and v % 10 == 0 and k + 2 < len(ws) and 1 <= UNITS.get(ws[k + 2], 0) <= 9:
                v += UNITS[ws[k + 2]]
            if 10 <= v <= 99:
                out.add(str(UNITS[w] * 100 + v))
    return out


def v_numbers(bs, ctx, most=1):
    """cisla (max `most` na beat, nikdy dvakrat) a farby, ktore clanok nepotvrdzuje"""
    errs, seen = [], {}
    for i, b in enumerate(bs):
        ns = numbers(b.get("text", ""))
        if len(ns) > most:
            errs.append(f"beat {i + 1} has {len(ns)} numbers ({', '.join(ns)}): " +
                        ("one number per beat at most" if most == 1 else f"at most {most} numbers per beat"))
        for n in ns:
            if n in seen:
                errs.append(f"the number '{n}' is used in beat {seen[n]} and beat {i + 1}: never repeat a number")
            seen.setdefault(n, i + 1)
        for c in set(m.lower() for m in COLORW.findall(b.get("text", ""))):
            if not re.search(rf"\b{c}", ctx["article"], re.I):
                errs.append(f"beat {i + 1} says '{c}', but the article never states that color")
    return errs


def v_tease(bs):
    return [f"beat {i + 1} teases a later fact ('{TEASE.search(b['text']).group(0)}'): say the fact itself"
            for i, b in enumerate(bs) if TEASE.search(b.get("text", ""))]


def v_ear(bs):
    errs = []
    for i, b in enumerate(bs):
        bad = re.findall(r"[0-9]+[.,][0-9]+|[%~()²³]|\bkm\b|[0-9] ?m\b", b.get("text", ""))
        if bad:
            errs.append(f"beat {i + 1} is not written for the ear ({', '.join(bad)}): spell numbers and units as words")
    return errs


def v_labels(bs, v2=False):
    errs = []
    for i, b in enumerate(bs):
        o = b.get("overlay") or {}
        if o.get("type") in ("tag", "stamp") and not re.search(r"[A-Za-z]{2}", digits(str(o.get("label", "")))):
            errs.append(f"beat {i + 1} {o['type']} label '{o.get('label')}' needs words, not a bare number")
        elif o.get("type") in ("tag", "stamp"):
            lab = digits(str(o.get("label", ""))).lower().split()
            said = set(digits(b.get("text", "")).lower().replace(",", " ").replace(".", " ").split())
            said |= years(b.get("text", "")) if v2 else set()       # v2: "EMPTY SINCE 1974" k "nineteen seventy four"
            if len(lab) < 2 or not set(lab) & said:
                errs.append(f"beat {i + 1} {o['type']} label '{o.get('label')}' must be the fact itself in 2-4 words "
                            f"from the beat text (like 'EYE OF QUEBEC'), not a category word")
    return errs


def v_hooks(s, need_digits=True):
    errs = []
    hooks = [h for h in s.get("hooks") or [] if isinstance(h, dict)]
    if len(hooks) < 2:
        errs.append("give 3 hook candidates in \"hooks\"")
    for i, h in enumerate(hooks):
        txt, ttl = str(h.get("text", "")), str(h.get("title", ""))
        if len(txt.split()) > 15:
            errs.append(f"hook {i + 1} is longer than 14 words")
        if BANNED.search(txt) or re.search(r"[0-9]", txt):
            errs.append(f"hook {i + 1} uses a banned phrase or digits")
        if not 2 <= len(ttl.split()) <= 4 or len(ttl) > 22:
            errs.append(f"hook {i + 1} title must be 2-4 words, max 22 characters")
        if need_digits and not re.search(r"[0-9]", ttl):         # "SKY PAINT", "ALKA RIFT" nic nehovoria
            errs.append(f"hook {i + 1} title '{ttl}' needs a true number in digits from the article plus a plain noun (like \"214 MILLION YEARS\")")
        if not need_digits and not re.search(r"\b(this|these)\b", txt, re.I):     # v2: hak pomenuje, co divak vidi
            errs.append(f"hook {i + 1} must name what the viewer sees, with 'this' or 'these' (\"This island...\")")
        spoken = digits(re.sub(r"[^\w\s-]", " ", txt)).replace(",", "")         # "twelve." -> "12"
        said = set(re.findall(r"\d+", spoken)) | (set() if need_digits else years(txt))   # v2: "BORN IN 1963"
        if re.search(r"[0-9]", ttl) and not set(re.findall(r"\d+", ttl)) & said:
            errs.append(f"hook {i + 1} title '{ttl}' must show the hook's own number (screen and voice say the same)")
        if CAUSE.search(ttl):
            errs.append(f"hook {i + 1} title '{ttl}' gives away the cause")
        hk = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?) ?KILOMET", spoken.upper())]
        if hk and s.get("feature_km") and not any(abs(n / float(s["feature_km"]) - 1) <= 0.15 for n in hk):
            errs.append(f"hook {i + 1} says {hk[0]:g} km but feature_km (the ruler) is {s['feature_km']}: use one size")
    return errs


def v_km_cues(s, bs, photos):
    errs = []
    try:
        if float(s.get("feature_km", 0)) <= 0:
            errs.append("feature_km must be > 0")
    except (TypeError, ValueError):
        errs.append("feature_km must be a number")
    for i, b in enumerate(bs):
        toks = [re.sub(r"[^a-z0-9']", "", t.lower()) for t in b.get("text", "").split()]
        for k in ("overlay", "react", "photo"):
            o = b.get(k)
            if o and re.sub(r"[^a-z0-9']", "", str(o.get("on", "")).lower()) not in toks:
                errs.append(f"beat {i + 1} {k}.on '{o.get('on')}' is not a word in that beat")
        ph = b.get("photo")
        if ph and not (isinstance(ph.get("index"), int) and 0 <= ph["index"] < len(photos)):
            errs.append(f"beat {i + 1} photo index out of range")
    return errs


def validate(s, photos, ctx):
    errs = []
    bs = s.get("beats") or []
    if len(bs) != 9:
        errs.append(f"need exactly 9 beats, got {len(bs)}")
    errs += v_numbers(bs[:-1], ctx)
    if len(bs) > 2 and "?" not in bs[1].get("text", ""):
        errs.append("beat 2 must be the viewer's question, ending with '?'")
    if ctx["scale"] and not any((b.get("overlay") or {}).get("type") == "scale" for b in bs):
        errs.append(f"add this computed scale fact in beat 4 or 5: \"{ctx['scale']['fact']}.\" with a scale overlay on the word '{ctx['scale']['on']}'")
    words = sum(len(b.get("text", "").split()) for b in bs)
    if not 75 <= words <= 105:
        errs.append(f"need 80-95 words, got {words}")
    errs += v_tease(bs[:-1]) + v_ear(bs)
    if sum(1 for b in bs if b.get("react")) < 2:
        errs.append("use 2 or 3 react cues")
    if sum(1 for b in bs[1:-1] if b.get("overlay")) < 4:
        errs.append("use 4 or 5 overlays, none in beat 1 or beat 9")
    errs += v_labels(bs)
    if photos and not any(b.get("photo") for b in bs):
        errs.append("use at least 1 photo from the list")
    errs += v_hooks(s)
    last = bs[-1].get("text", "").strip() if bs else ""
    if ctx["next"]:
        if not (last.startswith("Next target:") and last.endswith(SIGNOFF) and len(last.split()) <= 22):
            errs.append(f"beat 9 must be 'Next target: <short tease>. {SIGNOFF}'")
    elif last != SIGNOFF:
        errs.append(f"beat 9 must be exactly: {SIGNOFF}")
    return errs + v_km_cues(s, bs, photos)


def validate_v2(s, photos, ctx):
    """v2: 7 beatov, hak od 0. s, dokaz v beate 2, ziadna otazka ani rozlucenie, posledny beat = najsilnejsi fakt"""
    errs = []
    bs = s.get("beats") or []
    if len(bs) != 7:
        errs.append(f"need exactly 7 beats, got {len(bs)}")
    errs += v_numbers(bs, ctx, 2)
    words = sum(len(b.get("text", "").split()) for b in bs)
    if not V2_WORDS[0] <= words <= V2_WORDS[1]:
        errs.append(f"need 64-78 words, got {words}")
    chars = len(" ".join(b.get("text", "") for b in bs))
    if chars > V2_CHARS:
        errs.append(f"the narration takes too long to say ({chars} characters, the limit is {V2_CHARS}): cut "
                    f"{-(-(chars - V2_CHARS + 50) // 6)} words: drop one side detail from the longest beats, keep 7 beats, "
                    f"at most 11 words per beat")
    for i, b in enumerate(bs):
        t = b.get("text", "")
        if re.search(r"\d", t):
            errs.append(f"beat {i + 1} has digits ({', '.join(re.findall(r'[0-9][0-9,.]*', t))}): write every number in words")
        if len(t.split()) > V2_BEAT_MAX:
            errs.append(f"beat {i + 1} is longer than {V2_BEAT_MAX} words")
        if "?" in t:
            errs.append(f"beat {i + 1} is a question: no questions in the narration, state the fact")
        if SIGNOFF_RX.search(t):
            errs.append(f"beat {i + 1} signs off ('{SIGNOFF_RX.search(t).group(0)}'): no goodbye and no 'Next target', "
                        f"the last beat is the strongest fact")
    if bs and (len(bs[0].get("text", "").split()) > 15 or not re.search(r"\b(this|these)\b", bs[0].get("text", ""), re.I)):
        errs.append("beat 1 must be the hook: 14 words max, naming what the viewer sees with 'this' or 'these'")
    errs += v_tease(bs) + v_ear(bs)
    if not 1 <= sum(1 for b in bs if b.get("react")) <= 2:
        errs.append("use 1 or 2 react cues")
    if sum(1 for b in bs[2:] if (b.get("overlay") or {}).get("type") in ("ruler", "tag", "stamp", "highlight")) < 1:
        errs.append("use 1 to 3 overlays (ruler, tag, stamp, highlight) in beats 3-7")
    errs += v_labels(bs, v2=True)
    if photos and len(bs) > 1 and not bs[1].get("photo"):
        errs.append("beat 2 needs a photo cue: the photo of the place is the proof of the hook")
    if bs and (bs[0].get("photo") or bs[-1].get("photo")):
        errs.append("no photo in beat 1 or beat 7")
    errs += v_hooks(s, need_digits=False)
    q = s.get("question")
    if not (isinstance(q, list) and len(q) == 2 and all(isinstance(x, str) and 0 < len(x) <= 16 and x == x.upper() for x in q)
            and q[1].strip().endswith("?") and "?" not in q[0]):
        errs.append('"question" must be 2 ALL-CAPS lines, max 16 characters each: ONE question split over the two lines, only '
                    'the second line ends with "?" (["WOULD YOU", "LAND HERE?"])')
    return errs + v_km_cues(s, bs, photos)


def prompt(fact, photos, scale, nxt, km=None, v2=False):
    """zadanie pre model (aj pre zasobu scenarov orbit/bank.py): (user, side, ctx pre validate). v2: bez mesta a "Next target"."""
    if v2:
        scale = nxt = None
    ctx = {"article": fact["extract"], "scale": scale, "next": nxt}
    plist = "\n".join(f"{i}: {p['desc']}" for i, p in enumerate(photos)) or "(no photos)"
    extra = (f"Size of the main feature from the article: {km:g} km (use it as feature_km).\n" if km else "") + (f"Computed scale fact (true, use it in beat 4 or 5 with a scale overlay on the word '{scale['on']}'): {scale['fact']}."
             if scale else "Computed scale fact: none (do not use a scale overlay).")
    extra += (f"\nBeat 9 must be exactly: \"Next target: <tease of at most 10 words, one true fact from the next-topic text, "
              f"without naming the place>. {SIGNOFF}\"\nNext topic: {nxt['title']}. {nxt['extract'][:500]}"
              if nxt else f"\nBeat 9 must be exactly: \"{SIGNOFF}\"") if not v2 else ""
    user = (f"Place: {fact['title']}\nCoordinates: {fact['lat']:.4f}, {fact['lon']:.4f}\n{extra}\n\nPhotos:\n{plist}"
            f"\n\nArticle:\n{fact['extract']}")
    side = (f"\n\nComputed scale fact (true): {scale['fact']}." if scale else "") + (
        f"\n\nNext-topic text (only for the 'Next target' line): {nxt['extract'][:500]}" if nxt else "")
    return user, side, ctx


def more_text(fact, n=4500):
    """v2 potrebuje 7 roznych faktov: ulozeny vytah (~1200 znakov) nestaci -> cely text clanku z Wikipedie, skrateny na vety."""
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
            "action": "query", "titles": fact["title"], "redirects": 1, "prop": "extracts", "explaintext": 1,
            "exsectionformat": "plain", "format": "json", "formatversion": 2})
        t = re.sub(r"\n{2,}", "\n", (r.json()["query"]["pages"][0].get("extract") or "")).strip()
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        log(f"   dlhsi text clanku zlyhal ({e}), ostava vytah")
        return fact["extract"]
    if len(t) <= len(fact["extract"]):
        return fact["extract"]
    t = t[:n]
    return t[:max(t.rfind(". "), t.rfind(".\n")) + 1] or t


def year_words(y):
    """1970 -> 'nineteen seventy', 2005 -> 'two thousand five', 1905 -> 'nineteen oh five' (hlas cita slova, nie cislice)"""
    one = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
    ten = dict(zip(range(20, 100, 10), "twenty thirty forty fifty sixty seventy eighty ninety".split()))
    two = lambda n: one[n] if n < 20 else ten[n - n % 10] + ("-" + one[n % 10] if n % 10 else "")
    h, r = divmod(y, 100)
    if y % 1000 == 0:
        return one[y // 1000] + " thousand"
    if 2000 < y < 2010:
        return "two thousand " + one[r]
    if r == 0:
        return two(h) + " hundred"
    return two(h) + (" oh " + one[r] if r < 10 else " " + two(r))


YEAR_RX = re.compile(r"(?<![\d,.])(1[0-9]{3}|20[0-9]{2})(?![\d,]|\.\d)")


def proper(text, src):
    """otazka je v scenari VELKYMI: v popise vratit vlastnym menam velke pismeno ('Will you enter Pripyat?')"""
    low = set(re.findall(r"\b[a-z]{3,}\b", src))
    names = {c.lower(): c for c in re.findall(r"\b[A-Z][a-z]{2,}\b", src) if c.lower() not in low}
    return text[:1] + re.sub(r"[A-Za-z]+", lambda m: names.get(m.group(0).lower(), m.group(0)), text[1:])


_ONE = "one|two|three|four|five|six|seven|eight|nine"
_TEEN = "ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
_TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
YEARW_RX = re.compile(rf"\b({_TEEN}|twenty)[ -](?:oh[ -]({_ONE})|({_TENS})(?:[ -]({_ONE}))?|({_TEEN}))\b", re.I)
NUM_RX = r"\d[\d,]*(?: (?:MILLION|BILLION))?"
_NW = f"{_ONE}|{_TEEN}|{_TENS}|zero|hundred|thousand|million|billion"
NUMRUN_RX = re.compile(rf"\b(?:{_NW})(?:[ -](?:and[ -])?(?:{_NW}))*\b", re.I)


def num_label(t):
    """slova -> cislice: 'nineteen sixty-six' -> 1966, 'one thousand nine hundred acres' -> '1,900 acres', 'FOUR KM' -> '4 KM'"""
    u = lambda w: UNITS[w.lower()] if w else 0
    t = YEARW_RX.sub(lambda m: str(u(m.group(1)) * 100 + u(m.group(2)) + u(m.group(3)) + u(m.group(4)) + u(m.group(5))), t)
    return NUMRUN_RX.sub(lambda m: m.group(0) if m.group(0).lower() == "one" else digits(m.group(0)), t)   # "ONE FAMILY" ostava


def stamp_fix(label, text):
    """stitok v2 ukaze to iste cislo, co povie hlas, a k cislu podstatne meno; zlomky ('THREE QUARTERS') ostavaju slovami"""
    if re.search(r"quarter|half|third", label, re.I):
        return label
    lab, bt = num_label(label).upper(), num_label(text)
    ln, bn = re.findall(NUM_RX, lab), re.findall(NUM_RX, bt.upper())
    bare = lambda x: x.replace(",", "")
    if not ln or not bn or (all(bare(x) in map(bare, bn) for x in ln) and re.search(r"[A-Z]{2}", re.sub(NUM_RX, "", lab))):
        return lab
    bt = bt.upper()
    n0 = next((x for x in bn if bare(x).endswith(bare(ln[0]))), bn[0])    # hlas: 1,900; stitok: 900 -> plati hlas
    out = [n0]
    for w in re.findall(r"[A-Za-z]+", bt[bt.index(n0) + len(n0):])[:3]:
        if w.lower() in ("of", "in", "the", "a", "an", "and", "to", "on", "at", "by", "from", "than"):
            break
        out.append(w)
    return " ".join(out[:3]).upper()


def repair_v2(s):
    """v2: chyby v napovediach obrazu opravi kod (model na ne palil pokusy): zly stitok prec, reakcie 1-2, aspon 1 overlay.
    Roky cislicami -> slovami (hlas ich cita dlho, dlzku treba pocitat zo slov). "tag" -> "stamp": kod nevie, kde na mape
    pomenovana cast lezi, stitok by visel v strede utvaru (Pripjat: UNOPENED WHEEL nad lesom)."""
    bs = s["beats"]
    for b in bs:
        if YEAR_RX.search(b.get("text", "")):
            b["text"] = YEAR_RX.sub(lambda m: year_words(int(m.group(1))), b["text"])
        for k in ("overlay", "react", "photo"):
            c = b.get(k)
            if isinstance(c, dict) and YEAR_RX.fullmatch(str(c.get("on", "")).strip(".,")):
                c["on"] = year_words(int(str(c["on"]).strip(".,"))).split()[0]
        if (b.get("overlay") or {}).get("type") == "tag":
            b["overlay"]["type"] = "stamp"
        if (b.get("overlay") or {}).get("type") == "stamp" and b["overlay"].get("label"):
            b["overlay"]["label"] = stamp_fix(str(b["overlay"]["label"]), b.get("text", ""))
    for e in v_labels(bs, v2=True):
        m = re.match(r"beat (\d+) ", e)
        if m:
            bs[int(m.group(1)) - 1]["overlay"] = None
    rs = [b for b in bs if b.get("react")]
    for b in rs[2:]:
        b["react"] = None
    if not rs and len(bs) > 3:
        b = next((x for x in bs[2:-1] if numbers(x.get("text", ""))), bs[3])
        b["react"] = {"expr": "surprised", "on": max(b["text"].split(), key=len).strip(".,!?;:'\"")}
    if len(bs) > 2 and not any((b.get("overlay") or {}).get("type") in ("ruler", "tag", "stamp", "highlight") for b in bs[2:]):
        bs[2]["overlay"] = {"type": "highlight", "on": max(bs[2]["text"].split(), key=len).strip(".,!?;:'\"")}


def write(fact, photos, scale, nxt, km=None, v2=False):
    user, side, ctx = prompt(fact, photos, scale, nxt, km, v2)
    validate_ = validate_v2 if v2 else validate
    msgs = [{"role": "system", "content": SYSTEM_V2 if v2 else SYSTEM}, {"role": "user", "content": user}]
    for att in range(10):
        s = llm(msgs)
        s["beats"] = [b for b in s.get("beats") or [] if isinstance(b, dict)]
        for b in s["beats"]:                     # typograficke znaky -> ASCII (TTS ich cita zle)
            b["text"] = re.sub(r"[‐-―]", "-", b.get("text", "")).translate(
                {0x2018: "'", 0x2019: "'", 0x201c: '"', 0x201d: '"', 0x2026: "..."}).strip()
            toks = [re.sub(r"[^a-z0-9']", "", t.lower()) for t in b["text"].split()]
            for k in ("overlay", "react", "photo"):          # "on" s viac slovami -> prve slovo, ktore v zabere je
                o = b.get(k)
                if isinstance(o, dict) and len(str(o.get("on", "")).split()) > 1:
                    hit = [w for w in str(o["on"]).split() if re.sub(r"[^a-z0-9']", "", w.lower()) in toks]
                    if hit:
                        o["on"] = hit[0]
                if isinstance(o, dict) and re.sub(r"[^a-z0-9']", "", str(o.get("on", "")).lower()) not in toks and toks:
                    o["on"] = max(b["text"].split(), key=len).strip(".,!?;:'\"")   # cue na slove mimo vety -> najdlhsie slovo
        for h in s.get("hooks") or []:                       # titulok s inym cislom nez hlas -> cislo z hlasu (model to nevie opravit)
            if isinstance(h, dict):
                sp = re.findall(r"\d+", digits(re.sub(r"[^\w\s-]", " ", str(h.get("text", "")))).replace(",", ""))
                tt = str(h.get("title", "")); tn = re.findall(r"\d+", tt)
                tk = set(tn) | {str(int(x) * 1000) for x in re.findall(r"(\d+)K(?![A-Z])", tt)}   # "49K" = 49000
                if sp and tn and not tk & (set(sp) | (years(str(h.get("text", ""))) if v2 else set())):
                    log(f"   titulok {tt} -> cislo {sp[0]} z hooku: {h.get('text')}")
                    h["title"] = re.sub(re.escape(tn[0]) + r"K?(?![A-Z0-9])", sp[0], tt, count=1)
        if v2 and len(s["beats"]) >= 6:
            repair_v2(s)
        errs = validate_(s, photos, ctx)
        if len(s.get("beats") or []) < 6:                    # rozbity navrh: zopakovat tu istu poziadavku (opravy ostanu)
            log(f"   pokus {att + 1}: rozbity navrh, znova: {json.dumps(s)[:300]}")
            continue
        if fine(errs, att):
            hooks = [h for h in s["hooks"] if isinstance(h, dict)]
            pick = llm([{"role": "system", "content": JUDGE},
                        {"role": "user", "content": f"Article:\n{fact['extract'][:2500]}\n\nCandidates:\n" + "\n".join(
                            f"{i}: \"{h['text']}\" / title: {h['title']}" for i, h in enumerate(hooks))}], temp=0.1)
            best = pick.get("best") if isinstance(pick.get("best"), int) and 0 <= pick["best"] < len(hooks) else 0
            sc = pick.get("scores") if isinstance(pick.get("scores"), list) and len(pick["scores"]) == len(hooks) else []
            order = [best] + sorted((i for i in range(len(hooks)) if i != best),
                                    key=lambda i: -(sc[i] if i < len(sc) and isinstance(sc[i], (int, float)) else 0))
            b0 = s["beats"][0]
            cues = {k: b0.get(k) for k in ("overlay", "react", "photo")}
            for best in order:                               # hook neprejde (cislo, fakt) -> dalsi kandidat, nie novy scenar
                b0["text"], s["hook_title"] = [re.sub(r"[‐-―]", "-", hooks[best][k]).translate(
                    {0x2018: "'", 0x2019: "'", 0x201c: '"', 0x201d: '"'}).strip() for k in ("text", "title")]
                toks = [re.sub(r"[^a-z0-9']", "", t.lower()) for t in b0["text"].split()]
                for k, o in cues.items():                    # cue na slove, ktore vo vitaznom hooku nie je, zahodit
                    b0[k] = o if o and re.sub(r"[^a-z0-9']", "", str(o.get("on", "")).lower()) in toks else None
                log(f"   hook {best + 1}/{len(hooks)} {sc}: {b0['text']} | {s['hook_title']}")
                errs = validate_(s, photos, ctx)             # hook moze zopakovat cislo z dalsich beatov
                if fine(errs, att):
                    narr = f"On-screen title: {s['hook_title']}\n" + "\n".join(f"Beat {i + 1}: {b['text']}" for i, b in enumerate(s["beats"]))
                    errs = llm([{"role": "system", "content": CHECK},
                                {"role": "user", "content": f"Article:\n{fact['extract']}{side}\n\nNarration:\n{narr}"}], temp=0.1).get("problems") or []
                    errs = [f"fact: {e}" for e in errs]
                    hk = b0["text"][:30].lower()
                    if not (errs and all(hk in e.lower() or "beat 1" in e.lower() or "title" in e.lower() for e in errs)):
                        break                                # chyby aj mimo hooku: opravi ich model
                log(f"   hook {best + 1} neprešiel: " + " | ".join(errs)[:200])
        if not errs:
            log(f"   scenar OK (pokus {att + 1})")
            if v2:
                s["v2"] = True                       # prerender (ORBIT_REBUILD) podla toho vyberie build
            return s
        log(f"   pokus {att + 1}: " + " | ".join(errs)[:400])
        msgs = msgs[:2] + [{"role": "assistant", "content": json.dumps(s)},   # len posledny navrh (Groq 8000 tok/min)
                           {"role": "user", "content": "Fix these problems and return the full JSON again:\n- " + "\n- ".join(errs) + (
                               "\nEvery problem starting with 'fact:' is a claim that is NOT written in the article. Do not rephrase "
                               "it: delete that claim and write a different fact that the article states."
                               if any(e.startswith("fact:") for e in errs) else "")}]
    sys.exit("scenar nepresiel kontrolou ani na 10. pokus")


# ---------------------------------------------------------------- dorovnanie suradnic
def dist_km(a, b, c, d):
    x = math.sin(math.radians(a)) * math.sin(math.radians(c)) + \
        math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.cos(math.radians(d - b))
    return 6371 * math.acos(max(-1.0, min(1.0, x)))


def locate_osm(title, lat, lon):
    """OpenStreetMap (Nominatim, bez kluca): stred obdlznika okolo obrysu utvaru. Tazisko býva mimo (prstence, ramena jazier).
    Berie len prirodne/vodne/historicke objekty do 150 km od suradnic z Wikipedie."""
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", headers=UA, timeout=30,
                         params={"q": title, "format": "jsonv2", "limit": 5}).json()
    except (requests.RequestException, ValueError):
        return lat, lon, False
    best = None
    for x in r:
        if x.get("category") in ("tourism", "amenity", "shop", "highway", "building", "office", "railway"):
            continue
        s, n, w, e = map(float, x["boundingbox"])
        cy, cx = (s + n) / 2, (w + e) / 2
        d = dist_km(lat, lon, cy, cx)
        if d < 150 and (best is None or d < best[0]):
            best = (d, cy, cx, f"{x.get('category')}/{x.get('type')}")
    if not best:
        return lat, lon, False
    log(f"   OSM {best[3]}: posun {best[0]:.1f} km")
    return round(best[1], 4), round(best[2], 4), True


def osm_shape(title, lat, lon):
    """Obrys utvaru z OSM (na zvyraznenie) + jeho rozmer v km. (None, None), ak to nie je plocha pri suradniciach."""
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", headers=UA, timeout=30,
                         params={"q": title, "format": "jsonv2", "limit": 5, "polygon_geojson": 1, "polygon_threshold": 0.003}).json()
    except (requests.RequestException, ValueError):
        return None, None
    for x in r:
        g = x.get("geojson") or {}
        if x.get("category") in ("tourism", "amenity", "shop", "highway", "building", "office", "railway") or \
                g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        rings = [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]
        ring = max(rings, key=len)
        ys, xs = [p[1] for p in ring], [p[0] for p in ring]
        span = max(dist_km(min(ys), min(xs), min(ys), max(xs)), dist_km(min(ys), min(xs), max(ys), min(xs)))
        if len(ring) < 12:                                   # maly utvar -> OSM zjednodusi na trojuholnik
            continue
        if dist_km(lat, lon, (min(ys) + max(ys)) / 2, (min(xs) + max(xs)) / 2) < 60 and span > 0.3:
            ring = ring[::max(1, len(ring) // 150)]
            log(f"   obrys z OSM: {len(ring)} bodov, {span:.0f} km")
            return [[round(p[1], 5), round(p[0], 5)] for p in ring], round(span, 1)
    return None, None


CITIES = json.load(open(os.path.join(TOP, "cities.json"), encoding="utf-8"))
TIMES = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def feature_size(fact):
    """Velkost hlavneho utvaru (km) z clanku - pred pisanim, aby sa dalo spocitat porovnanie s mestom."""
    r = llm([{"role": "system", "content": "From the article, give the size in km (diameter, length or width) of the main "
              "thing visible from above on a satellite image. Only a number stated in the article. Return JSON {\"km\": number or null}."},
             {"role": "user", "content": fact["extract"][:3000]}], temp=0.1)
    try:
        return float(r.get("km")) if r.get("km") and float(r["km"]) > 0 else None
    except (TypeError, ValueError):
        return None


def scale_fact(km):
    """Porovnanie so znamym mestom v rovnakej mierke - pocita kod, model si ho nesmie vymysliet."""
    fits = [c for c in CITIES if 0.25 * km <= c["span_km"] <= 0.85 * km]
    if not fits:
        return None
    c = max(fits, key=lambda c: c["span_km"])
    say = c["name"].title()
    n = round(km / c["span_km"])
    fact = f"{say} would fit inside it" + (f", and it is about {TIMES[n]} times as wide as {say}" if n in TIMES else "")
    return {"city": c, "say": say, "on": say.split()[0], "fact": fact}


# ---------------------------------------------------------------- dorovnanie suradnic (vizualny model, zaloha)
VISION = ("meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct")
COLS = "ABCDEFGH"


def snapshot(lat, lon, z, n):
    """stvorcovy satelitny zaber 1080x1080 (sever hore) s mriezkou n x n, z = cela uroven."""
    import cv2
    import orbit_engine as E
    tx0, ty0, tx1, ty1, *_ = E.level_window(lat, lon, z, z)
    for ty in range(max(0, ty0), min(2 ** z - 1, ty1) + 1):
        for tx in range(tx0, tx1 + 1):
            E.fetch((z, tx % 2 ** z, ty))
    im = E.render_level(lat, lon, z, z)[420:1500]
    c = 1080 / n
    for k in range(1, n):
        cv2.line(im, (int(k * c), 0), (int(k * c), 1080), (255, 255, 255), 2)
        cv2.line(im, (0, int(k * c)), (1080, int(k * c)), (255, 255, 255), 2)
    for r in range(n if n > 1 else 0):                       # n = 1: cisty zaber bez mriezky (visible)
        for q in range(n):
            cv2.putText(im, f"{COLS[q]}{r + 1}", (int(q * c) + 6, int(r * c) + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    return cv2.imencode(".jpg", cv2.resize(im, (768, 768)), [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


_VM = []
def vision_models(base):
    """Groq meni ponuku modelov: vezmi pevny zoznam + vsetko, co v /models vyzera ako model s obrazkami."""
    if not _VM:
        ids = []
        try:
            r = requests.get(base + "/models", headers={"Authorization": "Bearer " + os.environ["MODELS_TOKEN"]}, timeout=30)
            ids = [m["id"] for m in r.json().get("data", [])]
        except (requests.RequestException, ValueError, KeyError):
            pass
        found = [i for i in ids if re.search(r"llama-4|scout|maverick|vision|[-_]vl|gemma-3|pixtral|qwen", i, re.I)]
        log(f"   vision kandidati: {found or 'ziadny'} (z {len(ids)} modelov)" + ("" if found else f": {sorted(ids)}"))
        _VM.extend(dict.fromkeys([v for v in VISION if v in ids] + found))
    return _VM


def vision(prompt, jpg):
    import base64
    base = os.environ.get("MODELS_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    url = "data:image/jpeg;base64," + base64.b64encode(jpg).decode()
    for model in vision_models(base):
        for a in range(3):
            try:
                r = requests.post(base + "/chat/completions", headers={"Authorization": "Bearer " + os.environ["MODELS_TOKEN"]},
                                  json={"model": model, "temperature": 0.1, "messages": [{"role": "user", "content": [
                                      {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]}]},
                                  timeout=120)
                if r.status_code == 200:
                    m = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
                    return json.loads(m.group(0)) if m else None
                log(f"   vision {model} {r.status_code}")
                if r.status_code in (400, 404):
                    break
            except (requests.RequestException, ValueError, KeyError) as e:
                log(f"   vision {model} chyba: {e}")
            time.sleep(10 * (a + 1))
    return None


def locate(fact, lat, lon, km):
    """Wikipedia casto dava stred oblasti, nie utvaru. Dva prechody: siroky zaber 6x6, potom blizsi 8x8."""
    import orbit_engine as E
    zf = z_for(lat, km)
    ok = False
    for z, n in ((int(math.floor(zf - 1.3)), 6), (int(math.floor(zf - 0.3)), 8)):
        z = max(3, min(16, z))
        prompt = (f"Satellite image, north is up, with a labeled {n}x{n} grid (columns {COLS[0]}-{COLS[n - 1]}, rows 1-{n}). "
                  f"Find {fact['title']}: {fact['extract'][:300]}\nIt is about {km:g} km across; the image is about "
                  f"{1080 * E.m_per_px(lat, z) / 1000:.0f} km wide. Which grid cell contains the CENTER of it? "
                  'Answer only JSON: {"cell": "C4", "visible": true, "confidence": 0.0-1.0}. If you cannot see it, "visible": false.')
        a = vision(prompt, snapshot(lat, lon, z, n))
        log(f"   poloha z{z}: {a}")
        cell = str((a or {}).get("cell", "")).upper().strip()
        if not a or not a.get("visible") or float(a.get("confidence", 0)) < 0.5 or not re.fullmatch(f"[{COLS[:n]}][1-{n}]", cell):
            continue
        q, r = COLS.index(cell[0]), int(cell[1]) - 1
        dx, dy = (q + 0.5) * 1080 / n - 540, (r + 0.5) * 1080 / n - 540     # px od stredu na urovni z
        cx, cy = E.merc(lat, lon, z)
        wz = 256 * 2 ** z
        lon = (cx + dx) / wz * 360 - 180
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (cy + dy) / wz))))
        ok = True
    return round(lat, 4), round(lon, 4), ok


# ---------------------------------------------------------------- v2: je to zo satelitu vobec vidiet?
MIN_KM = 0.1          # pod 100 m je to zo satelitu bodka (Darvaza 70 m); Grand Prismatic (110 m) este ide vdaka farbam
SMALL_KM = 0.25       # stare pravidlo 0,25 km: mensie utvary musia od modelu dostat aspon 4/5
VIS_MIN = 3           # skore 1-5, od ktoreho tema prejde


def img_score(jpg):
    """lacna zaloha bez modelu -> skore 1-5: kontrast jasu (odchylka L) + o kolko sa stred (utvar) lisi farbou od okolia.
    Odhali len prazdny zaber (more, rovne puste, sivá dlazdica "Map data not yet available"); vkus nenahradi."""
    import cv2
    import numpy as np
    im = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
    h, w = lab.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    d = np.hypot(xx - w / 2, yy - h / 2) / w
    de = float(np.linalg.norm(lab[d < 0.22].mean(0) - lab[(d > 0.38) & (d < 0.5)].mean(0)))
    st = float(lab[..., 0].std()) + 0.5 * de
    a, b5 = VIS_STAT
    return round(min(5.0, max(1.0, 1 + 2 * (st - a) / (b5 - a) if st < b5 else 3 + 2 * (st - b5) / (60 - b5))), 1)


VIS_STAT = (10.0, 22.0)   # L-odchylka + 0,5*dE: 10 = skore 1 (prazdne), 22 = skore 3; 10 referencii #011-#020 ma 23-100


def visible(fact, lat, lon, km):
    """(ok, preco): utvar musi byt zo satelitu poznat a vyzerat zaujimavo. Primaly -> hned nie; inak vizualny model
    nad satelitnym zaberom vo velkosti utvaru, pri jeho chybe statistika obrazka."""
    if km and km < MIN_KM:
        return False, f"{km:g} km, zo satelitu len bodka"
    z = max(3, min(18, int(round(z_for(lat, km) - 0.35)))) if km else 13
    try:
        jpg = snapshot(lat, lon, z, 1)
    except Exception as e:                                   # bez zaberu nevieme posudit -> nebrzdit
        log(f"   visible: zaber zlyhal ({e})")
        return True, "bez zaberu"
    import orbit_engine as E
    a = vision(f"Satellite image, north is up, about {1080 * E.m_per_px(lat, z) / 1000:.1f} km wide, centered on "
               f"{fact['title']}: {fact['extract'][:300]}\nIs the named feature clearly recognisable and visually striking in "
               "this satellite image? Score 1-5: 1 = nothing to see (plain water, plain ground, a dot), 3 = clearly "
               "recognisable, 5 = a striking shape or colors anyone would stop for. "
               'Answer only JSON: {"score": 1-5, "why": "at most 8 words"}', jpg)
    try:
        sc, why = float(a["score"]), "model: " + str(a.get("why", ""))[:60]
    except (TypeError, KeyError, ValueError):
        sc, why = img_score(jpg), "statistika obrazka"
    need = VIS_MIN + (1 if km and km < SMALL_KM else 0)
    log(f"   visible z{z}: {sc:g}/5 (treba {need}), {why}")
    return sc >= need, f"{sc:g}/5 z orbitu ({why})"


# ---------------------------------------------------------------- spec pre engine
def z_for(lat, km):
    """zoom, pri ktorom utvar zaberie ~80 % sirky (1080 px)."""
    return math.log2(156543.03 * math.cos(math.radians(lat)) * 1080 * 0.8 / (km * 1000))


def beat_fx(txt, i, n, nb, measured):
    """Efekty k slovam beatu (animacia toho, o com sa prave hovori). Pravidla, bez LLM."""
    def on(rx):
        m = re.search(rx, txt, re.I)
        return m.group(0).split()[0].lower().strip("?.,!") if m else None
    fx = []
    if i == 0:                                               # 1. beat = prelet z glóbusu
        return fx
    if i == n - 1:
        w = on(r"\bfollow\b")
        return [{"kind": "follow", "on": w}] if w else fx
    if "?" in txt and i < 3:
        fx.append({"kind": "ask", "on": on(r"\b(what|how|why|who|where|which)\b") or txt.split()[0].lower()})
    w = on(r"\b(ring|rings|circle|circular|round|oval)\b")
    if w and not measured and "highlight" not in nb and "tag" not in nb:
        fx.append({"kind": "trace", "on": w})
    w = on(r"\b(call|calls|called|nickname\w*|known)\b")
    if w:                                                    # "locals call it..." -> bublina, niekto hovori
        fx.append({"kind": "speech", "on": w})
    st = nb.get("stamp", {}).get("label", "")
    m = re.match(r"([\d.,]+)\s*(THOUSAND|MILLION|BILLION)?\s.*AGO", st) or \
        re.search(r"([\d.,]+)\s*(THOUSAND|MILLION|BILLION)\s+YEARS(\s+OLD)?$", st)   # "OVER 2 BILLION YEARS" (vek)
    if m:
        k = {"THOUSAND": 1e3, "MILLION": 1e6, "BILLION": 1e9}.get(m.group(2), 1)
        fx.append({"kind": "rewind", "on": txt.split()[0].lower().strip(",."), "n": int(float(m.group(1).replace(",", "")) * k)})
    w = on(r"\b(shatter|crack|fractur|split|broke|smash)\w*")
    if w:
        fx.append({"kind": "cracks", "on": w})
    if re.search(r"\b(fill|flood)\w*", txt, re.I) and re.search(r"\bwater\b", txt, re.I):
        fx.append({"kind": "water", "on": on(r"\b(fill|flood)\w*")})        # uz pri "filled", nie az na konci vety
    w = on(r"\b(deep|deeper|deepest|depth|depths)\b")
    if w:                                                    # hlbkomer; cislo len zo stampu (text ma cisla slovom)
        m = re.search(r"([\d,.]+)\s*(M|METERS?|METRES?|FT|FEET|KM)\b", st)
        d = {"kind": "depth", "on": txt.split()[0].lower().strip(",.")}   # "deep" byva posledne slovo -> od zaciatku vety
        if m:
            d["n"] = int(float(m.group(1).replace(",", "")))
            d["unit"] = {"FT": "FT", "FEET": "FT", "KM": "KM"}.get(m.group(2), "M")
        fx.append(d)
    m = re.search(r"\bsea(s| levels?)?\b[^.]{0,30}?\b(rose|rise[sn]?|rising|climb\w*|fell|fall\w*|drop\w*|lower\w*|sank)\b", txt, re.I)
    if m and not any(f["kind"] == "rewind" for f in fx):
        fx.append({"kind": "sea", "on": m.group(2).lower(), "dir": 1 if re.match(r"r|c", m.group(2), re.I) else -1})
    w = on(r"\beye\b")
    if w:                                                    # oko je vacsie nez bublina, spolu by sa prekryvali
        fx = [f for f in fx if f["kind"] != "speech"] + [{"kind": "eye", "on": w}]
    return fx


NEW_FX_MAX = 1      # dalsie efekty (fx_new.py) na video; variety_catalog rules: max 1 "signature" prvok na video
NEW_FX_WINDOW = 5   # efekt z poslednych 5 vydanych dielov sa neopakuje


def recent_new_fx():
    """druhy efektov z fx_new pouzite v poslednych NEW_FX_WINDOW vydanych dieloch (published.json + specs/)."""
    try:
        import fx_new
        pub = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "published.json"), encoding="utf-8"))
    except Exception:
        return set()
    out = set()
    for _, slug in sorted((v.get("no", 0), k) for k, v in pub.items())[-NEW_FX_WINDOW:]:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "specs", slug + ".json")
        if os.path.exists(p):
            out |= {f["kind"] for b in json.load(open(p, encoding="utf-8"))["beats"] for f in b.get("fx", [])
                    if f["kind"] in fx_new.EFFECTS}
    return out


def new_fx(txt, i, n, nb, fx, beats):
    """Jeden dalsi efekt z fx_new.TRIGGERS podla slov beatu (bez opakovania vo videu ani v poslednych dieloch);
    nie cez pravitko, foto, dopad."""
    if i == 0 or i == n - 1 or len(fx) >= 2 or any(k in nb for k in ("ruler", "rings", "scale", "impact", "photo")):
        return []
    try:
        import fx_new
    except ImportError:                                      # engine efekty (cv2) nie su k dispozicii -> bez nich
        return []
    used = [f["kind"] for x in beats for f in x.get("fx", []) if f["kind"] in fx_new.EFFECTS]
    if len(used) >= NEW_FX_MAX:
        return []
    f = fx_new.pick(txt, nb, used=set(used) | recent_new_fx(), have=[f["kind"] for f in fx])
    n = f.get("n") if f else None
    if isinstance(n, (int, float)) and 1000 <= n <= 2100 and (
            str(int(n)) in years(txt) or re.search(rf"\b{int(n)}\b", txt + " " + nb.get("stamp", {}).get("label", ""))):
        return []                                            # cislo je rok, nie pocet
    return [f] if f else []


def cut(t, n):                                               # skratit na cele slova, nie "FROM SPAC"
    t = t.upper().strip()
    return t if len(t) <= n else t[:n + 1].rsplit(" ", 1)[0]


MEASURED = ("ruler", "rings", "scale", "highlight", "tag")   # popisky, ktore sedia len na celom utvare


def dress(nb, b, i, n, beats, photos, lat, lon, km, scale, impact_ok, measured, react_dur=1.4, photo_dur=2.8, v2=False):
    """overlay, dopad, efekty, reakcia a foto jedneho beatu (spolocne pre v1 aj v2); dopisuje do nb.
    v2: kamera sa hybe stale -> nahradny sken max 2x na video a nie na beate s fotkou."""
    o = b.get("overlay") if i else None                      # v 1. zabere leti kamera z globusu, overlay by bol mrnavy
    if o and o.get("type") == "ruler":
        lab = f"{round(km * 1000)} M" if km < 1 else (o.get("label") or f"{km:g} KM")   # nie "0.318 KM"
        nb["ruler"] = {"lat": lat, "lon": lon, "km": km, "label": lab, "on": o["on"]}
    elif o and o.get("type") == "rings":
        nb["rings"] = {"lat": lat, "lon": lon, "km": [round(km / 2 * f, 2) for f in (0.3, 0.6, 0.9)], "on": o["on"]}
    elif o and o.get("type") == "scale" and scale:
        nb["scale"] = {"name": scale["city"]["name"], "poly_km": scale["city"]["poly_km"], "on": o["on"]}
    elif o and o.get("type") == "highlight":
        nb["highlight"] = {"on": o["on"]}
    elif o and o.get("type") == "tag":
        nb["tag"] = {"lat": lat, "lon": lon, "label": cut(digits(o.get("label", "")), 18), "on": o["on"]}
    elif o and o.get("type") == "stamp":
        lab = re.sub(r"\bMYA\b", "MILLION YEARS AGO", o.get("label", "").upper())
        nb["stamp"] = {"label": cut(re.sub(r"\bBYA\b", "BILLION YEARS AGO", lab), 26), "on": o["on"]}
    m = METEOR.search(b["text"]) if impact_ok and not any("impact" in x for x in beats) else None
    if m:                                                    # animacia dopadu na prvom beate, kde pribeh povie meteorit
        hw = HIT.search(b["text"], m.start()) or HIT.search(b["text"]) or m
        nb["impact"] = {"on": hw.group(1).lower()}
    fx = beat_fx(b["text"], i, n, nb, measured)
    fx += new_fx(b["text"], i, n, nb, fx, beats)
    busy = fx or any(k in nb for k in ("ruler", "rings", "scale", "highlight", "tag", "stamp", "impact", "photo"))
    nfb = sum(1 for x in beats for f in x.get("fx", []) if f.get("fallback"))
    if v2 and (b.get("photo") or nfb >= 2):
        busy = True
    if not busy and 0 < i < n - 1:                           # nic sa nedeje -> nahradny efekt (sken / sonar), striedavo
        fx = [{"kind": ("scan", "pulse")[nfb % 2], "on": None, "fallback": True}]
    if fx:
        nb["fx"] = fx
    r = b.get("react")
    if r and r.get("expr") in ("surprised", "happy"):
        nb["react"] = {"expr": r["expr"], "on": r["on"], "dur": react_dur}
    p = b.get("photo")
    if p and 0 < i < n - 1:
        ph = photos[p["index"]]
        pl = cut(p.get("label", ""), 22)
        if v2 and len(pl) < len(str(p.get("label", "")).strip()):
            pl = re.sub(r"\s+(OPEN|THE|OF|A|AN|IN|ON|AT|AND|FROM|NEAR|WITH|BY)$", "", pl)
        nb["photo"] = {"file": ph["file"], "label": pl, "credit": ph["credit"],
                       "on": p["on"], "dur": photo_dur}


def build(fact, s, photos, scale=None, shape=None, no=None, nxt_pos=None):
    if s.get("v2"):
        return build_v2(fact, s, photos, shape, no)
    lat, lon = fact["lat"], fact["lon"]
    km = float(s["feature_km"])
    zf = max(4.5, min(Z_MAX - 0.2, z_for(lat, km) - 0.35))     # cely utvar aj s okolim (~60 % sirky); maly utvar co najblizsie
    zs = {"feature": zf, "close": min(Z_MAX, zf + 0.9), "wide": max(4.5, zf - 1.8), "space": max(4.5, zf - 5.0)}
    beats, nfeat, wide_used = [], 0, False
    for i, b in enumerate(s["beats"]):
        shot = b.get("shot") if b.get("shot") in zs else "feature"
        if i == len(s["beats"]) - 1:
            shot = "space"
        elif shot == "space" or (shot == "wide" and (wide_used or i < 3)):
            shot = "feature"                                 # dalekych zaberov max 1, inak kamera "pumpuje"; nie pocas hacika a teaseru
        measured = (b.get("overlay") or {}).get("type") in MEASURED
        if measured:
            shot = "feature"                                 # pravitko/prstence sedia len na celom utvare
        wide_used |= shot == "wide"
        z = zs[shot]
        if shot == "feature" and not measured:
            z += min(0.3, 0.1 * nfeat); nfeat += 1           # pomaly najazd, nie skoky
        nb = {"text": b["text"], "cam": {"lat": lat, "lon": lon, "z": round(min(Z_MAX, z), 2)}}
        if shot == "space" and nxt_pos:                      # koniec: skok k dalsiemu cielu namiesto statickej mapy
            nb["cam"] = {"lat": nxt_pos[0], "lon": nxt_pos[1], "z": 13.0, "hop": True}
        if i == 0:
            nb["globe"] = True
        dress(nb, b, i, len(s["beats"]), beats, photos, lat, lon, km, scale, i >= 3 and shot != "space", measured)
        beats.append(nb)
    used = [photos[b["photo"]["index"]] for b in s["beats"] if b.get("photo")]
    credits = "Imagery: Esri, Maxar, Earthstar Geographics." + (
        " Photos: " + "; ".join(sorted({p["credit"] for p in used})) + ", Wikimedia Commons." if used else "")
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    return {"title": s.get("title") or fact["title"], "coords": f"{abs(lat):.4f} {ns}, {abs(lon):.4f} {ew}",
            "voice": "am_michael", "speed": 1.1, "music": "cine_616.mp3", "start": {"lat": lat, "lon": lon},
            "source": fact["url"], "feature_km": km, "beats": beats, "hook": cut(s.get("hook_title", ""), 22),
            "description": f"{s.get('description', '').strip()} {credits} Source: Wikipedia.",
            "hashtags": (s.get("hashtags") or ["#shorts"])[:6], "shape": shape, "series_no": no}


# ---------------------------------------------------------------- v2 kamera: po pristati nikdy nestoji
V2_ZOOM = (4.5, 19.0)        # engine: dlazdice Esri do z19 (referencie #012/#015 idu na 19.0); prilet z globusu od z5.3
V2_DEEP = (1.0, 1.4, 1.8, 2.2)   # priblizenia beatov 3-6 nad zaberom haku (referencie: +1.0 az +2.5)
STOP = set("the a an and but of in on at to is it its was were this that these with for from by as are has have had "
           "been into than then there here they them their only just still about over under".split())


def v2_word(text, last_part=0.5):
    """najdlhsie (nie pomocne) slovo z konca vety: na nom kamera odletie na cely utvar"""
    ws = [w.strip(".,!?;:'\"") for w in text.split()]
    tail = [w for w in ws[int(len(ws) * (1 - last_part)):] if w and w.lower() not in STOP and w.lower() not in NUMW]
    return max(reversed(tail or [w for w in ws if w]), key=len)


def ring_word(text):
    """slovo, ktore pomenuje to, co divak vidi ("This island..." -> island): na nom sa nakresli kruh"""
    ws = [w.strip(".,!?;:'\"") for w in text.split()]
    for k, w in enumerate(ws):
        if w.lower() in ("this", "these"):
            for x in ws[k + 1:]:
                if x and x.lower() not in NUMW | {"one", "a", "giant", "tiny", "huge", "small", "big", "perfect", "concrete"} \
                        and not COLORW.fullmatch(x):
                    return x
    return v2_word(text, 1.0)


def v2_cams(lat, lon, km, bs, seed):
    """kamera kazdeho beatu: iny bod vnutri utvaru a iny zoom (ako rucne #011-#020); posledny beat pri strede."""
    import random
    rng = random.Random(seed)                                # rovnaky slug -> rovnaky prerender
    zh = max(V2_ZOOM[0], min(V2_ZOOM[1] - 1.5, z_for(lat, km) - 1.0))   # hak: utvar s okolim (~40 % sirky), kruh okolo
    dlat = km / 111.32
    dlon = dlat / max(0.2, math.cos(math.radians(lat)))
    angs = list(range(0, 360, 45)); rng.shuffle(angs)
    deep = list(V2_DEEP); rng.shuffle(deep)
    cams = []
    for i, b in enumerate(bs):
        o = (b.get("overlay") or {}).get("type") if i else None
        if i == 0:
            dz, r = 0.0, 0.0
        elif i == len(bs) - 1:
            dz, r = 0.4, 0.0                                 # posledny beat: stred, potom "moves" von na cely utvar
        elif i == 1:                                         # dokaz: s fotkou mierne dnu, bez fotky priblizenie na detail
            dz, r = (0.8, 0.04) if b.get("photo") else (1.6, 0.12)
        elif o in MEASURED:
            dz, r = 0.4 + 0.1 * (i % 3), 0.03                # pravitko/stitok sedia len na celom utvare
        else:
            dz, r = deep[i % len(deep)], rng.uniform(0.12, 0.28)
        a = math.radians(angs[i % len(angs)])
        c = {"lat": round(lat + r * dlat * math.sin(a), 5), "lon": round(lon + r * dlon * math.cos(a), 5),
             "z": round(min(V2_ZOOM[1], zh + dz), 2)}
        while any(c == x for x in cams):                     # kamera nikdy dvakrat na tom istom mieste
            c["z"] = round(c["z"] - 0.15, 2)
        cams.append(c)
    return zh, cams


def v2_credit(c):
    """'Bruce McAdam, CC BY-SA 2.0' -> 'Bruce McAdam (CC BY-SA 2.0)' (styl popisov #011-#020)"""
    m = re.match(r"^(.*), ((?:CC|PD|Public|cc|pd).*)$", c)
    return f"{m.group(1)} ({m.group(2)})" if m else c


def build_v2(fact, s, photos, shape=None, no=None):
    lat, lon = fact["lat"], fact["lon"]
    km = float(s["feature_km"])
    bs = s["beats"]
    n = len(bs)
    zh, cams = v2_cams(lat, lon, km, bs, fact.get("url") or fact["title"])
    beats = []
    for i, b in enumerate(bs):
        nb = {"text": b["text"], "cam": cams[i]}
        if i == 0:                                           # kruh namiesto otaznikov
            o = b.get("overlay") or {}
            toks = [re.sub(r"[^a-z0-9']", "", t.lower()) for t in b["text"].split()]
            on = o.get("on") if o.get("type") == "rings" and re.sub(r"[^a-z0-9']", "", str(o.get("on", "")).lower()) in toks \
                else ring_word(b["text"])
            nb["rings"] = {"lat": lat, "lon": lon, "km": [round(0.6 * km, 3)], "on": on}
        if i == n - 1:                                       # slucka: kamera odletie na cely utvar (ako prvy zaber)
            nb["moves"] = [{"lat": lat, "lon": lon, "z": round(max(V2_ZOOM[0], zh - 0.6), 2), "on": v2_word(b["text"]),
                            "dur": 1.5}]
        measured = (b.get("overlay") or {}).get("type") in MEASURED
        dress(nb, b, i, n, beats, photos, lat, lon, km, None, i >= 2, measured, react_dur=1.3, photo_dur=2.4, v2=True)
        m = re.match(r"\s*([\d,.]+)\s*(KM|M)(?![A-Z])", nb.get("ruler", {}).get("label", ""))
        if m:                                                # pravitko meria to, co hovori stitok (hraz 32 km, nie jazero 60 km)
            rk = float(m.group(1).replace(",", "")) / (1000 if m.group(2) == "M" else 1)
            if rk > 0 and abs(rk / km - 1) > 0.15:
                nb["ruler"]["km"] = rk
        beats.append(nb)
    used = [photos[b["photo"]["index"]] for b in bs[1:-1] if b.get("photo")]
    cr = list(dict.fromkeys(v2_credit(p["credit"]) for p in used))
    q = [str(x).strip().upper() for x in s.get("question") or []][:2]
    ask = bool(no) and no % 2 == 1 and len(q) == 2           # A/B test: otazka na konci len pri neparnych dieloch
    desc = s.get("description", "").strip()
    desc = (desc + (" " + proper(q[0].capitalize() + " " + q[1].lower(), fact["title"] + " " + fact.get("extract", "")) if ask else "") + " Imagery: Esri, Maxar, Earthstar Geographics."
            + (f" Photo{'s' if len(cr) > 1 else ''}: {', '.join(cr)}, Wikimedia Commons." if cr else "") + " Source: Wikipedia.")
    tags = []
    for t in (s.get("hashtags") or [])[:6] + ["#satellite", "#earthfromspace"]:   # #orbit #shorts prida publish.py
        t = "#" + re.sub(r"[^a-z0-9]", "", str(t).lower())
        if len(t) > 1 and t not in tags and t not in ("#orbit", "#shorts"):
            tags.append(t)
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    spec = {"title": re.sub(r"\s*\(.*?\)", "", fact["title"]), "coords": f"{abs(lat):.4f} {ns}, {abs(lon):.4f} {ew}",
            "voice": "am_michael", "speed": 1.1, "music": "cine_616.mp3", "start": {"lat": lat, "lon": lon},
            "source": fact["url"], "feature_km": km, "hook": cut(num_label(s.get("hook_title", "")), 22), "series_no": no,
            "v2": True, "outro": "loop"}
    if ask:
        spec["outro_text"] = q
    spec.update({"tail": 1.4, "fly0": 1.3, "description": desc, "hashtags": tags[:7], "beats": beats, "shape": shape})
    return spec


def main():
    qp = os.path.join(TOP, "queue.json")
    queue = json.load(open(qp, encoding="utf-8"))
    slug, km = (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None), None
    todo = [x for x in queue if x["status"] == "todo"]
    last = max((x for x in queue if x.get("no") and x["status"] in ("written", "done")), key=lambda x: x["no"], default=None)
    lp = os.path.join(HERE, "drafts", last["slug"] + ".json") if last else ""
    promised = json.load(open(lp, encoding="utf-8")).get("next") if lp and os.path.exists(lp) else None
    todo.sort(key=lambda x: x["slug"] != promised)                  # predosly diel slubil "Next target: ..." -> ten prvy
    v2 = os.environ.get("ORBIT_V1") != "1"                          # v2 je predvolene; ORBIT_V1=1 = stary format (9 beatov)
    for x in ([] if slug else todo):
        bk = os.path.join(HERE, "bank", x["slug"] + ".json")
        if os.path.exists(bk) and json.load(open(bk, encoding="utf-8")).get("draft"):   # zo zasoby: velkost uz overena rucne
            slug = x["slug"]
            break
        xf = json.load(open(os.path.join(TOP, "facts", x["slug"] + ".json"), encoding="utf-8"))
        km = feature_size(xf)
        if v2:                                                    # v2: tema musi byt zo satelitu vidiet (Natron, Spotted Lake nie)
            vlat, vlon = (x["lat"], x["lon"]) if x.get("located") else locate_osm(xf["title"], x["lat"], x["lon"])[:2]
            ok, why = visible(xf, vlat, vlon, km)
            if not ok:
                log(f"   {x['slug']}: {why}, preskakujem")
                x["status"], x["why"] = "skip", why
                continue
        elif km and km < 0.25:                                    # zo satelitu len bodka (Darvaza 70 m) -> preskocit
            log(f"   {x['slug']}: {km} km, primale, preskakujem")
            x["status"] = "skip"
            continue
        slug = x["slug"]
        break
    if not slug:                                                  # vsetko preskocene: aspon zapisat dovody
        json.dump(queue, open(qp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        sys.exit("ziadna tema na pisanie (fronta prazdna alebo vsetko preskocene)")
    q = next(q for q in queue if q["slug"] == slug)
    fact = json.load(open(os.path.join(TOP, "facts", slug + ".json"), encoding="utf-8"))
    fact["lat"], fact["lon"] = q["lat"], q["lon"]          # queue ma aj rucne opravene suradnice
    log(f"tema: {fact['title']} ({q['lat']:.4f}, {q['lon']:.4f})")
    dp = os.path.join(HERE, "drafts", slug + ".json")
    bp = os.path.join(HERE, "bank", slug + ".json")                   # rucne prepracovany scenar zo zasoby (orbit/bank.py)
    bank = json.load(open(bp, encoding="utf-8")) if os.path.exists(bp) else {}
    if os.environ.get("ORBIT_REBUILD") != "1" and bank.get("draft"):
        s, photos, shape, scale = bank["draft"], bank["photos"], bank["shape"], bank["scale"]
        lat, lon, ok = bank["lat"], bank["lon"], bank["located"]
        fact["lat"], fact["lon"] = lat, lon
        nq = next((x for x in queue if x["slug"] == bank.get("next")), None)
        log("   scenar zo zasoby (orbit/bank)")
        if not ok:
            lat, lon, ok = locate(fact, q["lat"], q["lon"], float(s["feature_km"]))
        if not q.get("located"):
            fact["lat"], fact["lon"] = q["lat"], q["lon"] = lat, lon
            q["located"] = ok
    elif os.environ.get("ORBIT_REBUILD") == "1" and os.path.exists(dp):   # len prepocitat kameru/overlaye, text ostava
        d = json.load(open(dp, encoding="utf-8"))
        s, photos = d["draft"], d["photos"]
        log("   prerender z ulozeneho navrhu")
        if d.get("v2"):
            s["v2"] = True                                        # navrh v2 -> build_v2; stary navrh ostava v1
            repair_v2(s)
        v2 = bool(s.get("v2"))
        shape, scale = d.get("shape"), d.get("scale")
        nq = None if v2 else next((x for x in queue if x["slug"] == d.get("next")), None) or next(
            (x for x in queue if x["status"] == "todo" and x["slug"] != slug), None)
    else:
        photos = commons_photos(fact["title"], q["lat"], q["lon"])
        log(f"   fotky z Commons: {len(photos)}")
        lat, lon, ok = q["lat"], q["lon"], q.get("located")
        if not ok:
            lat, lon, ok = locate_osm(fact["title"], q["lat"], q["lon"])
            fact["lat"], fact["lon"] = lat, lon
        km = km or feature_size(fact)                               # porovnanie s mestom pocita kod z clanku
        scale = scale_fact(km) if km else None
        shape, span = osm_shape(fact["title"], fact["lat"], fact["lon"])
        if shape and km and not 0.6 * km <= span <= 1.5 * km:     # obrys je nieco ine nez utvar z clanku (ramena, rieky)
            log(f"   obrys {span} km nesedi s {km} km, zvyraznenie kruhom")
            shape = None
            if span > 1.5 * km and not q.get("located"):
                lat, lon = fact["lat"], fact["lon"] = q["lat"], q["lon"]
                log(f"   OSM objekt je vacsi nez utvar -> stred ostava z Wikipedie ({lat}, {lon})")
        log(f"   velkost {km} km, porovnanie: {scale['fact'] if scale else 'ziadne'}")
        nq = None if v2 else next((x for x in queue if x["status"] == "todo" and x["slug"] != slug and   # v2: ziadny "Next target"
                                   os.path.exists(os.path.join(TOP, "facts", x["slug"] + ".json"))), None)
        nxt = json.load(open(os.path.join(TOP, "facts", nq["slug"] + ".json"), encoding="utf-8")) if nq else None
        if v2:
            fact["extract"] = more_text(fact)
            log(f"   text clanku: {len(fact['extract'])} znakov")
        s = write(fact, photos, scale, nxt, km, v2)
        if not ok:
            lat, lon, ok = locate(fact, q["lat"], q["lon"], float(s["feature_km"]))
        if not q.get("located"):
            log(f"   stred utvaru: {lat}, {lon} (Wikipedia {q['lat']}, {q['lon']}){'' if ok else ' - NEDOROVNANE'}")
            fact["lat"], fact["lon"] = q["lat"], q["lon"] = lat, lon
            q["located"] = ok
    pp = os.path.join(HERE, "published.json")                      # rucne diely #011-#020 su len tu, nie vo fronte
    pub = json.load(open(pp, encoding="utf-8")) if os.path.exists(pp) else {}
    q["no"] = q.get("no") or 1 + max([x.get("no") or 0 for x in queue] +
                                     [v.get("no") or 0 for v in pub.values() if isinstance(v, dict)])   # cislo dielu serie
    download(photos, slug, {b["photo"]["index"] for b in s["beats"] if b.get("photo")})
    os.makedirs(os.path.join(HERE, "drafts"), exist_ok=True)       # surovy navrh: prerender bez noveho pisania
    json.dump({"draft": s, "photos": photos, "lat": fact["lat"], "lon": fact["lon"], "shape": shape, "scale": scale,
               "next": nq["slug"] if nq else None, **({"v2": True} if s.get("v2") else {})},
              open(os.path.join(HERE, "drafts", slug + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    spec = build(fact, s, photos, scale, shape, q["no"], (nq["lat"], nq["lon"]) if nq else None)
    json.dump(spec, open(os.path.join(HERE, "specs", slug + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    q["status"] = "written"
    json.dump(queue, open(qp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for b in spec["beats"]:
        log("   > " + b["text"])
    print(slug)
    if os.environ.get("GITHUB_OUTPUT"):
        open(os.environ["GITHUB_OUTPUT"], "a").write(f"slug={slug}\n")


if __name__ == "__main__":
    main()

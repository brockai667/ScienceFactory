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
Z_MAX = 16.8                  # Esri ma ostre snimky vsade len priblizne do z17


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
                log(f"   llm {model} {r.status_code}, cakam {wait:.0f} s" + ("" if r.status_code == 429 else ": " + r.text[:300]))
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
SYSTEM = """You write narration for a 40-50 second vertical video about a place seen on a satellite map.
A cute satellite robot called Orbi narrates while the camera flies from a globe down to the place.
The viewer must keep watching because a question stays open until late in the video.

Structure, exactly 9 beats, 100 to 125 words in total. Short spoken sentences (max 16 words), plain English:
1. Hook (rules below). Write 3 different hook candidates in "hooks"; beat 1 text is your best one.
2. The question the viewer is now asking, as a real question ("So what carves a lake into a perfect ring?"). Do not answer it yet.
3. A promise that keeps them watching: one more surprise is coming at the end, without saying what it is ("And the middle hides one more surprise."). Never reveal it here.
4-5. What you see and how big it is. Use the computed scale fact here if one is given.
6-7. The real answer, step by step. This is the first time the cause is named.
8. The payoff of the promise from beat 3: the most surprising fact in the article that you have not used yet.
9. The last beat (exact rule given in the user message).
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
- Each candidate has a "title": 2 to 4 words, ALL CAPS, max 22 characters, shown big from second 0. It adds a second true fact or a question and never repeats a word of the spoken hook. Digits are fine in the title only.

Example of the tone (a different place):
1 "This giant eye in the Sahara is forty kilometers wide, and no one built it."
2 "So what draws perfect rings into a desert?"
3 "Stay till the end, because the rings hide one more surprise."
4 "From orbit, ring sits inside ring, like a target."
5 "Paris would fit inside it, and it is about two times as wide."
6 "About a hundred million years ago, molten rock pushed the ground up into a giant dome."
7 "Then wind and rain wore it down, layer by layer, until only these rings were left."
8 "And astronauts use it as a landmark, because it is one of the few things you can spot from space."
9 "Next target: a crater that has been burning for decades. Follow for the next scan. Orbi out."

Written for the ear (a voice reads it):
- Numbers as people say them: "about seventy kilometers", "two hundred fourteen million years ago", "almost a kilometer high". No decimals, no symbols or unit signs (no km, m, %, ³, ~), no brackets, no em dashes. Plain ASCII quotes and hyphens.

Facts:
- Use ONLY facts written in the article. Every number, date, name and claim must be in the article. No guessing, no rounding up to sound bigger.
- Never invent a myth, rumor or what "some people" say, think or wonder. If the article has no myth, use a question instead.
- No comparisons or analogies of your own ("enough to flood a city", "as big as a country"). The only allowed comparison is the computed scale fact in the user message.
- Do not describe colors (blue, green, white...) unless the article states that color. Satellite colors often look different from what you expect.

Visual cues (each "on" is ONE word copied exactly from that beat's text, where the cue appears):
- shot per beat: "feature" (whole place fills the screen), "close" (zoomed in on detail), "wide" (zoomed out to see the surroundings), "space" (far away, only for the last beat).
- overlay (at most one per beat, none in beat 1 or beat 9, use 4 or 5 in total so something new appears every few seconds; labels in plain words with a noun, never a bare number, no abbreviations like MYA or KM2):
  {"type":"ruler","on":word,"label":"40 KM"} for the size (label must match feature_km),
  {"type":"highlight","on":word} spotlights the outline of the place (good when you name its shape),
  {"type":"scale","on":word} draws the city from the scale fact on top, at the same scale ("on" = the city's first word; required when a scale fact is given),
  {"type":"rings","on":word} only if the place is round,
  {"type":"tag","on":word,"label":"SHORT WORDS"} to pin a named part,
  {"type":"stamp","on":word,"label":"SHORT DATE OR FACT"} for the key date or record.
- react (2 or 3 in the whole video, the robot's face reacts): {"expr":"surprised" or "happy","on":word}. Surprised on the most shocking fact, happy on the payoff or the last beat.
- photo (use 1 or 2 if the list has photos that clearly show this place, never in beat 1 or the last beat): {"index":N,"label":"SHORT CAPTION","on":word} using a photo from the list.

Return JSON: {"title": str, "feature_km": number (size of the main thing visible from above, in km, from the article),
"hooks": [{"text": str, "title": str}, {"text": str, "title": str}, {"text": str, "title": str}],
"beats": [{"text": str, "shot": str, "overlay": obj or null, "react": obj or null, "photo": obj or null}],
"description": str (2 sentences, facts only), "hashtags": [5 strings starting with #]}"""

CHECK = """You are a fact checker for a short narrated video about a place seen on a satellite map.
Flag a sentence only if it states a FACT that is false or not in the article:
- a number, size, height, depth, date or age that differs from the article (rounding with "about"/"almost" is fine),
- a name, nickname, cause, record or event the article does not give,
- anything about what people or scientists say, call it, think, wonder or believe, unless the article says it,
- any comparison or analogy ("enough to flood a city", "bigger than...") that is not in the article, except the computed scale fact given below,
- a color the article does not state.
Never flag: describing shapes on the satellite image ("looks like an eye", "a ring", "from space"), telling viewers to type coordinates,
questions, promises that a surprise is coming, simple plain-language wording of what the article says, the computed scale fact,
the closing "Follow for the next scan. Orbi out." line. The "Next target" line is about a different place: check it only against the next-topic text.
Return JSON: {"problems": [str]}, one short line per false or invented fact. Empty list if there are none."""

JUDGE = """You pick the strongest opening line (hook) for a 45 second vertical video about a place seen on a satellite map.
Score each candidate 0-2 on each point:
1. Picture: names a concrete visual in the first 6 words.
2. Tension: a number, scale or impossibility that makes you ask a question, WITHOUT revealing the cause or answer (hook or title naming the cause scores 0 here).
3. Speed and sound: 14 words or fewer, clear without seeing the screen, no hype phrases, no coordinate numbers.
4. Truth and fit: every claim is in the article; the title adds a new fact and does not repeat the hook's words.
Highest total wins; a tie goes to the shorter one.
Return JSON: {"scores": [int per candidate], "best": index of the winner (0-based)}"""

BANNED = re.compile(r"something (strange|weird)|\bweird\b|mysterious|won't believe|\bsecret\b|baffled|did you know|today we", re.I)


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


def validate(s, photos, ctx):
    errs = []
    bs = s.get("beats") or []
    if len(bs) != 9:
        errs.append(f"need exactly 9 beats, got {len(bs)}")
    seen = {}
    for i, b in enumerate(bs[:-1]):
        ns = numbers(b.get("text", ""))
        if len(ns) > 1:
            errs.append(f"beat {i + 1} has {len(ns)} numbers ({', '.join(ns)}): one number per beat at most")
        for n in ns:
            if n in seen:
                errs.append(f"the number '{n}' is used in beat {seen[n]} and beat {i + 1}: never repeat a number")
            seen.setdefault(n, i + 1)
        for c in set(m.lower() for m in COLORW.findall(b.get("text", ""))):
            if not re.search(rf"\b{c}", ctx["article"], re.I):
                errs.append(f"beat {i + 1} says '{c}', but the article never states that color")
    if len(bs) > 2 and "?" not in bs[1].get("text", ""):
        errs.append("beat 2 must be the viewer's question, ending with '?'")
    if ctx["scale"] and not any((b.get("overlay") or {}).get("type") == "scale" for b in bs):
        errs.append(f"add this computed scale fact in beat 4 or 5: \"{ctx['scale']['fact']}.\" with a scale overlay on the word '{ctx['scale']['on']}'")
    words = sum(len(b.get("text", "").split()) for b in bs)
    if not 95 <= words <= 130:
        errs.append(f"need 100-125 words, got {words}")
    for i, b in enumerate(bs):
        bad = re.findall(r"[0-9]+[.,][0-9]+|[%~()²³]|\bkm\b|[0-9] ?m\b", b.get("text", ""))
        if bad:
            errs.append(f"beat {i + 1} is not written for the ear ({', '.join(bad)}): spell numbers and units as words")
    if sum(1 for b in bs if b.get("react")) < 2:
        errs.append("use 2 or 3 react cues")
    if sum(1 for b in bs[1:-1] if b.get("overlay")) < 4:
        errs.append("use 4 or 5 overlays, none in beat 1 or beat 9")
    for i, b in enumerate(bs):
        o = b.get("overlay") or {}
        if o.get("type") in ("tag", "stamp") and not re.search(r"[A-Za-z]{3}", str(o.get("label", ""))):
            errs.append(f"beat {i + 1} {o['type']} label '{o.get('label')}' needs words, not a bare number")
    if photos and not any(b.get("photo") for b in bs):
        errs.append("use at least 1 photo from the list")
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
    last = bs[-1].get("text", "").strip() if bs else ""
    if ctx["next"]:
        if not (last.startswith("Next target:") and last.endswith(SIGNOFF) and len(last.split()) <= 22):
            errs.append(f"beat 9 must be 'Next target: <short tease>. {SIGNOFF}'")
    elif last != SIGNOFF:
        errs.append(f"beat 9 must be exactly: {SIGNOFF}")
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


def write(fact, photos, scale, nxt, km=None):
    ctx = {"article": fact["extract"], "scale": scale, "next": nxt}
    plist = "\n".join(f"{i}: {p['desc']}" for i, p in enumerate(photos)) or "(no photos)"
    extra = (f"Size of the main feature from the article: {km:g} km (use it as feature_km).\n" if km else "") + (f"Computed scale fact (true, use it in beat 4 or 5 with a scale overlay on the word '{scale['on']}'): {scale['fact']}."
             if scale else "Computed scale fact: none (do not use a scale overlay).")
    extra += (f"\nBeat 9 must be exactly: \"Next target: <tease of at most 10 words, one true fact from the next-topic text, "
              f"without naming the place>. {SIGNOFF}\"\nNext topic: {nxt['title']}. {nxt['extract'][:500]}"
              if nxt else f"\nBeat 9 must be exactly: \"{SIGNOFF}\"")
    user = (f"Place: {fact['title']}\nCoordinates: {fact['lat']:.4f}, {fact['lon']:.4f}\n{extra}\n\nPhotos:\n{plist}"
            f"\n\nArticle:\n{fact['extract']}")
    side = (f"\n\nComputed scale fact (true): {scale['fact']}." if scale else "") + (
        f"\n\nNext-topic text (only for the 'Next target' line): {nxt['extract'][:500]}" if nxt else "")
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    for att in range(8):
        s = llm(msgs)
        for b in s.get("beats") or []:                       # typograficke znaky -> ASCII (TTS ich cita zle)
            b["text"] = re.sub(r"[‐-―]", "-", b.get("text", "")).translate(
                {0x2018: "'", 0x2019: "'", 0x201c: '"', 0x201d: '"', 0x2026: "..."}).strip()
            toks = [re.sub(r"[^a-z0-9']", "", t.lower()) for t in b["text"].split()]
            for k in ("overlay", "react", "photo"):          # "on" s viac slovami -> prve slovo, ktore v zabere je
                o = b.get(k)
                if isinstance(o, dict) and len(str(o.get("on", "")).split()) > 1:
                    hit = [w for w in str(o["on"]).split() if re.sub(r"[^a-z0-9']", "", w.lower()) in toks]
                    if hit:
                        o["on"] = hit[0]
        errs = validate(s, photos, ctx)
        if len(s.get("beats") or []) < 6:                    # rozbity navrh: neopravovat, zacat odznova
            log(f"   pokus {att + 1}: rozbity navrh, odznova: {json.dumps(s)[:300]}")
            msgs = msgs[:2]
            continue
        if not errs:
            hooks = [h for h in s["hooks"] if isinstance(h, dict)]
            pick = llm([{"role": "system", "content": JUDGE},
                        {"role": "user", "content": f"Article:\n{fact['extract'][:2500]}\n\nCandidates:\n" + "\n".join(
                            f"{i}: \"{h['text']}\" / title: {h['title']}" for i, h in enumerate(hooks))}], temp=0.1)
            best = pick.get("best") if isinstance(pick.get("best"), int) and 0 <= pick["best"] < len(hooks) else 0
            b0 = s["beats"][0]
            b0["text"], s["hook_title"] = [re.sub(r"[‐-―]", "-", hooks[best][k]).translate(
                {0x2018: "'", 0x2019: "'", 0x201c: '"', 0x201d: '"'}).strip() for k in ("text", "title")]
            toks = [re.sub(r"[^a-z0-9']", "", t.lower()) for t in b0["text"].split()]
            for k in ("overlay", "react", "photo"):              # cue na slove, ktore vo vitaznom hooku nie je, zahodit
                if b0.get(k) and re.sub(r"[^a-z0-9']", "", str(b0[k].get("on", "")).lower()) not in toks:
                    b0[k] = None
            log(f"   hook {best + 1}/{len(hooks)} {pick.get('scores')}: {b0['text']} | {s['hook_title']}")
            errs = validate(s, photos, ctx)                      # vitazny hook moze zopakovat cislo z dalsich beatov
        if not errs:
            narr = f"On-screen title: {s['hook_title']}\n" + "\n".join(b["text"] for b in s["beats"])
            errs = llm([{"role": "system", "content": CHECK},
                        {"role": "user", "content": f"Article:\n{fact['extract']}{side}\n\nNarration:\n{narr}"}], temp=0.1).get("problems") or []
            errs = [f"fact: {e}" for e in errs]
        if not errs:
            log(f"   scenar OK (pokus {att + 1})")
            return s
        log(f"   pokus {att + 1}: " + " | ".join(errs)[:400])
        msgs = msgs[:2] + [{"role": "assistant", "content": json.dumps(s)},   # len posledny navrh (Groq 8000 tok/min)
                           {"role": "user", "content": "Fix these problems and return the full JSON again:\n- " + "\n- ".join(errs)}]
    sys.exit("scenar nepresiel kontrolou ani na 8. pokus")


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
    for r in range(n):
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
        found = [i for i in ids if re.search(r"llama-4|scout|maverick|vision|[-_]vl|gemma-3|pixtral", i, re.I)]
        log(f"   vision kandidati: {found or 'ziadny'} (z {len(ids)} modelov)")
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


# ---------------------------------------------------------------- spec pre engine
def z_for(lat, km):
    """zoom, pri ktorom utvar zaberie ~80 % sirky (1080 px)."""
    return math.log2(156543.03 * math.cos(math.radians(lat)) * 1080 * 0.8 / (km * 1000))


def build(fact, s, photos, scale=None, shape=None, no=None):
    lat, lon = fact["lat"], fact["lon"]
    km = float(s["feature_km"])
    zf = max(4.5, min(Z_MAX - 1.0, z_for(lat, km) - 0.35))     # cely utvar aj s okolim (~60 % sirky)
    zs = {"feature": zf, "close": min(Z_MAX, zf + 0.9), "wide": max(4.5, zf - 1.8), "space": max(4.5, zf - 5.0)}
    def cut(t, n):                                           # skratit na cele slova, nie "FROM SPAC"
        t = t.upper().strip()
        return t if len(t) <= n else t[:n + 1].rsplit(" ", 1)[0]
    beats, nfeat, wide_used = [], 0, False
    for i, b in enumerate(s["beats"]):
        shot = b.get("shot") if b.get("shot") in zs else "feature"
        if i == len(s["beats"]) - 1:
            shot = "space"
        elif shot == "space" or (shot == "wide" and (wide_used or i == 0)):
            shot = "feature"                                 # dalekych zaberov max 1, inak kamera "pumpuje"
        measured = (b.get("overlay") or {}).get("type") in ("ruler", "rings", "scale", "highlight")
        if measured:
            shot = "feature"                                 # pravitko/prstence sedia len na celom utvare
        wide_used |= shot == "wide"
        z = zs[shot]
        if shot == "feature" and not measured:
            z += min(0.3, 0.1 * nfeat); nfeat += 1           # pomaly najazd, nie skoky
        nb = {"text": b["text"], "cam": {"lat": lat, "lon": lon, "z": round(min(Z_MAX, z), 2)}}
        if i == 0:
            nb["globe"] = True
        o = b.get("overlay") if i else None                  # v 1. zabere leti kamera z globusu, overlay by bol mrnavy
        if o and o.get("type") == "ruler":
            nb["ruler"] = {"lat": lat, "lon": lon, "km": km, "label": o.get("label") or f"{km:g} KM", "on": o["on"]}
        elif o and o.get("type") == "rings":
            nb["rings"] = {"lat": lat, "lon": lon, "km": [round(km / 2 * f, 2) for f in (0.3, 0.6, 0.9)], "on": o["on"]}
        elif o and o.get("type") == "scale" and scale:
            nb["scale"] = {"name": scale["city"]["name"], "poly_km": scale["city"]["poly_km"], "on": o["on"]}
        elif o and o.get("type") == "highlight":
            nb["highlight"] = {"on": o["on"]}
        elif o and o.get("type") == "tag":
            nb["tag"] = {"lat": lat, "lon": lon, "label": cut(o.get("label", ""), 18), "on": o["on"]}
        elif o and o.get("type") == "stamp":
            lab = re.sub(r"\bMYA\b", "MILLION YEARS AGO", o.get("label", "").upper())
            nb["stamp"] = {"label": cut(re.sub(r"\bBYA\b", "BILLION YEARS AGO", lab), 26), "on": o["on"]}
        r = b.get("react")
        if r and r.get("expr") in ("surprised", "happy"):
            nb["react"] = {"expr": r["expr"], "on": r["on"], "dur": 1.4}
        p = b.get("photo")
        if p and 0 < i < len(s["beats"]) - 1:
            ph = photos[p["index"]]
            nb["photo"] = {"file": ph["file"], "label": cut(p.get("label", ""), 22), "credit": ph["credit"],
                           "on": p["on"], "dur": 2.8}
        beats.append(nb)
    used = [photos[b["photo"]["index"]] for b in s["beats"] if b.get("photo")]
    credits = "Imagery: Esri, Maxar, Earthstar Geographics." + (
        " Photos: " + "; ".join(sorted({p["credit"] for p in used})) + ", Wikimedia Commons." if used else "")
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    return {"title": s.get("title") or fact["title"], "coords": f"{abs(lat):.4f} {ns}, {abs(lon):.4f} {ew}",
            "voice": "am_michael", "speed": 1.0, "music": "cine_616.mp3", "start": {"lat": lat, "lon": lon},
            "source": fact["url"], "feature_km": km, "beats": beats, "hook": cut(s.get("hook_title", ""), 22),
            "description": f"{s.get('description', '').strip()} {credits} Source: Wikipedia.",
            "hashtags": (s.get("hashtags") or ["#shorts"])[:6], "shape": shape, "series_no": no}


def main():
    qp = os.path.join(TOP, "queue.json")
    queue = json.load(open(qp, encoding="utf-8"))
    slug, km = (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None), None
    for x in ([] if slug else [x for x in queue if x["status"] == "todo"]):
        km = feature_size(json.load(open(os.path.join(TOP, "facts", x["slug"] + ".json"), encoding="utf-8")))
        if km and km < 0.25:                                      # zo satelitu len bodka (Darvaza 70 m) -> preskocit
            log(f"   {x['slug']}: {km} km, primale, preskakujem")
            x["status"] = "skip"
            continue
        slug = x["slug"]
        break
    q = next(q for q in queue if q["slug"] == slug)
    fact = json.load(open(os.path.join(TOP, "facts", slug + ".json"), encoding="utf-8"))
    fact["lat"], fact["lon"] = q["lat"], q["lon"]          # queue ma aj rucne opravene suradnice
    log(f"tema: {fact['title']} ({q['lat']:.4f}, {q['lon']:.4f})")
    dp = os.path.join(HERE, "drafts", slug + ".json")
    if os.environ.get("ORBIT_REBUILD") == "1" and os.path.exists(dp):   # len prepocitat kameru/overlaye, text ostava
        d = json.load(open(dp, encoding="utf-8"))
        s, photos = d["draft"], d["photos"]
        log("   prerender z ulozeneho navrhu")
        shape, scale = d.get("shape"), d.get("scale")
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
        log(f"   velkost {km} km, porovnanie: {scale['fact'] if scale else 'ziadne'}")
        nq = next((x for x in queue if x["status"] == "todo" and x["slug"] != slug and
                   os.path.exists(os.path.join(TOP, "facts", x["slug"] + ".json"))), None)
        nxt = json.load(open(os.path.join(TOP, "facts", nq["slug"] + ".json"), encoding="utf-8")) if nq else None
        s = write(fact, photos, scale, nxt, km)
        if not ok:
            lat, lon, ok = locate(fact, q["lat"], q["lon"], float(s["feature_km"]))
        if not q.get("located"):
            log(f"   stred utvaru: {lat}, {lon} (Wikipedia {q['lat']}, {q['lon']}){'' if ok else ' - NEDOROVNANE'}")
            fact["lat"], fact["lon"] = q["lat"], q["lon"] = lat, lon
            q["located"] = ok
    q["no"] = q.get("no") or 1 + max(x.get("no") or 0 for x in queue)   # cislo dielu serie
    download(photos, slug, {b["photo"]["index"] for b in s["beats"] if b.get("photo")})
    os.makedirs(os.path.join(HERE, "drafts"), exist_ok=True)       # surovy navrh: prerender bez noveho pisania
    json.dump({"draft": s, "photos": photos, "lat": fact["lat"], "lon": fact["lon"], "shape": shape, "scale": scale},
              open(os.path.join(HERE, "drafts", slug + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    spec = build(fact, s, photos, scale, shape, q["no"])
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

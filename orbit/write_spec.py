"""ORBIT: napise spec videa z Wikipedie (Groq, zadarmo) + fotky z Wikimedia Commons + kontrola faktov.
python orbit/write_spec.py [slug]   (bez slugu = dalsia "todo" tema z topics/queue.json)
-> orbit/specs/<slug>.json, orbit/photos/<slug>/pN.jpg. Kameru (zoom) pocita kod z velkosti utvaru, nie model."""
import html, json, math, os, re, sys, time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.join(HERE, "topics")
UA = {"User-Agent": "CurioBot/1.0 (https://github.com/brockai667/ScienceFactory) python-requests"}
CTA = "Follow for more places you can see from space."
Z_MAX = 16.8                  # Esri ma ostre snimky vsade len priblizne do z17


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- LLM (Groq, OpenAI-kompatibilne)
def llm(messages, temp=0.7):
    base = os.environ.get("MODELS_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    tok = os.environ["MODELS_TOKEN"]
    for model in (os.environ.get("MODELS_MODEL", "openai/gpt-oss-120b"), os.environ.get("MODELS_FALLBACK", "openai/gpt-oss-20b")):
        for a in range(5):
            wait = 8 * (a + 1)
            try:
                r = requests.post(base + "/chat/completions", headers={"Authorization": "Bearer " + tok},
                                  json={"model": model, "messages": messages, "temperature": temp,
                                        "response_format": {"type": "json_object"}}, timeout=180)
                if r.status_code == 200:
                    return json.loads(r.json()["choices"][0]["message"]["content"])
                m = re.search(r"try again in ([0-9.]+)s", r.text)     # Groq free: 8000 tokenov/min
                if r.status_code == 429 and m:
                    wait = float(m.group(1)) + 2
                log(f"   llm {model} {r.status_code}, cakam {wait:.0f} s")
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
SYSTEM = """You write narration for a 35-45 second vertical video about a place seen on a satellite map.
A cute satellite robot narrates while the camera flies from a globe down to the place.

Structure:
- 8 or 9 beats, 95 to 120 words in total. Short spoken sentences (max 16 words), plain English.
- Beat 1 is the hook: tell viewers to type these coordinates into a satellite map and what strange thing they will find, and where. Never say the coordinate numbers (they are typed on screen).
- Beats 2-4 build curiosity: what it looks like, how big it is, the popular myth or wild guess (only if the article mentions one; otherwise ask the question the viewer is thinking, like "So what could make a ring this big?").
- Beats 5-7 give the real answer step by step, then one surprising detail.
- Then one short payoff line that ties back to the hook. Do not repeat a sentence, name or nickname you already used.
- The last beat is exactly: "%s"

Example of the tone (a different place):
1 "Type these coordinates into a satellite map, and you'll find something strange in the middle of the Sahara."
2 "A giant eye, forty kilometers wide. Astronauts use it as a landmark from space."
3 "Perfect rings, one inside another."
4 "Some people say this is the lost city of Atlantis."
5 "But the truth is way older. About a hundred million years ago, molten rock pushed the ground up into a giant dome."
6 "Then wind and rain wore it down, layer by layer, until only these rings were left."
7 "The Eye of the Sahara isn't a lost city. It's the inside of an ancient dome, laid open by the wind."

Written for the ear (a voice reads it):
- Numbers as people say them: "about seventy kilometers", "two hundred fourteen million years ago", "almost a kilometer high". No decimals, no symbols or unit signs (no km, m, %%, ³, ~), no brackets, no em dashes. Plain ASCII quotes and hyphens.

Facts:
- Use ONLY facts written in the article. Every number, date, name and claim must be in the article. No guessing, no rounding up to sound bigger.
- Never invent a myth, rumor or what "some people" say, think or wonder. If the article has no myth, use a question instead.

Visual cues (each "on" is ONE word copied exactly from that beat's text, where the cue appears):
- shot per beat: "feature" (whole place fills the screen), "close" (zoomed in on detail), "wide" (zoomed out to see the surroundings), "space" (far away, only for the last beat).
- overlay (at most one per beat, use 3 or 4 in total; labels in plain words, no abbreviations like MYA or KM2): {"type":"ruler","on":word,"label":"40 KM"} for the size (label must match feature_km), {"type":"rings","on":word} only if the place is round, {"type":"tag","on":word,"label":"SHORT WORDS?"} to pin a myth or name, {"type":"stamp","on":word,"label":"SHORT DATE OR FACT"}.
- react (2 or 3 in the whole video, the robot's face reacts): {"expr":"surprised" or "happy","on":word}. Surprised on the most shocking fact, happy on the payoff or the last beat.
- photo (use 1 or 2 if the list has photos that clearly show this place, never in beat 1 or the last beat): {"index":N,"label":"SHORT CAPTION","on":word} using a photo from the list.

Return JSON: {"title": str, "feature_km": number (size of the main thing visible from above, in km, from the article),
"beats": [{"text": str, "shot": str, "overlay": obj or null, "react": obj or null, "photo": obj or null}],
"description": str (2 sentences, facts only), "hashtags": [5 strings starting with #]}""" % CTA

CHECK = """You are a fact checker for a short narrated video about a place seen on a satellite map.
Flag a sentence only if it states a FACT that is false or not in the article:
- a number, size, height, depth, date or age that differs from the article (rounding with "about"/"almost" is fine),
- a name, nickname, cause, record or event the article does not give,
- anything about what people or scientists say, call it, think, wonder or believe, unless the article says it.
Never flag: describing how it looks on the satellite image (shapes, colors, "looks like an eye", "from space"), telling viewers to type coordinates,
questions, simple plain-language wording of what the article says, the closing "Follow for more" line.
Return JSON: {"problems": [str]}, one short line per false or invented fact. Empty list if there are none."""


def validate(s, photos):
    errs = []
    bs = s.get("beats") or []
    if not 8 <= len(bs) <= 9:
        errs.append(f"need 8 or 9 beats, got {len(bs)}")
    words = sum(len(b.get("text", "").split()) for b in bs)
    if not 90 <= words <= 125:
        errs.append(f"need 95-120 words, got {words}")
    for i, b in enumerate(bs):
        bad = re.findall(r"[0-9]+[.,][0-9]+|[%~()²³]|\bkm\b|[0-9] ?m\b", b.get("text", ""))
        if bad:
            errs.append(f"beat {i + 1} is not written for the ear ({', '.join(bad)}): spell numbers and units as words")
    if sum(1 for b in bs if b.get("react")) < 2:
        errs.append("use 2 or 3 react cues")
    if sum(1 for b in bs if b.get("overlay")) < 3:
        errs.append("use 3 or 4 overlays")
    if photos and not any(b.get("photo") for b in bs):
        errs.append("use at least 1 photo from the list")
    if bs and bs[-1].get("text", "").strip() != CTA:
        errs.append("last beat must be exactly the CTA")
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


def write(fact, photos):
    plist = "\n".join(f"{i}: {p['desc']}" for i, p in enumerate(photos)) or "(no photos)"
    user = f"Place: {fact['title']}\nCoordinates: {fact['lat']:.4f}, {fact['lon']:.4f}\n\nPhotos:\n{plist}\n\nArticle:\n{fact['extract']}"
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    for att in range(6):
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
        errs = validate(s, photos)
        if len(s.get("beats") or []) < 6:                    # rozbity navrh: neopravovat, zacat odznova
            log(f"   pokus {att + 1}: rozbity navrh, odznova")
            msgs = msgs[:2]
            continue
        if not errs:
            narr = "\n".join(b["text"] for b in s["beats"])
            errs = llm([{"role": "system", "content": CHECK},
                        {"role": "user", "content": f"Article:\n{fact['extract']}\n\nNarration:\n{narr}"}], temp=0.1).get("problems") or []
            errs = [f"fact: {e}" for e in errs]
        if not errs:
            log(f"   scenar OK (pokus {att + 1})")
            return s
        log(f"   pokus {att + 1}: " + " | ".join(errs)[:400])
        msgs = msgs[:2] + [{"role": "assistant", "content": json.dumps(s)},   # len posledny navrh (Groq 8000 tok/min)
                           {"role": "user", "content": "Fix these problems and return the full JSON again:\n- " + "\n- ".join(errs)}]
    sys.exit("scenar neprešiel kontrolou ani na 6. pokus")


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


def build(fact, s, photos):
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
        measured = (b.get("overlay") or {}).get("type") in ("ruler", "rings")
        if measured:
            shot = "feature"                                 # pravitko/prstence sedia len na celom utvare
        wide_used |= shot == "wide"
        z = zs[shot]
        if shot == "feature" and not measured:
            z += min(0.3, 0.1 * nfeat); nfeat += 1           # pomaly najazd, nie skoky
        nb = {"text": b["text"], "cam": {"lat": lat, "lon": lon, "z": round(min(Z_MAX, z), 2)}}
        if i == 0:
            nb["globe"] = True
        o = b.get("overlay")
        if o and o.get("type") == "ruler":
            nb["ruler"] = {"lat": lat, "lon": lon, "km": km, "label": o.get("label") or f"{km:g} KM", "on": o["on"]}
        elif o and o.get("type") == "rings":
            nb["rings"] = {"lat": lat, "lon": lon, "km": [round(km / 2 * f, 2) for f in (0.3, 0.6, 0.9)], "on": o["on"]}
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
            "source": fact["url"], "feature_km": km, "beats": beats,
            "description": f"{s.get('description', '').strip()} {credits} Source: Wikipedia.",
            "hashtags": (s.get("hashtags") or ["#shorts"])[:6]}


def main():
    qp = os.path.join(TOP, "queue.json")
    queue = json.load(open(qp, encoding="utf-8"))
    slug = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else next(q["slug"] for q in queue if q["status"] == "todo")
    q = next(q for q in queue if q["slug"] == slug)
    fact = json.load(open(os.path.join(TOP, "facts", slug + ".json"), encoding="utf-8"))
    fact["lat"], fact["lon"] = q["lat"], q["lon"]          # queue ma aj rucne opravene suradnice
    log(f"tema: {fact['title']} ({q['lat']:.4f}, {q['lon']:.4f})")
    dp = os.path.join(HERE, "drafts", slug + ".json")
    if os.environ.get("ORBIT_REBUILD") == "1" and os.path.exists(dp):   # len prepocitat kameru/overlaye, text ostava
        d = json.load(open(dp, encoding="utf-8"))
        s, photos = d["draft"], d["photos"]
        log("   prerender z ulozeneho navrhu")
    else:
        photos = commons_photos(fact["title"], q["lat"], q["lon"])
        log(f"   fotky z Commons: {len(photos)}")
        s = write(fact, photos)
    if not q.get("located"):
        lat, lon, ok = locate_osm(fact["title"], q["lat"], q["lon"])
        if not ok:
            lat, lon, ok = locate(fact, q["lat"], q["lon"], float(s["feature_km"]))
        log(f"   stred utvaru: {lat}, {lon} (Wikipedia {q['lat']}, {q['lon']}){'' if ok else ' - NEDOROVNANE'}")
        fact["lat"], fact["lon"] = q["lat"], q["lon"] = lat, lon
        q["located"] = ok
    download(photos, slug, {b["photo"]["index"] for b in s["beats"] if b.get("photo")})
    os.makedirs(os.path.join(HERE, "drafts"), exist_ok=True)       # surovy navrh: prerender bez noveho pisania
    json.dump({"draft": s, "photos": photos, "lat": fact["lat"], "lon": fact["lon"]},
              open(os.path.join(HERE, "drafts", slug + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    spec = build(fact, s, photos)
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

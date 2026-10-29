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
        for a in range(3):
            try:
                r = requests.post(base + "/chat/completions", headers={"Authorization": "Bearer " + tok},
                                  json={"model": model, "messages": messages, "temperature": temp,
                                        "response_format": {"type": "json_object"}}, timeout=180)
                if r.status_code == 200:
                    return json.loads(r.json()["choices"][0]["message"]["content"])
                log(f"   llm {model} {r.status_code}: {r.text[:200]}")
            except (requests.RequestException, ValueError, KeyError) as e:
                log(f"   llm {model} chyba: {e}")
            time.sleep(8 * (a + 1))
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
- 7 to 9 beats, 85 to 120 words in total. Short spoken sentences, plain English, no em dashes.
- Beat 1 is the hook: tell viewers to type the coordinates into a satellite map, say what they will find and where, and make them curious.
- Then: what it looks like and how big it is, then the popular myth or the obvious wrong guess (if the article has one), then the real explanation, then one surprising detail, then a short payoff line.
- The last beat is exactly: "%s"

Facts:
- Use ONLY facts written in the article. Every number, date, name and claim must be in the article. No guessing, no rounding up to sound bigger.

Visual cues (each "on" is ONE word copied exactly from that beat's text, where the cue appears):
- shot per beat: "feature" (whole place fills the screen), "close" (zoomed in on detail), "wide" (zoomed out to see the surroundings), "space" (far away, only for the last beat).
- overlay (optional, at most one per beat, use 2 to 4 in total): {"type":"ruler","on":word,"label":"40 KM"} for the size (label must match feature_km), {"type":"rings","on":word} only if the place is round, {"type":"tag","on":word,"label":"SHORT WORDS?"} to pin a myth or name, {"type":"stamp","on":word,"label":"SHORT DATE OR FACT"}.
- react (optional, 2 or 3 in the whole video): {"expr":"surprised" or "happy","on":word}.
- photo (optional, at most 2 in the video, never in beat 1 or the last beat): {"index":N,"label":"SHORT CAPTION","on":word} using a photo from the list.

Return JSON: {"title": str, "feature_km": number (size of the main thing visible from above, in km, from the article),
"beats": [{"text": str, "shot": str, "overlay": obj or null, "react": obj or null, "photo": obj or null}],
"description": str (2 sentences, facts only), "hashtags": [5 strings starting with #]}""" % CTA

CHECK = """You are a strict fact checker. Compare every claim in the narration with the article.
List each claim that is not clearly supported by the article (wrong number, wrong date, invented detail, exaggeration).
Return JSON: {"problems": [str]}. Empty list if everything is supported."""


def validate(s, photos):
    errs = []
    bs = s.get("beats") or []
    if not 7 <= len(bs) <= 9:
        errs.append(f"need 7-9 beats, got {len(bs)}")
    words = sum(len(b.get("text", "").split()) for b in bs)
    if not 80 <= words <= 130:
        errs.append(f"need 85-120 words, got {words}")
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
    for att in range(4):
        s = llm(msgs)
        errs = validate(s, photos)
        if not errs:
            narr = "\n".join(b["text"] for b in s["beats"])
            errs = llm([{"role": "system", "content": CHECK},
                        {"role": "user", "content": f"Article:\n{fact['extract']}\n\nNarration:\n{narr}"}], temp=0.1).get("problems") or []
            errs = [f"fact: {e}" for e in errs]
        if not errs:
            log(f"   scenar OK (pokus {att + 1})")
            return s
        log(f"   pokus {att + 1}: " + " | ".join(errs)[:400])
        msgs += [{"role": "assistant", "content": json.dumps(s)},
                 {"role": "user", "content": "Fix these problems and return the full JSON again:\n- " + "\n- ".join(errs)}]
    sys.exit("scenar neprešiel kontrolou ani na 4. pokus")


# ---------------------------------------------------------------- spec pre engine
def z_for(lat, km):
    """zoom, pri ktorom utvar zaberie ~80 % sirky (1080 px)."""
    return math.log2(156543.03 * math.cos(math.radians(lat)) * 1080 * 0.8 / (km * 1000))


def build(fact, s, photos):
    lat, lon = fact["lat"], fact["lon"]
    km = float(s["feature_km"])
    zf = max(4.5, min(Z_MAX - 1.0, z_for(lat, km)))
    zs = {"feature": zf, "close": min(Z_MAX, zf + 1.0), "wide": max(4.5, zf - 2.0), "space": max(4.5, zf - 5.0)}
    beats, nfeat = [], 0
    for i, b in enumerate(s["beats"]):
        shot = b.get("shot") if b.get("shot") in zs else "feature"
        if i == len(s["beats"]) - 1:
            shot = "space"
        z = zs[shot]
        if shot == "feature":
            z += 0.2 * nfeat; nfeat += 1                     # kazdy dalsi zaber kusok blizsie
        nb = {"text": b["text"], "cam": {"lat": lat, "lon": lon, "z": round(min(Z_MAX, z), 2)}}
        if i == 0:
            nb["globe"] = True
        o = b.get("overlay")
        if o and o.get("type") == "ruler":
            nb["ruler"] = {"lat": lat, "lon": lon, "km": km, "label": o.get("label") or f"{km:g} KM", "on": o["on"]}
        elif o and o.get("type") == "rings":
            nb["rings"] = {"lat": lat, "lon": lon, "km": [round(km * f, 2) for f in (0.13, 0.26, 0.39)], "on": o["on"]}
        elif o and o.get("type") == "tag":
            nb["tag"] = {"lat": lat, "lon": lon, "label": o.get("label", "")[:18].upper(), "on": o["on"]}
        elif o and o.get("type") == "stamp":
            nb["stamp"] = {"label": o.get("label", "")[:26].upper(), "on": o["on"]}
        r = b.get("react")
        if r and r.get("expr") in ("surprised", "happy"):
            nb["react"] = {"expr": r["expr"], "on": r["on"], "dur": 1.4}
        p = b.get("photo")
        if p and 0 < i < len(s["beats"]) - 1:
            ph = photos[p["index"]]
            nb["photo"] = {"file": ph["file"], "label": p.get("label", "")[:22].upper(), "credit": ph["credit"],
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
    photos = commons_photos(fact["title"], q["lat"], q["lon"])
    log(f"   fotky z Commons: {len(photos)}")
    s = write(fact, photos)
    download(photos, slug, {b["photo"]["index"] for b in s["beats"] if b.get("photo")})
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

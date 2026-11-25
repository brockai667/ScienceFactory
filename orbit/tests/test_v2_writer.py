"""Offline test v2 pisania (bez LLM tokenu a bez siete).
python -I -X utf8 orbit/tests/test_v2_writer.py
1) build() v2 z navrhov podla rucnych dielov #011-#020, 2) validate_v2 dobry/zle navrhy, 3) publish.texts(),
4) stary v1 build()/validate() = verzia z HEAD (git show), 5) kamera v2 cez orbit_engine.camera_track (bez renderu)."""
import copy, json, os, re, subprocess, sys, types

ORBIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ORBIT)
sys.path.insert(0, ORBIT)
sys.path.insert(0, ROOT)
import write_spec as W   # noqa: E402
import publish as P      # noqa: E402


def no_net(*a, **k):
    raise AssertionError("test nesmie volat LLM ani siet")


W.llm = W.vision = W.commons_photos = W.locate_osm = W.osm_shape = no_net
W.requests = types.SimpleNamespace(get=no_net, post=no_net, RequestException=Exception)


def load(p):
    return json.load(open(os.path.join(ORBIT, p), encoding="utf-8"))


def head_module(path, name):
    """povodny subor z HEAD ako modul (HERE ukazuje do orbit/, aby nasiel topics/)"""
    src = subprocess.run(["git", "show", f"HEAD:orbit/{path}"], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8")
    m = types.ModuleType(name)
    m.__file__ = os.path.join(ORBIT, path)
    exec(compile(src, name, "exec"), m.__dict__)
    return m


def tok(t):
    return [re.sub(r"[^a-z0-9']", "", w.lower()) for w in t.split()]


# ---------------------------------------------------------------- navrhy v2 z rucnych dielov
REF = {"surtsey": ("surtsey", "surtsey"), "meteor_crater": ("meteor_crater", "meteor"),     # spec: (facts, photos/)
       "great_salt_lake": ("great_salt_lake", "saltlake"), "kawah_ijen": ("ijen", "ijen"),
       "palm_jumeirah": ("palm_jumeirah", "palm"), "grand_prismatic_spring": ("grand_prismatic_spring", "prismatic"),
       "manicouagan_ring": ("manicouagan_reservoir", "mani"), "hashima_island": ("hashima_island", "hashima")}
BUILD = ("surtsey", "meteor_crater", "great_salt_lake")
GOOD = [k for k in REF if k != "great_salt_lake"]   # rucny #016 opakuje cislo "two" a nema reakciu -> validator ho vrati


def draft_from_ref(slug):
    fslug, pdir = REF[slug]
    ref = load(f"specs/{slug}.json")
    photos = load(f"photos/{pdir}/credits.json")
    files = [p["file"] for p in photos]
    beats = []
    for i, b in enumerate(ref["beats"]):
        nb = {"text": b["text"], "overlay": None, "react": None, "photo": None}
        if i == 0 and "rings" in b:
            nb["overlay"] = {"type": "rings", "on": b["rings"]["on"]}
        for k in ("ruler", "stamp", "tag"):
            if i and k in b and not nb["overlay"]:
                nb["overlay"] = {"type": k, "on": b[k]["on"], **({"label": b[k]["label"]} if "label" in b[k] else {})}
        if "react" in b:
            nb["react"] = {"expr": b["react"]["expr"], "on": b["react"]["on"]}
        if "photo" in b and b["photo"]["file"] in files:
            nb["photo"] = {"index": files.index(b["photo"]["file"]), "label": b["photo"]["label"], "on": b["photo"]["on"]}
        beats.append(nb)
    desc = re.sub(r"\s[^.?!]*\?$", "", ref["description"].split(" Imagery:")[0])
    s = {"title": ref["title"], "feature_km": ref["feature_km"], "beats": beats, "v2": True,
         "hooks": [{"text": beats[0]["text"], "title": ref["hook"]}, {"text": beats[0]["text"], "title": ref["hook"]}],
         "hook_title": ref["hook"], "question": ref.get("outro_text") or ["WOULD YOU", "GO THERE?"],
         "description": desc, "hashtags": ref["hashtags"]}
    fact = load(f"topics/facts/{fslug}.json")
    fact["lat"], fact["lon"] = ref["start"]["lat"], ref["start"]["lon"]
    return fact, s, photos, ref


def check_v2_spec(spec, s, no):
    assert spec["v2"] is True and spec["outro"] == "loop", "v2/outro"
    assert len(spec["beats"]) == 7, len(spec["beats"])
    b0 = spec["beats"][0]
    assert "rings" in b0 and b0["rings"]["km"][0] > 0, "kruh na beate 1"
    assert ("outro_text" in spec) == (no % 2 == 1), "otazka len pri neparnych"
    assert spec["tail"] == 1.4 and spec["fly0"] == 1.3 and spec["hook"]
    cams = [(b["cam"]["lat"], b["cam"]["lon"], b["cam"]["z"]) for b in spec["beats"]]
    assert len(set(cams)) == 7, f"kamera sa opakuje: {cams}"
    for b in spec["beats"]:
        assert not W.SIGNOFF_RX.search(b["text"]) and "?" not in b["text"], b["text"]
        for c in [b["cam"]] + b.get("moves", []):
            assert W.V2_ZOOM[0] <= c["z"] <= W.V2_ZOOM[1], f"zoom {c['z']}"
        t = tok(b["text"])
        cues = [b[k] for k in ("rings", "ruler", "tag", "stamp", "photo", "react", "impact", "highlight") if k in b]
        cues += b.get("fx", []) + b.get("moves", [])
        for c in cues:
            if c.get("on") is not None:
                assert re.sub(r"[^a-z0-9']", "", str(c["on"]).lower()) in t, f"'{c['on']}' nie je v: {b['text']}"
    assert "photo" in spec["beats"][1] or not any(x.get("photo") for x in s["beats"]), "dokaz (foto) v beate 2"
    last = spec["beats"][-1]
    assert last["moves"] and last["moves"][0]["z"] < last["cam"]["z"] and last["cam"]["lat"] == spec["start"]["lat"], "odlet na cely utvar"
    assert not {t.lower() for t in spec["hashtags"]} & {"#orbit", "#shorts"}, spec["hashtags"]
    d = spec["description"]
    assert d.startswith(s["description"]) and "Imagery: Esri, Maxar, Earthstar Geographics." in d and d.endswith("Source: Wikipedia."), d
    assert ("Photo" in d) == any("photo" in b for b in spec["beats"])


results = []


def test(name):
    def deco(fn):
        try:
            fn()
            results.append((name, "PASS", ""))
        except Exception as e:                               # noqa: BLE001
            results.append((name, "FAIL", f"{type(e).__name__}: {e}"))
        return fn
    return deco


@test("1 build_v2 z navrhov (surtsey, meteor_crater, great_salt_lake), neparny aj parny diel")
def _():
    for slug in BUILD:
        fact, s, photos, ref = draft_from_ref(slug)
        for no in (21, 22):
            spec = W.build(fact, copy.deepcopy(s), photos, None, None, no, None)
            check_v2_spec(spec, s, no)
            assert spec == W.build(fact, copy.deepcopy(s), photos, None, None, no, None), "build nie je deterministicky"
        assert set(spec) >= set(ref) - {"imagery_release", "imagery_minz", "outro_text"}, set(ref) - set(spec)


@test("2a validate_v2: navrhy z 7 rucnych dielov prejdu, #016 (great_salt_lake) nie")
def _():
    fact, s, photos, _ = draft_from_ref("great_salt_lake")
    assert W.validate_v2(s, photos, {"article": fact["extract"], "scale": None, "next": None})
    for slug in GOOD:
        fact, s, photos, _ = draft_from_ref(slug)
        errs = W.validate_v2(s, photos, {"article": fact["extract"], "scale": None, "next": None})
        assert not errs, f"{slug}: {errs}"


@test("2b validate_v2: zle navrhy neprejdu (8 beatov, sign-off, Next target, dlhy, otazka, chyba foto)")
def _():
    fact, s, photos, _ = draft_from_ref("surtsey")
    ctx = {"article": fact["extract"], "scale": None, "next": None}
    def bad(fn, want):
        x = copy.deepcopy(s); fn(x)
        errs = W.validate_v2(x, photos, ctx)
        assert any(re.search(want, e) for e in errs), f"chyba '{want}' nenajdena: {errs}"
    bad(lambda x: x["beats"].append({"text": "Scientists still visit it every summer.", "overlay": None, "react": None, "photo": None}),
        r"exactly 7 beats")
    bad(lambda x: x["beats"][-1].update(text="Follow for the next scan. Orbi out."), r"signs off")
    bad(lambda x: x["beats"][-1].update(text="Next target: a lake that is pink."), r"signs off")
    bad(lambda x: [b.update(text=b["text"] + " It is a small island near the coast of Iceland today.") for b in x["beats"][2:6]],
        r"need 70-88 words|longer than 16")
    bad(lambda x: x["beats"][2].update(text="So what made this island rise?"), r"is a question")
    bad(lambda x: x["beats"][1].update(photo=None), r"beat 2 needs a photo")
    bad(lambda x: x.update(question=["would you go"]), r'"question"')


@test("3 publish.texts: v2 bez zdvojeneho haku, #orbit raz; v1 bajt po bajte ako HEAD")
def _():
    sp = load("specs/surtsey.json")
    _, cap = P.texts(sp)
    assert cap.count("This island did not exist before") == 1, cap
    assert cap.lower().count("#orbit") == 1 and cap.count("#shorts") == 1 and cap.endswith("#orbit #shorts"), cap
    old = head_module("publish.py", "publish_head")
    n = 0
    for f in sorted(os.listdir(os.path.join(ORBIT, "specs"))):
        spec = load(f"specs/{f}")
        if spec.get("v2"):
            continue
        tags = [t.lower() for t in spec.get("hashtags") or []]
        if len(set(tags)) == len(tags) and not set(tags) & {"#orbit", "#shorts"}:
            assert P.texts(spec) == old.texts(spec), f
            n += 1
    assert n >= 5, f"len {n} v1 specov"
    v1 = load("specs/area_51.json")
    assert P.texts(v1)[1].startswith(v1["beats"][0]["text"] + "\n\n")


@test("4 v1 build()/validate()/SYSTEM = HEAD pre vsetky navrhy zo zasoby (orbit/bank)")
def _():
    old = head_module("write_spec.py", "write_spec_head")
    assert old.SYSTEM == W.SYSTEM
    for m in (old,):
        m.llm = m.vision = no_net
    n = 0
    for f in sorted(os.listdir(os.path.join(ORBIT, "bank"))):
        bk = load(f"bank/{f}")
        if not isinstance(bk, dict) or not bk.get("draft"):
            continue
        slug = f[:-5]
        fact = load(f"topics/facts/{slug}.json")
        fact["lat"], fact["lon"] = bk["lat"], bk["lon"]
        photos = copy.deepcopy(bk["photos"])
        for i in {b["photo"]["index"] for b in bk["draft"]["beats"] if b.get("photo")}:
            photos[i]["file"] = f"photos/{slug}/p{i}.jpg"            # co by dorobil download()
        q = {x["slug"]: x for x in load("topics/queue.json")}
        nq = q.get(bk.get("next"))
        args = (fact, bk["draft"], photos, bk["scale"], bk["shape"], 7, (nq["lat"], nq["lon"]) if nq else None)
        a, b = old.build(*copy.deepcopy(args)), W.build(*copy.deepcopy(args))
        assert json.dumps(a, sort_keys=False) == json.dumps(b, sort_keys=False), f"{slug}: v1 build sa zmenil"
        nxt = load(f"topics/facts/{nq['slug']}.json") if nq and os.path.exists(os.path.join(ORBIT, "topics/facts", nq["slug"] + ".json")) else None
        ctx = {"article": fact["extract"], "scale": bk["scale"], "next": nxt}
        assert old.validate(bk["draft"], photos, ctx) == W.validate(bk["draft"], photos, ctx), f"{slug}: v1 validate sa zmenil"
        assert old.prompt(fact, photos, bk["scale"], nxt, bk.get("km")) == W.prompt(fact, photos, bk["scale"], nxt, bk.get("km"))
        n += 1
    assert n >= 5, f"len {n} navrhov"


@test("5 visible(): primaly utvar hned nie; zlyhany model -> statistika obrazka")
def _():
    fact = load("topics/facts/darvaza_gas_crater.json")
    ok, why = W.visible(fact, 40.2525, 58.4396, 0.07)
    assert not ok and "bodka" in why, why
    import numpy as np, cv2
    flat = cv2.imencode(".jpg", np.full((768, 768, 3), 120, np.uint8))[1].tobytes()
    assert W.img_score(flat) <= 1.5, W.img_score(flat)
    snap, real = W.snapshot, W.vision
    try:                                                     # zaber z cache dlazdic (Surtsey), model nedostupny
        W.vision = lambda *a, **k: None
        W.snapshot = lambda *a, **k: flat
        ok, why = W.visible(load("topics/facts/surtsey.json"), 63.303, -20.605, 1.5)
        assert not ok and "statistika" in why, why
    finally:
        W.snapshot, W.vision = snap, real


@test("6 kamera v2 v engine (camera_track): ziadny skok, kamera sa hybe v kazdom beate, slucka konci na globuse")
def _():
    import orbit_engine as E
    fact, s, photos, _ = draft_from_ref("surtsey")
    spec = W.build(fact, s, photos, None, None, 21, None)
    t, beats = 0.15, copy.deepcopy(spec["beats"])
    for b in beats:                                          # casy ako z TTS: ~2,6 slova/s pri speed 1.1
        b["t0"], t = t, t + len(b["text"].split()) / 2.6 + 0.25
        b["t1"] = t
    total = t + spec["tail"]
    cams = E.camera_track(spec, beats, total, ())
    assert len(cams) == int(-(-total * E.FPS // 1))
    jumps = [abs(cams[i + 1][2] - cams[i][2]) for i in range(len(cams) - 1)]
    land = int((E.GLOBE_T - 0.3 + spec["fly0"]) * E.FPS)
    out0 = int(E.out_times(spec, total)[0] * E.FPS)
    assert max(jumps[land:out0]) < 0.12, f"skok zoomu {max(jumps[land:out0]):.3f}"
    still = max(len(x) for x in re.split("1+", "".join("0" if (abs(cams[i + 1][0] - cams[i][0]) + abs(cams[i + 1][1] - cams[i][1]) < 1e-7
                                                                and jumps[i] < 1e-9) else "1" for i in range(land, out0))) or [""])
    assert still < 0.5 * E.FPS, f"kamera stoji {still} snimok"
    assert abs(cams[-1][2] - E.GLOBE_ZEND) < 0.3, cams[-1]
    print(f"   kamera: {len(cams)} snimok, {total:.1f} s, z {min(c[2] for c in cams[land:out0]):.2f}-{max(c[2] for c in cams[land:out0]):.2f}")


for name, st, msg in results:
    print(f"{st}  {name}" + (f"\n      {msg}" if msg else ""))
sys.exit(1 if any(st != "PASS" for _, st, _ in results) else 0)

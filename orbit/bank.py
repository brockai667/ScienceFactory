"""Zasoba rucne prepracovanych scenarov ORBIT (nocny beh ich berie namiesto Groq).
python orbit/bank.py prep N      pripravi zadania pre N dalsich tem v poradi serie -> orbit/bank/<slug>.json (bez "draft")
python orbit/bank.py check SLUG  skontroluje "draft" rovnakymi pravidlami ako write_spec.validate (vypise chyby)
python orbit/bank.py left        kolko scenarov este caka; 0 -> exit 1 (workflow posle mail "CURIO - doplnit scripty")
Zadanie (prompt) a pravidla su presne tie, ktore dostava Groq: write_spec.SYSTEM + "user"."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import write_spec as w

BANK = os.path.join(HERE, "bank")
QP = os.path.join(w.TOP, "queue.json")
KM = os.path.join(BANK, "km.json")                       # velkost utvaru (km) z clanku, rucne: {slug: km alebo null}


def km_of(slug, fact):
    """rucne precitana velkost (bez Groq kluca lokalne), inak ako nocny beh cez model."""
    known = json.load(open(KM, encoding="utf-8")) if os.path.exists(KM) else {}
    return known[slug] if slug in known else w.feature_size(fact)


def fact_of(slug, q):
    f = json.load(open(os.path.join(w.TOP, "facts", slug + ".json"), encoding="utf-8"))
    f["lat"], f["lon"] = q["lat"], q["lon"]
    return f


def order(queue, n):
    """dalsich n tem v poradi serie: najprv ta, ktoru slubil posledny diel, potom todo z fronty (bez primalych)."""
    last = max((x for x in queue if x.get("no") and x["status"] in ("written", "done")), key=lambda x: x["no"], default=None)
    lp = os.path.join(HERE, "drafts", last["slug"] + ".json") if last else ""
    promised = json.load(open(lp, encoding="utf-8")).get("next") if lp and os.path.exists(lp) else None
    todo = sorted((x for x in queue if x["status"] == "todo" and os.path.exists(os.path.join(w.TOP, "facts", x["slug"] + ".json"))),
                  key=lambda x: x["slug"] != promised)
    out = []
    for x in todo:
        km = km_of(x["slug"], fact_of(x["slug"], x))
        if km and km < 0.25:                                  # zo satelitu len bodka, nocny beh ju tiez preskoci
            continue
        out.append(x)
        if len(out) == n + 1:                                 # +1: posledny potrebuje "Next target"
            break
    return out


def prep(n):
    queue = json.load(open(QP, encoding="utf-8"))
    os.makedirs(BANK, exist_ok=True)
    chain = order(queue, n)
    for i, q in enumerate(chain[:n]):
        p = os.path.join(BANK, q["slug"] + ".json")
        if os.path.exists(p):
            print(f"{q['slug']}: uz je v zasobe"); continue
        fact = fact_of(q["slug"], q)
        photos = w.commons_photos(fact["title"], q["lat"], q["lon"])
        lat, lon, ok = q["lat"], q["lon"], q.get("located")
        if not ok:
            lat, lon, ok = w.locate_osm(fact["title"], q["lat"], q["lon"])
            fact["lat"], fact["lon"] = lat, lon
        km = km_of(q["slug"], fact)
        scale = w.scale_fact(km) if km else None
        shape, span = w.osm_shape(fact["title"], fact["lat"], fact["lon"])
        if shape and km and not 0.6 * km <= span <= 1.5 * km:
            shape = None
        nq = chain[i + 1] if i + 1 < len(chain) else None
        nxt = fact_of(nq["slug"], nq) if nq else None
        user, side, _ = w.prompt(fact, photos, scale, nxt, km)
        json.dump({"slug": q["slug"], "next": nq["slug"] if nq else None, "photos": photos, "lat": lat, "lon": lon,
                   "located": ok, "km": km, "scale": scale, "shape": shape, "user": user, "side": side, "draft": None},
                  open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{i + 1}. {q['slug']} -> next {nq['slug'] if nq else '-'} | {km} km | fotky {len(photos)}")


def check(slug):
    b = json.load(open(os.path.join(BANK, slug + ".json"), encoding="utf-8"))
    s = b.get("draft")
    if not s:
        sys.exit(f"{slug}: chyba draft")
    queue = json.load(open(QP, encoding="utf-8"))
    q = next(x for x in queue if x["slug"] == slug)
    nq = next((x for x in queue if x["slug"] == b.get("next")), None)
    ctx = {"article": fact_of(slug, q)["extract"], "scale": b["scale"], "next": fact_of(nq["slug"], nq) if nq else None}
    errs = w.validate(s, b["photos"], ctx)
    hooks = [h.get("text") for h in s.get("hooks") or [] if isinstance(h, dict)]
    if s["beats"] and s["beats"][0].get("text") not in hooks:
        errs.append("beat 1 text must be one of the hooks (the chosen one)")
    if not s.get("hook_title") or s["hook_title"] not in [h.get("title") for h in s.get("hooks") or []]:
        errs.append("hook_title must be the title of the chosen hook")
    words = sum(len(x.get("text", "").split()) for x in s["beats"])
    print(f"{slug}: {words} slov, {'OK' if not errs else str(len(errs)) + ' chyb'}")
    for e in errs:
        print("  - " + e)
    sys.exit(1 if errs else 0)


def left():
    queue = {x["slug"]: x["status"] for x in json.load(open(QP, encoding="utf-8"))}
    n = [f[:-5] for f in os.listdir(BANK) if f.endswith(".json") and queue.get(f[:-5]) == "todo"
         and json.load(open(os.path.join(BANK, f), encoding="utf-8")).get("draft")] if os.path.isdir(BANK) else []
    print(f"v zasobe {len(n)} scenarov: {', '.join(sorted(n))}")
    sys.exit(0 if n else 1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "prep":
        prep(int(sys.argv[2]))
    elif cmd == "check":
        check(sys.argv[2])
    elif cmd == "left":
        left()
    else:
        sys.exit(__doc__)

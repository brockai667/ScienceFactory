"""Stiahne z Wikipedie suradnice + text pre kandidatov ORBIT (zadarmo, bez kluca).
python orbit/topics/fetch_facts.py  ->  orbit/topics/facts/<slug>.json + orbit/topics/topics.json"""
import json, os, re, time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "facts")
UA = {"User-Agent": "CurioBot/1.0 (https://github.com/brockai667/ScienceFactory) python-requests"}
API = "https://en.wikipedia.org/w/api.php"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def get(params):
    for k in range(4):
        try:
            r = requests.get(API, params={**params, "format": "json", "formatversion": 2}, headers=UA, timeout=30)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(3 * (k + 1))
    return None


def fetch(title):
    j = get({"action": "query", "titles": title, "redirects": 1, "prop": "coordinates|extracts|pageimages|info",
             "explaintext": 1, "exsectionformat": "plain", "exchars": 6000, "piprop": "original", "inprop": "url"})
    if not j:
        return None
    p = j["query"]["pages"][0]
    if p.get("missing"):
        return None
    c = (p.get("coordinates") or [None])[0]
    return {"title": p["title"], "url": p.get("fullurl"),
            "lat": c and c["lat"], "lon": c and c["lon"],
            "extract": p.get("extract", ""), "image": (p.get("original") or {}).get("source")}


def main():
    os.makedirs(OUT, exist_ok=True)
    names = [l.strip() for l in open(os.path.join(HERE, "candidates.txt"), encoding="utf-8")
             if l.strip() and not l.startswith("#")]
    seen, rows = set(), []
    for n in names:
        d = fetch(n)
        if not d:
            print("CHYBA", n); continue
        if d["title"] in seen:
            print("DUPL ", n, "->", d["title"]); continue
        seen.add(d["title"])
        s = slug(d["title"])
        json.dump(d, open(os.path.join(OUT, s + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        rows.append({"slug": s, "title": d["title"], "lat": d["lat"], "lon": d["lon"],
                     "chars": len(d["extract"]), "has_coords": d["lat"] is not None})
        print(("OK   " if d["lat"] is not None else "BEZ  ") + d["title"])
        time.sleep(0.3)
    json.dump(rows, open(os.path.join(HERE, "topics.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"spolu {len(rows)}, so suradnicami {sum(r['has_coords'] for r in rows)}")


if __name__ == "__main__":
    main()

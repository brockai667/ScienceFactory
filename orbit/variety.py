"""Strazca rozmanitosti: dva diely po sebe nesmu mat rovnaku kostru (otvorenie, porovnanie, frazy, poradie popiskov).
python orbit/variety.py <slug>   ->  vypise zhody s poslednymi dielmi; exit 1 = prilis podobne.
Pouziva bank.py check (pri pisani scenara) a qc.py (len varovanie, aby den nevypadol)."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOW = 5            # s kolkymi poslednymi dielmi porovnavat
SKELETON_MAX = 4      # max rovnakych zaciatkov beatu (prve 2 slova) na tej istej pozicii ako predosly diel
PHRASES = [           # sablonove frazy: kazda smie byt najviac raz v okne
    r"\bwould fit inside\b", r"\bfrom orbit\b", r"^so (what|how|why|who)\b", r"^today\b",
    r"\bnobody (knows|drew)\b", r"\bno one (knows|drew|d)\b",
]


def beats_of(slug):
    for d in ("specs", "drafts", "bank"):
        p = os.path.join(HERE, d, slug + ".json")
        if os.path.exists(p):
            j = json.load(open(p, encoding="utf-8"))
            return (j.get("draft") or j)["beats"]
    return None


def fingerprint(beats):
    txt = [b["text"].strip() for b in beats]
    starts = [" ".join(re.findall(r"[a-z']+", t.lower())[:2]) for t in txt]
    scale = next((((b.get("scale") or {}).get("name")) or (b.get("overlay") or {}).get("label") or ""
                  for b in beats if "scale" in b or (b.get("overlay") or {}).get("type") == "scale"), "")
    m = next((re.search(r"(\b[A-Z][a-z]+(?: [A-Z][a-z]+)?) would fit", t) for t in txt if "would fit" in t), None)
    phr = {p for p in PHRASES for t in txt if re.search(p, t, re.I)}
    ov = [next((k for k in ("ruler", "rings", "scale", "tag", "stamp", "highlight") if k in b
                or (b.get("overlay") or {}).get("type") == k), "-") for b in beats]
    return {"starts": starts, "scale": (m.group(1) if m else scale).lower(), "phrases": phr, "overlays": ov}


def recent(slug):
    pub = json.load(open(os.path.join(HERE, "published.json"), encoding="utf-8"))
    mine = pub.get(slug, {}).get("no", 10 ** 6)                  # uz vydany diel porovnaj len s predoslymi
    order = sorted((v.get("no", 0), k) for k, v in pub.items() if k != slug and v.get("no", 0) < mine)
    return [k for _, k in order][-WINDOW:]


def check(slug, beats=None):
    beats = beats or beats_of(slug)
    me, issues = fingerprint(beats), []
    prev = [(s, fingerprint(b)) for s in recent(slug) if (b := beats_of(s))]
    if prev:
        s, last = prev[-1]
        same = sum(1 for a, b in zip(me["starts"][:-1], last["starts"][:-1]) if a == b)
        if same > SKELETON_MAX:
            issues.append(f"kostra ako {s}: {same} beatov zacina rovnako")
        if me["starts"][0] == last["starts"][0]:
            issues.append(f"rovnake otvorenie ako {s}: '{me['starts'][0]}'")
        if me["overlays"] == last["overlays"]:
            issues.append(f"rovnake poradie popiskov ako {s}")
    for s, f in prev:
        if me["scale"] and me["scale"] == f["scale"]:
            issues.append(f"porovnanie '{me['scale']}' uz bolo v {s}")
        for p in me["phrases"] & f["phrases"]:
            issues.append(f"fraza /{p}/ uz bola v {s}")
    return issues


if __name__ == "__main__":
    out = check(sys.argv[1])
    for i in out:
        print("variety:", i)
    print("variety:", "OK" if not out else f"{len(out)} opakovani")
    sys.exit(1 if out else 0)

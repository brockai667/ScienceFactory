#!/usr/bin/env python3
"""Ikonova kniznica pre explainer v2: OpenMoji (CC BY 4.0, 4 495 plochych SVG ikon s outline).

- ensure()            stiahne a rozbali openmoji-svg-color.zip + openmoji.json do temp/openmoji (cache)
- path_for_emoji(e)   '🖨️' -> cesta k SVG (hexcode, bez VS16/ZWJ variacii ak chybaju)
- search(text)        'old printer' -> najlepsie zhody podla annotation/tags (fallback ked LLM neda emoji)
- resolve(spec)       {'emoji': '🖨️'} | {'query': 'printer'} | {'hex': '1F5A8'} -> cesta alebo None
- install(paths, pub) skopiruje pouzite SVG do public/icons/ projektu

Kredit: OpenMoji – https://openmoji.org (CC BY-SA 4.0) - do popisu videa.
"""
import io
import json
import os
import re
import shutil
import zipfile

import requests

V2 = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(V2))
OM_DIR = os.path.join(ROOT, "temp", "openmoji")
OM_VER = "17.0.0"
OM_ZIP = f"https://github.com/hfg-gmuend/openmoji/releases/download/{OM_VER}/openmoji-svg-color.zip"
OM_JSON = f"https://raw.githubusercontent.com/hfg-gmuend/openmoji/{OM_VER}/data/openmoji.json"
CREDIT = "Icons: OpenMoji (openmoji.org), CC BY-SA 4.0"

_meta = None


def ensure():
    os.makedirs(OM_DIR, exist_ok=True)
    svg_dir = os.path.join(OM_DIR, "svg")
    if not os.path.exists(os.path.join(OM_DIR, "openmoji.json")):
        r = requests.get(OM_JSON, timeout=120)
        r.raise_for_status()
        with open(os.path.join(OM_DIR, "openmoji.json"), "wb") as f:
            f.write(r.content)
    if not os.path.isdir(svg_dir) or len(os.listdir(svg_dir)) < 1000:
        r = requests.get(OM_ZIP, timeout=600)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            z.extractall(svg_dir)
    return svg_dir


def meta():
    global _meta
    if _meta is None:
        ensure()
        with open(os.path.join(OM_DIR, "openmoji.json"), encoding="utf-8") as f:
            _meta = json.load(f)
    return _meta


def _hex_of(emoji):
    cps = [f"{ord(ch):04X}" for ch in emoji]
    return "-".join(cps)


def path_for_hex(hexcode):
    p = os.path.join(OM_DIR, "svg", f"{hexcode}.svg")
    return p if os.path.exists(p) else None


def path_for_emoji(emoji):
    """Skusi plny hexcode, potom bez FE0F (variation selector), potom len prvy codepoint."""
    emoji = str(emoji).strip()
    if not emoji:
        return None
    ensure()
    cands = [_hex_of(emoji)]
    stripped = emoji.replace("️", "")
    cands.append(_hex_of(stripped))
    if stripped:
        cands.append(_hex_of(stripped[0]))
    for h in cands:
        p = path_for_hex(h)
        if p:
            return p
    return None


_STOP = {"a", "an", "the", "of", "old", "new", "small", "big", "large", "modern", "vintage", "classic"}


def search(text, n=3, groups=None):
    """Jednoduche skorovanie: zhoda slov v annotation (2b), v tags/openmoji_tags (1b); preferuj objekty."""
    words = [w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if w not in _STOP]
    if not words:
        return []
    groups = groups or ("objects", "travel-places", "food-drink", "animals-nature", "activities",
                        "symbols", "extras-openmoji", "smileys-emotion", "people-body")
    out = []
    for m in meta():
        if m.get("group") not in groups or m.get("skintone"):
            continue
        ann = m.get("annotation", "").lower()
        tags = (m.get("tags", "") + " " + m.get("openmoji_tags", "")).lower()
        sc = 0
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", ann):
                sc += 2
            elif w in tags:
                sc += 1
        if sc:
            # kratsie anotacie = konkretnejsie
            sc += 0.3 / (1 + len(ann.split()))
            if m.get("group") == "objects":
                sc += 0.2
            out.append((sc, m))
    out.sort(key=lambda x: -x[0])
    return [(m["emoji"], m["hexcode"], m["annotation"]) for _, m in out[:n]]


def resolve(spec):
    """spec: str (emoji alebo text) | dict {'emoji'|'hex'|'query'} -> cesta k SVG alebo None."""
    if spec is None:
        return None
    if isinstance(spec, str):
        p = path_for_emoji(spec)
        if p:
            return p
        hits = search(spec, 1)
        return path_for_hex(hits[0][1]) if hits else None
    if spec.get("hex"):
        p = path_for_hex(spec["hex"])
        if p:
            return p
    if spec.get("emoji"):
        p = path_for_emoji(spec["emoji"])
        if p:
            return p
    if spec.get("query"):
        hits = search(spec["query"], 1)
        if hits:
            return path_for_hex(hits[0][1])
    return None


def install(paths, public_dir):
    """Skopiruje SVG do <public_dir>/icons/, vrati mapu cesta -> relativna URL (public/icons/X.svg)."""
    out = {}
    d = os.path.join(public_dir, "icons")
    os.makedirs(d, exist_ok=True)
    for p in set(x for x in paths if x):
        name = os.path.basename(p)
        shutil.copy(p, os.path.join(d, name))
        out[p] = f"public/icons/{name}"
    return out


if __name__ == "__main__":
    import sys
    ensure()
    for q in sys.argv[1:] or ["printer", "keyboard", "🖱️", "car radio", "battery", "light bulb", "volcano"]:
        print(q, "->", resolve(q), search(q, 3))

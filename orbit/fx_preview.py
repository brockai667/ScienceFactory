"""Nahlady efektov z fx_new.py na skutocnej satelitnej mape (bez hlasu, bez videa).

python orbit/fx_preview.py [id ...] [--spec orbit/specs/great_blue_hole.json] [--tiles <dir s dlazdicami>]
-> output/fx_preview/<id>.png (4 snimky pocas efektu) + output/fx_preview/_all.jpg (prehlad vsetkych)
Dlazdice sa len citaju (ziadne stahovanie); chybajuca dlazdica = cierna plocha.
"""
import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

SAMPLE = {                                                   # ukazkove parametre (inak ich doplni write_spec)
    "thermometer": {"n": 48, "unit": "C"}, "population_dots_fx": {"n": 1200}, "number_slot_roll": {"n": 1947, "label": "STEPS"},
    "bar_race": {"labels": ["THIS", "TYPICAL"], "values": [3, 1]}, "time_counter": {"n": 12000},
    "depth_sounding": {"n": 124}, "xray_layers": {"n": 500}, "season_swap": {"label": "AUTUMN"},
    "label_arrow_pop": {"label": "LOOK HERE"}, "earthquake_shake": {"n": 7.1},
}
TIMES = (0.12, 0.5, 1.1, 2.2)                # 4 snimky: nabeh, vrchol, stred, koniec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--spec", default=os.path.join(HERE, "specs", "richat.json"))
    ap.add_argument("--tiles", default=None)
    ap.add_argument("--z", type=float, default=None, help="zoom kamery (inak z 2. beatu)")
    a = ap.parse_args()
    if not os.path.exists(os.path.join(ROOT, "config.json")):
        sys.exit("chyba config.json (skopiruj config.example.json)")
    import orbit_engine as E
    import fx_new
    if a.tiles:
        E.TDIR = a.tiles
    E.fetch = lambda key: None                                 # nahlad nic nestahuje
    spec = json.load(open(a.spec, encoding="utf-8"))
    spec.setdefault("feature_km", 40)
    st = spec.get("start") or spec["beats"][0]["cam"]
    cam = (st["lat"], st["lon"], a.z or spec["beats"][1]["cam"]["z"])
    base = E.render_flat(*cam)
    vig = np.clip(1.12 - (((E._xx - E.W / 2) / E.W) ** 2 + ((E._yy - E.H / 2) / E.H) ** 2) * 1.1, 0.55, 1)[..., None]
    base = base * vig
    cx, cy = E.screen_xy(st["lat"], st["lon"], cam)
    R = max(80.0, float(spec.get("feature_km") or 20) / 2 * 1000 / E.m_per_px(st["lat"], cam[2]))
    out_dir = os.path.join(ROOT, "output", "fx_preview")
    os.makedirs(out_dir, exist_ok=True)
    ids = a.ids or list(fx_new.EFFECTS)
    thumbs, slow = [], []
    for k in ids:
        f = dict({"kind": k, "on": None}, **SAMPLE.get(k, {}))
        frames, t0 = [], time.time()
        for i, dt in enumerate(TIMES):
            fr = base.copy()
            fx_new.draw(k, fr, 10.0 + float(dt), float(dt), cx, cy, R, 1.0, f, cam, spec)
            frames.append(cv2.resize(np.clip(fr, 0, 255).astype(np.uint8), (360, 640), interpolation=cv2.INTER_AREA))
        ms = (time.time() - t0) / 4 * 1000
        slow.append((ms, k))
        sheet = np.hstack([np.pad(x, ((0, 0), (4, 4), (0, 0))) for x in frames])
        bar = np.zeros((60, sheet.shape[1], 3), np.uint8)
        cv2.putText(bar, f"{k}   ({ms:.0f} ms/frame)   dt = {TIMES} s", (12, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
        sheet = np.vstack([bar, sheet])
        cv2.imwrite(os.path.join(out_dir, f"{k}.png"), sheet)
        small = cv2.resize(np.clip(base, 0, 255).astype(np.uint8), (360, 640), interpolation=cv2.INTER_AREA).astype(np.int16)
        th = max(frames, key=lambda x: np.abs(x.astype(np.int16) - small).mean()).copy()   # najvyraznejsi snimok
        cv2.rectangle(th, (0, 0), (360, 34), (0, 0, 0), -1)
        cv2.putText(th, k, (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
        thumbs.append(cv2.resize(th, (240, 427)))
        print(f"{k:22s} {ms:6.0f} ms/snimok")
    cols = 9
    while len(thumbs) % cols:
        thumbs.append(np.zeros_like(thumbs[0]))
    grid = np.vstack([np.hstack(thumbs[i:i + cols]) for i in range(0, len(thumbs), cols)])
    if not a.ids:
        cv2.imwrite(os.path.join(out_dir, "_all.jpg"), grid, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("najpomalsie:", ", ".join(f"{k} {ms:.0f} ms" for ms, k in sorted(slow, reverse=True)[:5]))


if __name__ == "__main__":
    main()

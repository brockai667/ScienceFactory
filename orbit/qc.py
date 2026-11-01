"""Kontrola pred nahratim: video nesmie byt prilis velke a musi mat dost animacii (nie holy globus).
python orbit/qc.py <spec.json> <video.mp4>  ->  exit 1 = nenahravat."""
import json
import os
import sys

MAX_MB = 30          # zrno filmu zle komprimuje; nad tymto pada upload cez API/Buffer
MIN_FX = 3           # skutocne animacie k slovam (meteorit, praskliny, oko...), bez nahradnych
MAX_FALLBACK = 3     # viac beatov s nahradnym skenom = tema, ku ktorej nemame efekty


def main():
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    mb = os.path.getsize(sys.argv[2]) / 1e6
    fx = [f for b in spec["beats"] for f in b.get("fx", []) if f["kind"] != "follow"]
    real = sum(1 for f in fx if not f.get("fallback")) + sum(1 for b in spec["beats"] if "impact" in b)
    fb = sum(1 for f in fx if f.get("fallback"))
    print(f"qc: {mb:.1f} MB, efekty {real}, nahradne {fb}: " + ", ".join(f["kind"] for f in fx))
    errs = []
    if mb > MAX_MB:
        errs.append(f"video ma {mb:.1f} MB (max {MAX_MB})")
    if real < MIN_FX:
        errs.append(f"len {real} skutocnych efektov (min {MIN_FX})")
    if fb > MAX_FALLBACK:
        errs.append(f"{fb} beatov len s nahradnym efektom (max {MAX_FALLBACK})")
    for e in errs:
        print("qc FAIL:", e)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()

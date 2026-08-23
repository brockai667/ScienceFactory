#!/usr/bin/env python3
"""Tyzdenny beh explainer v2: tema -> spec (Groq) -> engine (HyperFrames) -> QA -> publish.

  python explainer/v2/run_v2.py                   # plny beh (dalsia tema z banky)
  python explainer/v2/run_v2.py --dry             # bez publikovania
  python explainer/v2/run_v2.py --spec explainer/v2/specs/usb_demo.json
  python explainer/v2/run_v2.py --topic "Every HDMI Version Explained"
  python explainer/v2/run_v2.py --long-only       # bez reels (rychlejsi test)
"""
import json
import os
import subprocess
import sys
import time

V2 = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(V2)
ROOT = os.path.dirname(EXP)
for p in (EXP, V2):
    if p not in sys.path:
        sys.path.insert(0, p)
import common  # noqa: E402


def contact_sheet(mp4, out_jpg, cols=6, every=3.0, width=320):
    ff = common.load_cfg().get("ffmpeg", "ffmpeg")
    rows = 10
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", mp4, "-vf",
                    f"fps=1/{every},scale={width}:-1,tile={cols}x{rows}", "-frames:v", "1", out_jpg],
                   capture_output=True, timeout=600)
    return out_jpg if os.path.exists(out_jpg) else None


def thumbnail(meta, spec, out_dir):
    """Snimka z konca intro-gridu (nazov serie + vsetky polozky + PART 1) ako YouTube thumbnail."""
    ff = common.load_cfg().get("ffmpeg", "ffmpeg")
    t = 0.0
    grid = (spec.get("intro") or {}).get("grid")
    if grid and "_t0" in grid:
        t = grid["_t0"] + grid["_dur"] - 0.6
    elif meta.get("duration"):
        t = min(12.0, meta["duration"] * 0.15)
    out = os.path.join(out_dir, "thumb.jpg")
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", meta["long"], "-frames:v", "1",
                    "-vf", "scale=1280:720", "-q:v", "2", out], capture_output=True, timeout=120)
    return out if os.path.exists(out) else None


def main():
    argv = sys.argv[1:]
    dry = "--dry" in argv
    long_only = "--long-only" in argv
    spec_path = argv[argv.index("--spec") + 1] if "--spec" in argv else None
    topic = argv[argv.index("--topic") + 1] if "--topic" in argv else None
    t0 = time.time()
    common.ensure_dirs()

    if not spec_path:
        import script as sc
        import script_v2
        if topic:
            series, items = topic, None
        else:
            t = sc.pick_topic()
            series, items = t["series"], t.get("items")
        spec_path, _ = script_v2.generate(series, items)
        sc.mark_used(series)
        print(f"[1/4] spec OK: {spec_path} ({(time.time() - t0) / 60:.1f} min)")
    else:
        print(f"[1/4] spec: {spec_path} (dodany)")

    spec = json.load(open(spec_path, encoding="utf-8"))
    import engine
    out_dir = os.path.join(common.OUT_ROOT, common.slug(spec.get("series")))
    os.makedirs(out_dir, exist_ok=True)
    workers = int(os.environ.get("HF_WORKERS", "2"))
    meta = engine.render_spec(spec, out_dir, do_long=True, do_reels=not long_only, workers=workers)
    meta["script"] = os.path.relpath(spec_path, ROOT)
    meta["thumb"] = thumbnail(meta, spec, out_dir)
    meta["sheet"] = contact_sheet(meta["long"], os.path.join(out_dir, "sheet.jpg"))
    meta["description"] = (meta.get("description", "") + "\n\n" + meta.get("credits", "")).strip()
    meta_path = os.path.join(out_dir, "meta.json")
    common.save_json(meta_path, meta)
    print(f"[2/4] render OK: {meta['long']} ({meta.get('duration', 0) / 60:.1f} min) + {len(meta.get('reels', []))} reels "
          f"({(time.time() - t0) / 60:.1f} min); cue_missing={len(meta.get('cue_missing', []))}")

    print(f"[3/4] QA: sheet={meta.get('sheet')} thumb={meta.get('thumb')}")
    import publish
    publish.publish(meta_path, do_yt=True, do_reels=not long_only, dry=dry)
    print(f"[4/4] publikovanie {'(dry) ' if dry else ''}OK ({(time.time() - t0) / 60:.1f} min)")
    with open(os.path.join(common.OUT_ROOT, "LAST_META"), "w", encoding="utf-8") as f:
        f.write(meta_path)


if __name__ == "__main__":
    main()

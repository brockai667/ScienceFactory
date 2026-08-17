#!/usr/bin/env python3
"""Tyzdenny beh explainer fabriky (pondelok): tema -> scenar -> render -> publikovanie.

Pouzitie:
  python explainer/run_weekly.py                       # plny beh
  python explainer/run_weekly.py --dry                 # vsetko okrem publikovania (test na Actions)
  python explainer/run_weekly.py --script explainer/scripts/x.json   # preskoc generovanie, pouzi hotovy skript
  python explainer/run_weekly.py --no-images           # rychly test bez AI obrazkov
  python explainer/run_weekly.py --topic "Every X Explained"

Kroky su idempotentne: meta.json si pamata, co uz je nahrane (opakovany beh nic neduplikuje).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def main():
    argv = sys.argv[1:]
    dry = "--dry" in argv
    no_images = "--no-images" in argv
    script = None
    topic = None
    if "--script" in argv:
        script = argv[argv.index("--script") + 1]
    if "--topic" in argv:
        topic = argv[argv.index("--topic") + 1]
    t0 = time.time()
    common.ensure_dirs()

    if not script:
        import script as sc
        if topic:
            series, items = topic, None
        else:
            t = sc.pick_topic()
            series, items = t["series"], t.get("items")
        script, spec = sc.generate(series, items)
        sc.mark_used(series)
        print(f"[1/3] scenar OK: {script} ({(time.time() - t0) / 60:.1f} min)")
    else:
        print(f"[1/3] scenar: {script} (dodany)")

    import render
    meta = render.render_all(script, do_long=True, do_reels=True, use_images=not no_images)
    meta_path = os.path.join(os.path.dirname(meta["long"]), "meta.json")
    print(f"[2/3] render OK: {meta['long']} + {len(meta.get('reels', []))} reels ({(time.time() - t0) / 60:.1f} min)")

    import publish
    publish.publish(meta_path, do_yt=True, do_reels=True, dry=dry)
    print(f"[3/3] publikovanie {'(dry-run) ' if dry else ''}OK ({(time.time() - t0) / 60:.1f} min)")
    # cesta pre workflow (artefakty)
    with open(os.path.join(common.OUT_ROOT, "LAST_META"), "w", encoding="utf-8") as f:
        f.write(meta_path)


if __name__ == "__main__":
    main()

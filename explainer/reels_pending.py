#!/usr/bin/env python3
"""Cakajuce reels pre Buffer (free plan = max 10 naplanovanych postov na kanal).

Reels sa planuju na 7+ dni dopredu, ale denna fabrika drzi IG frontu plnu -> Buffer odmietne
("Scheduled posts limit reached"). Riesenie: neuspesne (alebo daleke) posty sa ulozia sem a denny beh
(`python explainer/publish.py --drain`) ich doplanuje vzdy len ~1 den dopredu, ked je vo fronte miesto.

Subor: explainer/reels_pending.json (commitovany stav)
  [{"series","name","label","title","yt_title","body","hosted_url","due" (ISO UTC), "services": ["instagram", ...]}]
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

PENDING_FILE = os.path.join(common.EXP_DIR, "reels_pending.json")
DRAIN_HORIZON_H = 30      # planuj len posty, ktore maju ist do ~30 h (fronta 10 postov = ~3 dni dennej fabriky)


def load():
    return common.load_json(PENDING_FILE, [])


def save(items):
    common.save_json(PENDING_FILE, items)


def add(entry):
    """Prida/zluci zaznam (klucom je hosted_url + service)."""
    items = load()
    for it in items:
        if it.get("hosted_url") == entry.get("hosted_url"):
            it["services"] = sorted(set(it.get("services", [])) | set(entry.get("services", [])))
            for k, v in entry.items():
                it.setdefault(k, v)
            save(items)
            return
    items.append(entry)
    save(items)


def _parse(due):
    return datetime.datetime.strptime(due[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)


def drain(cfg, dry=False, horizon_h=DRAIN_HORIZON_H):
    """Naplanuje cakajuce reels, ktorych cas je do `horizon_h` hodin. Vrati pocet uspesne pridanych postov."""
    sys.path.insert(0, common.ROOT)
    import push_to_buffer as ptb
    items = load()
    if not items:
        print("  [drain] nic necaka")
        return 0
    token = cfg.get("buffer_token", "").strip()
    chans = {c["service"].lower(): c["id"] for c in (cfg.get("buffer_channels") or [])}
    now = datetime.datetime.now(datetime.timezone.utc)
    limit = now + datetime.timedelta(hours=horizon_h)
    done_posts, keep = 0, []
    for it in items:
        due = _parse(it["due"])
        if due < now + datetime.timedelta(minutes=20):
            # cas uz presiel (napr. fronta bola plna viac dni) -> posun na najblizsiu celu hodinu +1h
            due = (now + datetime.timedelta(hours=1)).replace(minute=random_minute(), second=0, microsecond=0)
            it["due"] = due.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if due > limit:
            keep.append(it)
            continue
        pending = [s for s in it.get("services", []) if s in chans]
        print(f"  [drain] {it.get('label')} -> {due.strftime('%a %d.%m %H:%M')}Z ({', '.join(pending) or 'hotovo'})")
        left = []
        for svc in pending:
            if dry:
                left.append(svc)
                continue
            title = it.get("yt_title") if svc == "youtube" else it.get("title")
            ok, msg = ptb.create_post(token, svc, chans[svc], it.get("body", ""), it["hosted_url"], title, it["due"])
            if ok:
                done_posts += 1
                print(f"     [{svc}] OK")
            else:
                left.append(svc)
                print(f"     [{svc}] CHYBA: {str(msg)[:160]}")
        it["services"] = left
        if left:
            keep.append(it)
    if not dry:
        save(keep)
    print(f"  [drain] naplanovane {done_posts}, caka {len(keep)}")
    return done_posts


def random_minute():
    import random
    return random.randint(0, 25)


if __name__ == "__main__":
    drain(common.load_cfg(), dry="--dry-run" in sys.argv)

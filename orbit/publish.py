"""Publikovanie ORBIT: YT + IG cez Buffer (naplanovane na SLOT_HOUR), TikTok cez feed orbit/tiktok.json pre appku TikTok Nahravac.
python orbit/publish.py <slug> [--dry-run]     opakovane spustenie doplni len chybajuce sluzby
python orbit/publish.py --retry               doplni Buffer pri starsich dieloch (napr. po vymene tokenu)
python orbit/publish.py --check-stop           exit 1, ak uz vyslo STOP_AFTER videi (fabrika caka na verdikt)
python orbit/publish.py --retime              po zmene SLOT_HOUR presunie naplanovane Buffer posty + TikTok feed
Stav: orbit/published.json {slug: {no, due, video, services}}."""
import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PUB = os.path.join(HERE, "published.json")
FEED = os.path.join(HERE, "tiktok.json")
QUEUE = os.path.join(HERE, "topics", "queue.json")
SLOT_HOUR = 10                                               # Bratislava; 1 video denne (TikTok z appky v rovnaky cas)
STOP_AFTER = 10                                              # potom stop, po 10 dnoch Damian porovna cisla
TAG = "orbit"                                                # GitHub Release s videami (verejny, zadarmo)


def load(p, default):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def save(p, data):
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def next_due(pub):
    """Najblizsie SLOT_HOUR (aspon o 30 min), v den, ked este nic nevyslo. ISO UTC."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Bratislava")
    now = datetime.datetime.now(tz)
    used = {datetime.datetime.fromisoformat(p["due"].replace("Z", "+00:00")).astimezone(tz).date()
            for p in pub.values() if p.get("due")}
    t = now.replace(hour=SLOT_HOUR, minute=0, second=0, microsecond=0)
    while t < now + datetime.timedelta(minutes=30) or t.date() in used:
        t += datetime.timedelta(days=1)
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def texts(spec):
    no = spec.get("series_no") or 0
    title = f"{spec['title']} from space · ORBIT #{no:03d}"[:100]
    tags = " ".join(spec.get("hashtags") or []) + " #orbit #shorts"
    caption = f"{spec['beats'][0]['text']}\n\n{spec['description']}\n\n{tags}"
    return title, caption


def main():
    args = sys.argv[1:]
    pub = load(PUB, {})
    if "--check-stop" in args:
        n = len(pub)
        print(f"ORBIT: vyslo {n} videi (stop pri {STOP_AFTER})")
        sys.exit(1 if n >= STOP_AFTER else 0)
    if "--retime" in args:                                     # zmena SLOT_HOUR: naplanovane posty presunut na novy cas
        sys.exit(retime(pub))
    if "--unpublish" in args:                                  # stiahnut naplanovane (este nevydane) diely na prerobenie
        sys.exit(unpublish(pub, [a for a in args if not a.startswith("--")]))
    if "--retry" in args:
        bad = 0
        for slug, e in list(pub.items()):
            if e.get("video") and len(e["services"]) < 3:
                bad += publish(slug, pub, False)
        sys.exit(1 if bad else 0)
    slug = next(a for a in args if not a.startswith("--"))
    sys.exit(publish(slug, pub, "--dry-run" in args))


def retime(pub):
    """diely, ktore este nevysli a nemaju cas SLOT_HOUR: zmazat ich naplanovane Buffer posty a naplanovat znova
    (v ten isty den o SLOT_HOUR, ak je este aspon 30 min dopredu, inak dalsi volny den)."""
    from zoneinfo import ZoneInfo
    import push_to_buffer as pb
    tz = ZoneInfo("Europe/Bratislava")
    token = (pb.load_cfg().get("buffer_token") or "").strip()
    now = datetime.datetime.now(tz)
    orgs = ((pb.gql(token, "query{account{organizations{id}}}") or {}).get("account") or {}).get("organizations") or []
    q = ("query($o:OrganizationId!){posts(input:{organizationId:$o, filter:{status:[scheduled]}}){edges{node{id dueAt channelId}}}}")
    mine = {c["id"] for c in pb.load_cfg().get("buffer_channels") or []}
    posts = [e["node"] for o in orgs for e in (((pb.gql(token, q, {"o": o["id"]}) or {}).get("posts") or {}).get("edges") or [])
             if e["node"].get("channelId") in mine]
    bad = 0
    for slug, e in pub.items():
        old = datetime.datetime.fromisoformat(e["due"].replace("Z", "+00:00")).astimezone(tz)
        if old < now or old.hour == SLOT_HOUR:
            continue
        for p in posts:                                       # posty tohto dielu = rovnaky cas v Bufferi
            if datetime.datetime.fromisoformat(p["dueAt"].replace("Z", "+00:00")) == old:
                d = pb.gql(token, "mutation($id:PostId!){deletePost(input:{id:$id}){__typename}}", {"id": p["id"]})
                print(f"  {slug}: zruseny post {p['id']} ({p['dueAt']}): {json.dumps(d)[:120]}")
        t = old.replace(hour=SLOT_HOUR, minute=0)
        e["due"] = (t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                    if t >= now + datetime.timedelta(minutes=30) else next_due({k: v for k, v in pub.items() if k != slug}))
        e["services"] = [s for s in e["services"] if s == "tiktok"]
        save(PUB, pub)
        bad += publish(slug, pub, False)
    return 1 if bad else 0


def unpublish(pub, slugs):
    """Zmaze naplanovane Buffer posty dielov (len buduce), vyhodi ich z published.json aj z TikTok feedu."""
    import push_to_buffer as pb
    token = (pb.load_cfg().get("buffer_token") or "").strip()
    now = datetime.datetime.now(datetime.timezone.utc)
    orgs = ((pb.gql(token, "query{account{organizations{id}}}") or {}).get("account") or {}).get("organizations") or []
    q = ("query($o:OrganizationId!){posts(input:{organizationId:$o, filter:{status:[scheduled]}}){edges{node{id dueAt channelId}}}}")
    mine = {c["id"] for c in pb.load_cfg().get("buffer_channels") or []}
    posts = [e["node"] for o in orgs for e in (((pb.gql(token, q, {"o": o["id"]}) or {}).get("posts") or {}).get("edges") or [])
             if e["node"].get("channelId") in mine]
    feed = load(FEED, {"episodes": {}})
    bad = 0
    for slug in slugs:
        e = pub.get(slug)
        if not e:
            print(f"  {slug}: nie je v published.json"); continue
        due = datetime.datetime.fromisoformat(e["due"].replace("Z", "+00:00"))
        if due < now + datetime.timedelta(minutes=10):
            print(f"  {slug}: uz vysiel / vychadza, nestahujem"); bad += 1; continue
        for p in posts:
            if datetime.datetime.fromisoformat(p["dueAt"].replace("Z", "+00:00")) == due:
                d = pb.gql(token, "mutation($id:PostId!){deletePost(input:{id:$id}){__typename}}", {"id": p["id"]})
                print(f"  {slug}: zruseny Buffer post {p['id']} ({p['dueAt']}): {json.dumps(d)[:100]}")
        feed["episodes"].pop(str(e.get("no")), None)
        pub.pop(slug)
        print(f"  {slug}: stiahnuty (feed aj published.json)")
    save(PUB, pub)
    save(FEED, feed)
    return 1 if bad else 0


def publish(slug, pub, dry):
    spec = json.load(open(os.path.join(HERE, "specs", slug + ".json"), encoding="utf-8"))
    out = os.path.join(ROOT, "output")
    mp4, tt = os.path.join(out, f"orbit_{slug}.mp4"), os.path.join(out, f"orbit_{slug}_tiktok.mp4")
    cover = os.path.join(out, f"orbit_{slug}_tiktok-cover.jpg")      # appka: {video_base}-cover.jpg
    title, caption = texts(spec)
    e = pub.setdefault(slug, {"no": spec.get("series_no"), "services": []})
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
    if not e.get("due") or (len(e["services"]) < 3 and datetime.datetime.fromisoformat(e["due"].replace("Z", "+00:00")) < now):
        e["due"] = next_due({k: v for k, v in pub.items() if k != slug})     # zmeskany termin -> dalsi volny den
    print(f"{slug}: {title} | {e['due']}")
    if dry:
        print(caption); return 0
    import push_to_buffer as pb
    cfg = pb.load_cfg()
    if not e.get("video"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2.5", "-i", mp4, "-frames:v", "1", "-q:v", "3", cover], check=True)
        e["video"] = pb.upload_github_release(cfg, mp4, tag=TAG)
        e["tiktok"] = pb.upload_github_release(cfg, tt, tag=TAG)
        pb.upload_github_release(cfg, cover, tag=TAG, ctype="image/jpeg")
        save(PUB, pub)
    feed = load(FEED, {"episodes": {}})                       # TikTok: appka si video stiahne a nahra
    feed["episodes"][str(e["no"])] = {"id": slug, "title": f"ORBIT #{e['no']:03d}: {spec['title']}",
                                     "text": caption, "video": e["tiktok"], "due": e["due"]}
    save(FEED, feed)
    if "tiktok" not in e["services"]:
        e["services"].append("tiktok")
    fails = []
    token = (cfg.get("buffer_token") or "").strip()
    for c in cfg.get("buffer_channels") or []:
        svc = c["service"].lower()
        if svc in e["services"]:
            continue
        if not token:
            fails.append(f"{svc}: chyba BUFFER_TOKEN"); continue
        ok, msg = pb.create_post(token, svc, c["id"], caption, e["video"], title, e["due"])
        print(f"  buffer {svc}: {'OK' if ok else msg}")
        if ok:
            e["services"].append(svc)
        else:
            fails.append(f"{svc}: {msg}")
    save(PUB, pub)
    q = load(QUEUE, [])
    for x in q:
        if x["slug"] == slug:
            x["status"] = "done"
    save(QUEUE, q)
    if fails:                                                 # TikTok feed je hotovy; Buffer doplni --retry dalsim behom
        print("CHYBA publikovania: " + "; ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    main()

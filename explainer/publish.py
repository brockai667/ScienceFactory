#!/usr/bin/env python3
"""Publikovanie explainer vystupu:
  1) dlhe video -> YouTube Data API (OAuth refresh token), naplanovane na pondelok o yt_publish_hour,
     s kapitolami (timestampy) v popise + thumbnail
  2) reels (kapitoly) -> Buffer, jeden na den (reel_slot_hour, Europe/Bratislava), s odkazom na dlhe video

Pouzitie:
  python explainer/publish.py output/explainer/<slug>/meta.json            # oboje
  python explainer/publish.py output/explainer/<slug>/meta.json --yt-only
  python explainer/publish.py output/explainer/<slug>/meta.json --reels-only
  python explainer/publish.py ... --dry-run                                # nic neposle, len vypise plan
Stav: output/explainer/<slug>/meta.json (yt_url, reels[i].pushed) -> opakovane spustenie neduplikuje.
"""
import datetime
import json
import os
import random
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

YT_CATEGORY = "28"   # Science & Technology


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Bratislava")
    except Exception:
        return datetime.timezone(datetime.timedelta(hours=2))


def _env(key, cfg):
    return os.environ.get(key) or cfg.get(key.lower()) or ""


# ---------------------------------------------------------------- YouTube
def yt_access_token(cid, csec, rtok):
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": cid, "client_secret": csec, "refresh_token": rtok, "grant_type": "refresh_token"})
    r.raise_for_status()
    return r.json()["access_token"]


def yt_upload(tok, mp4, title, description, tags, publish_at=None):
    status = {"selfDeclaredMadeForKids": False}
    if publish_at:
        status.update({"privacyStatus": "private", "publishAt": publish_at})
    else:
        status["privacyStatus"] = "public"
    meta = {"snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:20],
                        "categoryId": YT_CATEGORY}, "status": status}
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/*"},
        data=json.dumps(meta).encode("utf-8"), timeout=60)
    init.raise_for_status()
    up_url = init.headers["Location"]
    with open(mp4, "rb") as f:
        body = f.read()
    put = requests.put(up_url, headers={"Content-Type": "video/*", "Content-Length": str(len(body))},
                       data=body, timeout=1800)
    put.raise_for_status()
    return put.json()


def yt_set_thumbnail(tok, video_id, jpg):
    with open(jpg, "rb") as f:
        data = f.read()
    r = requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}",
                      headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"},
                      data=data, timeout=120)
    r.raise_for_status()


def yt_publish_time(cfg):
    """Najblizsi pondelok (alebo dnes, ak je pondelok a cas este nenastal) o yt_publish_hour. ISO UTC."""
    e = cfg["explainer"]
    tz = _tz()
    now = datetime.datetime.now(tz)
    hour = int(e.get("yt_publish_hour", 17))
    d = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    # ak bezime v pondelok pred publikovacim casom -> dnes; inak najblizsi buduci pondelok
    while d.weekday() != 0 or d <= now + datetime.timedelta(minutes=20):
        d += datetime.timedelta(days=1)
        d = d.replace(hour=hour, minute=0, second=0, microsecond=0)
    return d


def publish_youtube(meta, cfg, dry=False):
    if meta.get("yt_url"):
        print(f"  [yt] uz nahrane: {meta['yt_url']}")
        return meta["yt_url"]
    mp4 = meta.get("long")
    if not mp4 or not os.path.exists(mp4):
        raise RuntimeError("Dlhe video neexistuje (meta.long).")
    e = cfg["explainer"]
    title = meta.get("title") or meta.get("series")
    hashline = " ".join(meta.get("hashtags", []))
    chapters = meta.get("chapters_ts") or []
    ch_lines = "\n".join(f"{ts} {name}" for name, ts in chapters)
    if chapters and not chapters[0][1].startswith("0:00"):
        ch_lines = "0:00 Intro\n" + ch_lines
    desc = (meta.get("description", "").strip() + "\n\nChapters:\n" + ch_lines +
            "\n\nEvery Monday: one thing you use every day, fully explained. Subscribe.\n"
            f"{e.get('channel_url', '')}\n\n{hashline}").strip()
    tags = [h.lstrip("#") for h in meta.get("hashtags", [])] + ["explained", "technology", "science"]
    when = yt_publish_time(cfg)
    publish_at = when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"  [yt] {title}\n       publish: {when.strftime('%a %Y-%m-%d %H:%M %Z')} ({os.path.getsize(mp4) / 1e6:.0f} MB)")
    if dry:
        print("  [yt] dry-run - nenahravam")
        return None
    cid, csec, rtok = (_env("YOUTUBE_CLIENT_ID", cfg), _env("YOUTUBE_CLIENT_SECRET", cfg),
                       _env("YOUTUBE_REFRESH_TOKEN", cfg))
    if not (cid and csec and rtok):
        raise RuntimeError("Chybaju YouTube OAuth udaje (YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN).")
    tok = yt_access_token(cid, csec, rtok)
    res = yt_upload(tok, mp4, title, desc, tags, publish_at)
    vid = res.get("id")
    url = f"https://www.youtube.com/watch?v={vid}"
    print(f"  [yt] OK: {url}")
    meta["yt_url"] = url
    meta["yt_publish_at"] = publish_at
    thumb = meta.get("thumb")
    if thumb and os.path.exists(thumb):
        try:
            yt_set_thumbnail(tok, vid, thumb)
            print("  [yt] thumbnail OK")
        except Exception as ex:
            print("  [yt] thumbnail preskoceny:", str(ex)[:160])
    return url


# ---------------------------------------------------------------- Buffer reels
def reel_slots(n, cfg, start=None):
    """n dni po sebe o reel_slot_hour (Bratislava) + jitter. start = datum prveho reelu."""
    e = cfg["explainer"]
    tz = _tz()
    now = datetime.datetime.now(tz)
    hour = int(e.get("reel_slot_hour", 18))
    d = (start or now).astimezone(tz).replace(hour=hour, minute=0, second=0, microsecond=0)
    d += datetime.timedelta(days=int(e.get("reels_start_offset_days", 0)))
    if d <= now + datetime.timedelta(minutes=30):
        d += datetime.timedelta(days=1)
    out = []
    for i in range(n):
        if i < 7:
            t = d + datetime.timedelta(days=i)
        else:
            # 8. a dalsi reel: nekoliduj s buducim pondelkom -> druhy slot (o 6 h skor) v dnoch 2..
            t = d + datetime.timedelta(days=i - 6, hours=-6)
        t += datetime.timedelta(minutes=random.randint(0, 25), seconds=random.randint(0, 59))
        out.append(t)
    return out


def reel_text(meta, reel, i, n, yt_url, cfg):
    e = cfg["explainer"]
    series = meta.get("series", "")
    hook = (reel.get("hook") or f"{reel.get('name')} explained.").strip()
    tags = " ".join(meta.get("hashtags", [])[:8])
    link = yt_url or e.get("channel_url", "")
    body = (f"{hook}\n\n{series} — part {i + 1}/{n}: {reel.get('name')}.\n\n"
            f"▶ Full video (all {n} parts): {link}\n\n{tags}")
    title = f"{reel.get('name')} — {series} ({i + 1}/{n})"
    return title, body


def publish_reels(meta, cfg, dry=False, yt_url=None):
    import push_to_buffer as ptb   # zdielane: hosting videa + Buffer mutacia
    reels = meta.get("reels") or []
    if not reels:
        print("  [reels] ziadne reels v meta")
        return
    token = cfg.get("buffer_token", "").strip()
    targets = cfg.get("buffer_channels") or []
    if not dry and (not token or not targets):
        raise RuntimeError("Chyba buffer_token / buffer_channels v configu.")
    n = len(reels)
    # start: den publikovania dlheho videa (yt_publish_at) alebo dnes
    start = None
    if meta.get("yt_publish_at"):
        start = datetime.datetime.strptime(meta["yt_publish_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc)
    slots = reel_slots(n, cfg, start)
    services = [c["service"].lower() for c in targets]
    for i, reel in enumerate(reels):
        done = set(reel.get("pushed", []))
        pending = [c for c in targets if c["service"].lower() not in done]
        title, body = reel_text(meta, reel, i, n, yt_url or meta.get("yt_url"), cfg)
        due = slots[i].astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print(f"  [reel {i + 1}/{n}] {reel.get('label')} -> {slots[i].strftime('%a %d.%m %H:%M')} "
              f"({', '.join(c['service'] for c in pending) or 'hotovo'})")
        if dry or not pending:
            continue
        if not os.path.exists(reel["path"]):
            print("     CHYBA: subor neexistuje", reel["path"])
            continue
        url = reel.get("hosted_url") or ptb.host_video(cfg, reel["path"])
        reel["hosted_url"] = url
        for c in pending:
            svc = c["service"].lower()
            yt_title = (title + " #shorts")[:100]
            ok, msg = ptb.create_post(token, svc, c["id"], body, url, yt_title if svc == "youtube" else title, due)
            if ok:
                done.add(svc)
                reel["pushed"] = sorted(done)
                print(f"     [{svc}] OK")
            else:
                print(f"     [{svc}] CHYBA: {msg[:200]}")
    fully = sum(1 for r in reels if set(r.get("pushed", [])) >= set(services))
    print(f"  [reels] plne naplanovane: {fully}/{n}")


# ---------------------------------------------------------------- main
def publish(meta_path, do_yt=True, do_reels=True, dry=False):
    cfg = common.load_cfg()
    meta = common.load_json(meta_path, None)
    if not meta:
        raise SystemExit(f"meta.json nenajdeny: {meta_path}")
    yt_url = meta.get("yt_url")
    if do_yt:
        try:
            yt_url = publish_youtube(meta, cfg, dry)
        finally:
            common.save_json(meta_path, meta)
    if do_reels:
        try:
            publish_reels(meta, cfg, dry, yt_url)
        finally:
            common.save_json(meta_path, meta)
    return meta


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)
    publish(args[0], do_yt="--reels-only" not in sys.argv, do_reels="--yt-only" not in sys.argv,
            dry="--dry-run" in sys.argv)

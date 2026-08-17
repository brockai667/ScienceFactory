# Pro video pipeline (shared base)

This factory runs autonomously daily: generate_topics (its niche + trend-scan) -> generate_batch -> make_video -> push_to_buffer.

## Shared engine base (identical across ALL factories; only the NICHE differs)
- **B-roll**: pooled multi-query Pexels search in get_broll -> picks best by topic-match (url slug) + resolution.
- **Captions**: POP animated (config caption_renderer=pop) - each word pops in (scale), key words/numbers yellow.
- **Voice**: Kokoro (local, free). **Music**: cinematic (cine_*). **Motion**: hook zoom + Ken Burns. Color grade per brand.
- Per-segment `asset` (local image/video) supported for screenshots / micro-montages / animated logos.

Each factory keeps its own niche (topics_bank + brand colors/hashtags) but the make_video.py engine is identical.

## Weekly explainer (explainer/, workflow weekly.yml) - Curio only
Monday: one 16:9 "Every X Explained" long video (YouTube, scheduled 17:00 Bratislava) + one 9:16 reel per
chapter, queued in Buffer one per day at 18:00 (IG/YT Shorts) linking to the long video.
The daily engine drops from 3 to 2 videos/day; the chapter reel fills the third slot.

- `explainer/script.py`  topic from `explainer_bank.json` (list-shaped topics, 6-8 items) -> Groq outline
  -> per-chapter beats (title -> what+year -> why -> number+comparison -> where it fails -> twist -> today -> question)
- `explainer/render.py`  slideshow engine: white bg, PIL stick figure (no stock), Comic Neue, AI images
  (Pollinations Flux, fixed style suffix) in blue-shadow frames, chapter HUD, ffmpeg progress bar.
  Same JSON renders long.mp4 AND reel_XX.mp4. Voice: Kokoro `am_michael`. Test: `--no-images`.
- `explainer/publish.py` YouTube Data API upload (OAuth refresh token, publishAt, chapters in description,
  thumbnail) + Buffer reels via push_to_buffer helpers (GitHub Release hosting). Idempotent via meta.json.
- `explainer/run_weekly.py` orchestrates; `--dry` skips publishing (workflow_dispatch input `dry_run`).
- One-off setup: `python youtube_auth.py` (settings.json with client id/secret) -> secrets YOUTUBE_CLIENT_ID,
  YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN for the Curio channel. Optional: POLLINATIONS_TOKEN
  (free at auth.pollinations.ai; lifts image rate limit 1/15s -> 1/5s).

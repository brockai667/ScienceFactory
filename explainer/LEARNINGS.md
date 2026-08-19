# Explainer v1 → v2: prečo v1 zlyhal a ako sa robia dobré explainery

Stav 2026-08-19: v1 (explainer/render.py) = statické slajdy. Užívateľ: „odporné, nič nerobiace scény,
neťahá diváka ani o sekundu ďalej". Weekly workflow VYPNUTÝ, YT video + 16 Buffer postov stiahnuté.
Zajtra: postaviť v2 engine. Tento súbor = zhrnutie naštudovaného + plán.

## 1. Diagnóza v1 (podľa HyperFrames motion doctrine – sedí 1:1)
- **Slideshow failure**: všetok obsah slajdu sa ukáže v prvých 25 % a ZAMRZNE (pop-in 0,33 s, potom hold 5–8 s).
  Nič sa neodhaľuje na podnet hlasu. Presne „agent-made PowerPoint".
- **Bouncy**: použil som `ease_out_back` (overshoot) – „#1 instant turn-off", serious shops to nerobia.
- **Žiadna kontinuita**: každý beat nový obrázok, žiadna spoločná „scéna", ktorá rastie (diagram, os, stôl).
- **Žiadny pohyb kamery, žiadne count-upy, draw-on, zvýraznenia, SFX, hudba** – obrázok + text a ticho.
- **Skript**: „show" text = heslo bez rytmu; hlas nemá frázové hranice, ku ktorým by sa dalo odhaľovať.
- Obrázky z Pollinations sú OK-ish, ale statické fotky v rámiku samy o sebe nič neurobia.

## 2. Čo fungovalo pri Money Glitch (AmbientFactory/glitch_engine.py) – prevziať
- JEDEN súvislý TTS hlas (nie per-veta lepenie) + časovanie titulkov z hraníc viet/slov.
- **Čísla sa KRESLIA perom a ESKALUJÚ** (draw_number), červený ručný kruh na payoffe, šípky, rovnice, loop diagram.
- Ikony sa jemne kolíšu (wobble), zrno + vinetácia = film, nie PowerPoint.
- Maskot s lip-syncom z RMS hlasu = osobnosť; glosuje na hook/beat/close.
- Sebavedomý tón, hook bez undercutu; cover karta prvých 0,55 s (clickbait thumbnail v grid-e).

## 3. Princípy z HyperFrames skillov (faceless-explainer / motion-language / story-design)
**Motion doctrine (load-bearing):**
1. Smooth > bouncy: `power3.out` dlhý dojazd; žiadne back/bounce/elastic.
2. **Sekvenčné odhaľovanie v zadných ~50 % scény, časované na hlas** – každý prvok (riadok, karta, číslo)
   sa objaví, KEĎ ho hlas vysloví. Menej vecí na plátne, každá na svoj beat.
3. Žiadne „lazy breathing" (pulzujúce karty) ani pomalý pan v druhej polovici – radšej ticho + jemný jitter.
4. Vnútorné strihy = velocity-matched (cut-the-curve, zoom-through), nie tvrdý slajd.
**Slovník pohybov:** per-word staggered reveal, kinetic beat-slam, type-on, value-scaled counter (číslo rastie
a zväčšuje sa), bars/fills, SVG self-draw, push/focus/drift kamera, zoom-to-target, cluster→outward expansion,
split-tilt cards (porovnanie), scale-swap, marker highlight/circle/scribble, depth-of-field blur, spring-pop
(bez overshootu).
**Story design:** 1 štruktúra na video (concept / how-to / listicle / story); hook v prvých 3–5 s z menu
(šokujúca štatistika, kontraintuitívne tvrdenie, rečnícka otázka, „imagine", stakes) – NIKDY definícia;
téza do 2. beatu, zvyšok = dôkazy; každý frame má 1 job (narrativeRole + keyMessage); telo = 3–6 framov na
**konzistentnej scéne** (ten istý diagram rastie); 2–3 typy prechodov na celé video a opakovať
(push-slide pre kroky, crossfade pre vrstvu, zoom-through do detailu, cut na nový item).
**Skript:** 6–20 slov na frame, písané ako diskrétne cue („First the snowball — then the hill — then the speed"),
konkretizácia/analógia namiesto parafrázy; tiché framy (diagram sa skladá sám) sú povolené.
**Cover/pacing:** vizuálny beat každé ~2–4 s (nový prvok, zmena), nikdy 6 s holdu bez zmeny.

## 4. Nástroje (nainštalované 2026-08-19)
- **HyperFrames** (heygen-com/hyperframes, 41,7k★): HTML+GSAP → deterministický MP4. `npx hyperframes render`
  OVERENÉ lokálne (5 s video za 14 s, 4 workery; Node 24 OK). Skilly v ~/.claude/skills: hyperframes,
  faceless-explainer (workflow + scripts: audio/captions/transitions/assemble), hyperframes-animation
  (22 blueprintov, 48 pravidiel, 24 text efektov), hyperframes-keyframes (kamera/Ken Burns), -creative
  (13 frame presetov, typografia, beat-direction), -core (kontrakt: `class="clip"`, data-start/duration,
  audio klipy), -audio, -cli, media-use (Kokoro TTS, BGM/SFX katalóg HeyGen – vyžaduje sign-in).
- **Remotion skills** (remotion-dev/skills, 12 skillov) – alternatíva, React; nepoužijeme, HF stačí.
- OpenMontage lokálne (C:\Users\damia\OpenMontage) – 80+ skillov, vrátane sound-effects, visual-style.
- iart-ai/motion-skills – iný formát (tools/), neinštalované.

## 5. Plán v2 (zajtra)
**Architektúra:** Groq píše beat JSON (ako teraz, ale skript v tvare cue + blueprint per beat) →
Kokoro TTS jedným kusom + faster-whisper word timings (máme) → **Python generátor HyperFrames kompozícií**
(10–12 šablón/blueprintov v HTML+GSAP, parametrizované textom, číslami, obrázkami, časmi slov) →
`npx hyperframes render` (Ubuntu runner: node 22 + chromium, odhad ~40 min na 13 min videa) → reels 9:16 z tých
istých dát. ŽIADNE LLM-písanie HTML na runneri – šablóny = deterministická kvalita.
**Šablóny (blueprints) pre explainer:** hook-kinetic (beat-slam + kamera push), concept-name (titlecard-reveal),
stat-countup (value-scaled counter + bar), compare-split (split-tilt cards), timeline-grow (konzistentná os,
push-slide), hub-3 (constellation: stred + 3), image-focus (Ken Burns + marker circle + label on cue),
list-build (grid-card-assemble, reveal per cue), quote/verdict (type-on), chapter-card, cold-open grid, outro.
Každá: entrance nese len to, čo hlas hovorí v t=0; zvyšok na word-cue; power3; 1 kamera move; SFX whoosh/tick
na reveal; subtle grain+vignette; panáčik = SVG s lip-sync (RMS) a gestom, nie statický PNG.
**Štýl:** rozhodnúť s užívateľom na 60-s demo A/B: (A) biely „notes" look ako referencia ale živý,
(B) HF preset (capsule/bold-poster/coral). Hudba: tichý bed (-22 dB) + ducking pod hlas.
**Kroky:** (1) demo 1 kapitola (~90 s) v HF s 5 šablónami → ukázať; (2) po schválení zvyšok šablón + 9:16;
(3) nahradiť render.py; (4) dry-run na Actions; (5) až potom publish + reels (publish.py ostáva).

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

## 6. Engine v2 – STAV 2026-08-22 (postavene, schvalene demo v7)
**Moduly (`explainer/v2/`):** `engine.py` (spec JSON → HyperFrames kompozicie 16:9 + 9:16 → MP4; Kokoro per beat,
1 whisper prechod → relativne slova per beat; sablony intro_compare / intro_grid / hook / title / focus / list / stat /
compare / outro / chapter_card / endcard), `svglib.py` (hero objekty USB + stickman/crown/note/stamp, animovatelne po
castiach), `icons.py` (OpenMoji 4 495 SVG, emoji → subor, textove hladanie ako zaloha; kredit CC BY-SA do popisu),
`script_v2.py` (Groq → spec: osnova + 6 beatov/kapitola s cue frazami a emoji; validacia cue = substring say,
emoji → existujuca ikona), `run_v2.py` (tema → spec → render → thumbnail z intro gridu → kontaktny harok → publish),
`specs/usb_demo.json` (regresny spec = schvalene demo).

**Co sa naucil engine z 7 demo iteracii (a je zapecene v kode):**
1. `cue_time` = ZACIATOK slova (+12 %), nie koniec – inak vsetko chodi neskoro.
2. Prvy prvok beatu vzdy t0+0.25 (nikdy prazdna obrazovka), seam 0.45 s dnu / 0.36 s von, kamera push 1.045.
3. Dash-kreslene prvky (skrt, kruh, kable, EKG) maju `opacity="0"` v markupu + `tl.set(opacity)` pri kresleni –
   inak okruhle zakoncenie presvita ako bodka.
4. Markery (kruh, peciatka) sa POCITAJU z layoutu (grid: stlpec = (W-2*280-3*60)/4, stred 1. = 427), nie od oka.
5. CSS: `.center` je celoplosny flex kontajner – nadpisy pouzivaju `.tcenter` (text-align). V 16:9 sa chyba
   neprejavila, v 9:16 nadpis skocil do stredu cez obsah. Kontaktny harok reelu to odhalil.
6. Kazdy beat ma vizual + nieco sa deje kazde 2–4 s: pulz tiles na vlastnost, peciatka roku na slovo, EKG na „never
   died", fotka lezie 3 s s casovacom, kable sa kreslia k SVOJMU portu, koruna + konfety na payoff.
7. Reel 9:16: karta focus max 760x560, zoznam max 3 polozky v rade (330 px rozostup), kompare karty pod sebou.
8. Lokalny render: `npx -y hyperframes@0.8.4` (0.8.10 sa pyta y/n → -y), 2 workery, protocol-timeout 600000,
   spustat SKRYTO (Start-Process -WindowStyle Hidden) – chrome-headless-shell okna rusia usera; 1 GB RAM stacilo.
9. Groq free kluc: gpt-oss musi mat `reasoning_effort: low` + `response_format json_object`, inak minie tokeny na
   reasoning a vrati prazdny obsah; 429 → cakat 30–90 s. Generovanie 4 kapitol trva ~10+ min.
10. QA = kontaktny harok (fps=1/2.5, tile 4x8 / 8x3) po KAZDOM renderi; `meta.cue_missing` musi byt [].

**Dalsie kroky:** (a) prvy generovany spec (HDMI) cez engine – skontrolovat OpenMoji ikony a generovane cue;
(b) dry-run weekly.yml na Actions (node 22 + chromium), zmerat cas renderu 13 min videa + 8 reels;
(c) thumbnail = snimka z intro gridu; (d) hudobny bed + maskot s lip-syncom = neskor.

### 6.x Poučenia z prvého generovaného videa (HDMI, 23.8.)
11. **Unikátne ID per beat.** Šablóny používali pevné `id="stat"`, `id="slam1"` – v kapitole 2+ GSAP
    animoval vždy prvý výskyt (čísla stáli na 0.0, slamy sa ukázali naraz). Riešenie: `_scope_ids`
    prepisuje každé `id` a selektor na `u<beat>_…` hneď pri skladaní klipu.
12. **Cue nesmie byť číslo s jednotkou.** Whisper píše „10.2 Gbps“, TTS číta „ten point two gigabits“ –
    cue sa nenájde. `_norm` mapuje jednotky/číslovky, ale prompt radšej vyžaduje cue zo slov.
13. **LLM kopíruje placeholdre.** Opis „THE TRUTH, 3-5 WORDS“ v prompte sa objavil ako slam vo videu.
    Prompt má teraz kompletný few-shot príklad (USB biely port) + validátor placeholdre zahadzuje.
14. **8 beatov na kapitolu** (hook, title, focus, list, stat, focus, list, compare) → ~1.7 min/kapitola,
    5 kapitol ≈ 8+ min, čo je pre YT dlhé video minimum.
15. **Nikdy prázdna scéna.** Karty porovnania a prvá položka zoznamu čakali na cue aj 9 s → headline sám na
    papieri. Vstup prvku je teraz ohraničený (karty ≤1.3/2.1 s, 1. položka ≤1.6 s), cue spúšťa len badge/pulz.
16. **Fact sheet pred kapitolami.** Groq 120b si per-kapitolu vymýšľal čísla (HDMI 1.3 „4.8 Gb/s, 600 MHz, 3D“).
    Jedno volanie s nízkou teplotou pre všetky položky naraz dáva presné, konzistentné čísla → ground truth v prompte.
17. **Verzie jedného produktu = jedna ikona.** Model dával HDMI 2.1 raketu a 2.1a puzzle; keď majú kapitoly
    spoločné prvé slovo, všetky dostanú hero ikonu (fyzický objekt), líšia sa labelom – ako farebné USB porty.
18. **Dedup beatov podľa tpl zjedol 8-beatovú štruktúru** (2. focus/list) → dedup len presných duplikátov,
    plus len prvý hook/title (model rád pridá hook na koniec).

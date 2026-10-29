"""Z topics.json urobi frontu tem queue.json: vyhodi miesta bez jasneho satelitneho zaberu,
doplni rucne suradnice tam, kde ich Wikipedia nema. Poradie = poradie v candidates.txt."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))

# ziadny jasny zaber zo satelitu (cela puste, oblast na mape, udalost, pod ladom)
EXCLUDE = {"Bermuda Triangle", "Burning Man", "Tunguska event", "Lake Vostok", "Camp Century", "Sahara",
           "Rub' al Khali", "Taklamakan Desert", "Atacama Desert", "Antarctic Peninsula", "Danxia landform",
           "Yamal Peninsula", "Woomera Prohibited Area", "Kennicott", "Dracaena cinnabari",
           "Steppe Geoglyphs", "Fairy circle (arid grass formation)", "Skeleton Coast", "Bayuda Desert"}
# Wikipedia nema suradnice v hlavicke clanku
MANUAL = {"Pole of inaccessibility": (-48.8767, -123.3933),   # Point Nemo
          "Dallol (hydrothermal system)": (14.2417, 40.3000),
          "Dead Sea": (31.50, 35.50),
          "Tsingy de Bemaraha National Park": (-18.72, 44.72),
          "Petra": (30.3285, 35.4444),
          "Batagaika crater": (67.58, 134.77)}

rows = json.load(open(os.path.join(HERE, "topics.json"), encoding="utf-8"))
queue = []
for r in rows:
    if r["title"] in EXCLUDE:
        continue
    if r["title"] in MANUAL:
        r["lat"], r["lon"] = MANUAL[r["title"]]
    if r["lat"] is None:
        continue
    queue.append({"slug": r["slug"], "title": r["title"], "lat": r["lat"], "lon": r["lon"], "status": "todo"})
queue[0]["status"] = "done"   # richat = ukazka
json.dump(queue, open(os.path.join(HERE, "queue.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(queue), "tem vo fronte")

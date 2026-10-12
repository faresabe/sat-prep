import json
from pathlib import Path
from collections import Counter

DOWNLOADS = Path("SAT_Downloads")

def load_all():
    for path in DOWNLOADS.rglob("*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                yield path, json.load(f)
        except Exception as e:
            yield path, {"_load_error": str(e)}

keys = Counter()
for _, doc in load_all():
    keys.update(doc.keys())

for k, n in keys.most_common():
    print(f"{n:5d}  {k}")
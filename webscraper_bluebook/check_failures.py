import json
from collections import Counter

c = Counter()
with open("canonical/import_failures.jsonl") as f:
    for line in f:
        d = json.loads(line)
        c[d["reason"]] += 1

for reason, n in c.most_common():
    print(f"{n:5d}  {reason}")
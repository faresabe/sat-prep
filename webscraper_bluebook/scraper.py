"""
SAT Question Bank scraper — API version. No Selenium, no browser.
Run:  python scraper_api.py
"""

import os
import json
import time
import requests


# ---------------------------------------------------------------------------
# Folder naming (unchanged — matches your existing folders)
# ---------------------------------------------------------------------------
def make_folder_name(section, domain, skill, difficulty):
    prefix = "RW" if section == "Reading and Writing" else "Math"
    name = "_".join([prefix, domain, skill, difficulty])
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', ',']:
        name = name.replace(ch, '')
    while "__" in name:
        name = name.replace("__", "_")
    return name.strip("_")[:150]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_ROOT = "https://qbank-api.collegeboard.org/msreportingquestionbank-prod/questionbank/digital"
ASMT = 99
OUTPUT_ROOT = "SAT_Downloads"
DIFF_MAP = {"E": "Easy", "M": "Medium", "H": "Hard"}

# For each section: list of domain query strings to hit, in order.
# We'll union the results and dedupe by external_id.
SECTIONS = [
    ("Reading and Writing", 1, ["INI,CAS,EOI,SEC"]),
    ("Math",                2, ["H,P,Q,G", "A,P,Q,G", "H,AM,PSDA,GT"]),
]

SLEEP_BETWEEN = 0.05   # polite delay between question downloads


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
SESSION = requests.Session()
SESSION.headers.update({
    "Content-Type": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/122.0 Safari/537.36"),
})


def fetch_question_list(test, domain_string):
    r = SESSION.post(
        f"{API_ROOT}/get-questions",
        json={"asmtEventId": ASMT, "test": test, "domain": domain_string},
        timeout=60,
    )
    if r.status_code != 200:
        return []
    try:
        return r.json()
    except Exception:
        return []


def fetch_question(external_id):
    for attempt in range(3):
        try:
            r = SESSION.post(
                f"{API_ROOT}/get-question",
                json={"external_id": external_id},
                timeout=60,
            )
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:
            time.sleep(1)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    # 1. collect unique questions per section (union + dedupe)
    resolved = []   # list of (section, [question dict, ...])

    for section, test, domain_strings in SECTIONS:
        print(f"\n=== {section} ===")
        seen = set()
        qlist = []
        for dstr in domain_strings:
            batch = fetch_question_list(test, dstr)
            print(f"  {dstr!r:25s} -> {len(batch)} questions")
            for q in batch:
                key = q.get("external_id") or q.get("questionId")
                if key and key not in seen:
                    seen.add(key)
                    qlist.append(q)
        print(f"  unique: {len(qlist)}")
        resolved.append((section, qlist))

    total = sum(len(q) for _, q in resolved)
    print(f"\nTotal unique questions to download: {total}")

    # 2. download every question
    t0 = time.time()
    downloaded = skipped = failed = 0
    i = 0

    for section, qlist in resolved:
        print(f"\n--- {section} ({len(qlist)} questions) ---")
        for q in qlist:
            i += 1
            qid = q.get("questionId")
            ext = q.get("external_id")
            skill = q.get("skill_desc") or "Unknown"
            domain = q.get("primary_class_cd_desc") or "Unknown"
            diff = DIFF_MAP.get(q.get("difficulty") or "E", "Easy")

            if not qid or not ext:
                failed += 1
                continue

            folder = make_folder_name(section, domain, skill, diff)
            path = os.path.join(OUTPUT_ROOT, folder)
            os.makedirs(path, exist_ok=True)

            out = os.path.join(path, f"q{qid}.json")
            if os.path.exists(out):
                skipped += 1
                continue

            payload = fetch_question(ext)
            if payload is None:
                failed += 1
                print(f"  ✗ failed {qid}")
                continue

            payload["_section"] = section
            payload["_domain"] = domain
            payload["_skill"] = skill
            payload["_difficulty"] = diff

            with open(out, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)

            downloaded += 1
            if downloaded % 25 == 0:
                el = time.time() - t0
                rate = downloaded / el if el else 0
                print(f"  [{i}/{total}] {rate:.1f}/s — "
                      f"downloaded={downloaded} skipped={skipped} failed={failed}")

            time.sleep(SLEEP_BETWEEN)

    el = time.time() - t0
    print(f"\nDONE in {el:.1f}s")
    print(f"  downloaded: {downloaded}")
    print(f"  skipped:    {skipped}")
    print(f"  failed:     {failed}")
    print(f"\nOutput: {os.path.abspath(OUTPUT_ROOT)}")


if __name__ == "__main__":
    main()
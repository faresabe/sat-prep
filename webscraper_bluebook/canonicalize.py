#!/usr/bin/env python3
"""
canonicalize.py — turn mixed scraped SAT JSON files into one uniform shape.

Input:  SAT_Downloads/**/*.json   (two variants: API and Selenium)
Output: canonical/questions.jsonl (clean, one JSON per line)
        canonical/invalid.jsonl   (rejected, with reasons)
        canonical/stats.json      (counts, for eyeballing)
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

DOWNLOADS = Path("SAT_Downloads")
OUT_DIR   = Path("canonical")
OUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------
# Static mappings
# ---------------------------------------------------------------------

SECTION_MAP = {
    "Math": "MATH",
    "Reading and Writing": "RW",
}

DIFFICULTY_MAP = {
    "Easy":   "easy",
    "Medium": "medium",
    "Hard":   "hard",
}

LABELS = ["A", "B", "C", "D"]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _strip_html(s):
    if not s:
        return ""
    return re.sub(r"<[^>]+>", "", s).strip()


def detect_variant(doc):
    if not isinstance(doc, dict):
        return "not_an_object"
    if doc.get("_source") == "selenium":
        return "selenium"
    if "externalid" in doc:
        return "api"
    return "unknown"


# ---------------------------------------------------------------------
# Mappers
# ---------------------------------------------------------------------

def map_api(doc):
    """
    API-sourced file.
    MC: has answerOptions[{id,content}], keys (list of option UUIDs), type='mcq'
    Grid-in: has NO answerOptions, type='spr', keys=['15.5','31/2'], correct_answer=[...]
    """
    is_grid_in = doc.get("type") == "spr"

    if is_grid_in:
        choices          = []
        correct_labels   = []
        correct_answers  = list(doc.get("correct_answer", [])) or list(doc.get("keys", []))
    else:
        correct_positions = [
            i for i, opt in enumerate(doc["answerOptions"])
            if opt["id"] in doc.get("keys", [])
        ]
        choices = [
            {"label": LABELS[i], "content": opt["content"]}
            for i, opt in enumerate(doc["answerOptions"])
        ]
        correct_labels  = [LABELS[i] for i in correct_positions]
        correct_answers = []

    return {
        "source_id":       f"cb_qb:{doc['externalid']}",
        "source_variant":  "api",
        "section":         SECTION_MAP[doc["_section"]],
        "domain_name":     doc["_domain"],
        "skill_name":      doc["_skill"],
        "difficulty":      DIFFICULTY_MAP[doc["_difficulty"]],
        "question_type":   "grid_in" if is_grid_in else "multiple_choice",
        "stem":            doc.get("stem", ""),
        "stimulus":        doc.get("stimulus"),
        "choices":         choices,
        "correct_labels":  correct_labels,
        "correct_answers": correct_answers,
        "explanation":     doc.get("rationale", ""),
        "images":          [],
        "warnings":        [],
    }


def map_selenium(doc):
    """
    Selenium-sourced file.
    MC: has answerOptions[{label,content}], _question_type='MCQ', correct_answer=['A']
    Grid-in: _question_type='SPR', no answerOptions, correct_answer=['15.5','31/2']
    """
    is_grid_in = doc.get("_question_type", "").upper() == "SPR"

    if is_grid_in:
        choices         = []
        correct_labels  = []
        correct_answers = list(doc.get("correct_answer", []))
    else:
        choices = [
            {"label": opt["label"], "content": opt["content"]}
            for opt in doc.get("answerOptions", [])
        ]
        correct_labels  = list(doc.get("correct_answer", []))
        correct_answers = []

    return {
        "source_id":       f"cb_qb_selenium:{doc['questionId']}",
        "source_variant":  "selenium",
        "section":         SECTION_MAP[doc["_section"]],
        "domain_name":     doc["_domain"],
        "skill_name":      doc["_skill"],
        "difficulty":      DIFFICULTY_MAP[doc["_difficulty"]],
        "question_type":   "grid_in" if is_grid_in else "multiple_choice",
        "stem":            doc.get("stem", ""),
        "stimulus":        doc.get("stimulus") or doc.get("stimulus_reference"),
        "choices":         choices,
        "correct_labels":  correct_labels,
        "correct_answers": correct_answers,
        "explanation":     None,
        "images":          doc.get("math_images", []),
        "warnings":        ["no explanation"] if not doc.get("rationale") else [],
    }


MAPPERS = {
    "api":      map_api,
    "selenium": map_selenium,
}


# ---------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------

def validate(c):
    problems = []

    if c["section"] not in ("MATH", "RW"):
        problems.append(f"bad section: {c['section']!r}")

    if c["difficulty"] not in ("easy", "medium", "hard"):
        problems.append(f"bad difficulty: {c['difficulty']!r}")

    if c["question_type"] not in ("multiple_choice", "grid_in"):
        problems.append(f"bad question_type: {c['question_type']!r}")

    if not _strip_html(c["stem"]):
        problems.append("empty stem")

    if c["question_type"] == "multiple_choice":
        labels = [ch["label"] for ch in c["choices"]]
        if labels != LABELS:
            problems.append(f"MC must have choices A,B,C,D; got {labels}")
        if len(c["correct_labels"]) != 1:
            problems.append(
                f"MC must have exactly 1 correct; got {c['correct_labels']}"
            )
        if c["correct_labels"] and not set(c["correct_labels"]).issubset(set(labels)):
            problems.append("correct label not among choices")

    elif c["question_type"] == "grid_in":
        if c["section"] != "MATH":
            problems.append("grid-in must be MATH")
        if not c["correct_answers"]:
            problems.append("grid-in has no correct answer")

    return problems


# ---------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------

def process(path):
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        return None, f"load error: {e}"

    variant = detect_variant(doc)
    if variant not in MAPPERS:
        return None, f"unknown variant: {variant}"

    try:
        c = MAPPERS[variant](doc)
    except KeyError as e:
        # report the actual missing key
        return None, f"map error ({variant}): missing key {e!s}"
    except Exception as e:
        return None, f"map error ({variant}): {type(e).__name__}: {e}"

    problems = validate(c)
    if problems:
        c["_problems"] = problems
        c["_path"] = str(path)
        return None, c

    return c, None


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    good_path    = OUT_DIR / "questions.jsonl"
    invalid_path = OUT_DIR / "invalid.jsonl"

    counts = Counter()
    variant_counts = Counter()
    type_counts = Counter()

    with open(good_path, "w", encoding="utf-8") as good, \
         open(invalid_path, "w", encoding="utf-8") as invalid:

        for path in sorted(DOWNLOADS.rglob("*.json")):
            counts["seen"] += 1
            c, err = process(path)

            if c is None:
                counts["rejected"] += 1
                if isinstance(err, dict):
                    invalid.write(json.dumps(err) + "\n")
                else:
                    invalid.write(json.dumps({"_path": str(path), "_err": err}) + "\n")
                continue

            counts["ok"] += 1
            variant_counts[c["source_variant"]] += 1
            type_counts[c["question_type"]] += 1
            good.write(json.dumps(c) + "\n")

    stats = {
        "seen":        counts["seen"],
        "ok":          counts["ok"],
        "rejected":    counts["rejected"],
        "by_variant":  dict(variant_counts),
        "by_type":     dict(type_counts),
    }
    (OUT_DIR / "stats.json").write_text(json.dumps(stats, indent=2))

    print(f"Processed {counts['seen']} files")
    print(f"  OK:       {counts['ok']}")
    print(f"  Rejected: {counts['rejected']}")
    print(f"  By variant: {dict(variant_counts)}")
    print(f"  By type:    {dict(type_counts)}")
    print()
    print(f"Output: {good_path}")
    print(f"Rejects: {invalid_path}")
    print(f"Stats:  {OUT_DIR / 'stats.json'}")


if __name__ == "__main__":
    main()
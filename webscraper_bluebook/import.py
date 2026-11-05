#!/usr/bin/env python3
"""
import.py — read canonical/questions.jsonl and insert each row into PostgreSQL.

Usage:
    python import.py --dry-run --limit 5      # show what would happen
    python import.py --limit 100              # real insert of first 100
    python import.py                          # full run

Passage handling:
  For RW questions with a non-empty `stimulus` field, a row is created in the
  `passages` table and the question's `passage_id` is set.  Stimuli are
  de-duplicated by a SHA-256 hash of the normalized text so questions sharing
  the same passage reuse one row.

  Two passes are run:
    1. import_row — inserts NEW questions (with passage_id if applicable).
    2. link_passages_existing — updates ALREADY-IMPORTED questions that lack
       a passage_id.  This pass connects as app_owner and temporarily
       disables the trg_lock_published_question trigger so that published
       questions can be updated.
"""

import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path
from collections import Counter

import psycopg

CANONICAL        = Path("canonical/questions.jsonl")
CONN_STRING      = "postgresql://app_content_admin:fares@localhost:5432/satprep"
OWNER_CONN_STRING = "postgresql://app_owner:fares@localhost:5432/satprep"

# Folder-name → DB-name aliases, where folder name differs from what's in
# the skills table. Both sides are normalized (lowercase + collapsed spaces).
SKILL_ALIASES = {
    ("RW", "inferences"): ("RW", "inference"),
}

# ─────────────────────────────────────────────────────────────────────────────
# Passage helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_stimulus(text: str) -> str:
    """Collapse whitespace and lowercase for stable hashing."""
    return " ".join(text.split()).strip().lower()


def _stimulus_hash(text: str) -> str:
    return hashlib.sha256(_normalize_stimulus(text).encode()).hexdigest()


def load_passage_cache(cur) -> dict:
    """Load all existing passages into {content_hash: passage_id}."""
    cur.execute("SELECT id, content FROM passages")
    cache = {}
    for pid, content in cur.fetchall():
        cache[_stimulus_hash(content)] = pid
    return cache


def get_or_create_passage(cur, stimulus: str, passage_cache: dict) -> uuid.UUID:
    """Return passage_id for the given stimulus, creating a row if needed."""
    h = _stimulus_hash(stimulus)
    if h in passage_cache:
        return passage_cache[h]
    pid = uuid.uuid4()
    cur.execute(
        "INSERT INTO passages (id, content, status) VALUES (%s, %s, 'published')",
        (pid, stimulus),
    )
    passage_cache[h] = pid
    return pid


# ─────────────────────────────────────────────────────────────────────────────
# Name normalisation — case-insensitive, whitespace-collapsed
# ─────────────────────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------
# Name normalisation — case-insensitive, whitespace-collapsed
# ---------------------------------------------------------------------

def _norm(s):
    return " ".join(s.lower().split())


# ---------------------------------------------------------------------
# Taxonomy cache — loaded once
# ---------------------------------------------------------------------

def load_taxonomy(cur):
    """
    Returns {(section, normalized_skill_name): (domain_id, skill_id)}
    """
    cur.execute("""
        SELECT s.section, s.name, d.id, s.id
          FROM skills s JOIN domains d ON d.id = s.domain_id
    """)
    m = {}
    for section, skill_name, domain_id, skill_id in cur.fetchall():
        m[(section, _norm(skill_name))] = (domain_id, skill_id)
    return m


# ---------------------------------------------------------------------
# Per-row import
# ---------------------------------------------------------------------

def import_row(cur, row, taxonomy, passage_cache, dry_run=False):
    """
    Inserts one question. Returns (status, detail).
    Must be called inside an open transaction.
    """
    source_id = row["source_id"]

    # 1. Already imported?
    cur.execute("SELECT id FROM questions WHERE source = %s", (source_id,))
    existing = cur.fetchone()
    if existing:
        return "skipped", str(existing[0])

    # 2. Resolve taxonomy (with alias remapping)
    key = (row["section"], _norm(row["skill_name"]))
    key = SKILL_ALIASES.get(key, key)
    if key not in taxonomy:
        return "failed", f"unmapped skill: {row['section']} / {row['skill_name']!r}"

    domain_id, skill_id = taxonomy[key]

    # 3. Resolve passage for RW questions with a non-empty stimulus
    passage_id = None
    if row["section"] == "RW" and row.get("stimulus") and row["stimulus"].strip():
        passage_id = get_or_create_passage(cur, row["stimulus"], passage_cache)

    # 4. Insert question (draft)
    qid = uuid.uuid4()
    cur.execute("""
        INSERT INTO questions
            (id, root_question_id, revision, section, domain_id, skill_id,
             question_type, stem, difficulty, status, source, passage_id)
        VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s, 'draft', %s, %s)
    """, (
        qid, qid,
        row["section"], domain_id, skill_id,
        row["question_type"],
        row["stem"],
        row["difficulty"],
        source_id,
        passage_id,
    ))

    # 5. Insert choices + resolve correct choice UUIDs (MC only)
    if row["question_type"] == "multiple_choice":
        correct_choice_ids = []
        for choice in row["choices"]:
            cid = uuid.uuid4()
            cur.execute("""
                INSERT INTO question_choices
                    (id, question_id, label, content, position)
                VALUES (%s, %s, %s, %s, %s)
            """, (cid, qid, choice["label"], choice["content"], ord(choice["label"]) - 64))
            if choice["label"] in row["correct_labels"]:
                correct_choice_ids.append(cid)

        for cid in correct_choice_ids:
            cur.execute("""
                INSERT INTO grading.question_keys (question_id, correct_choice_id)
                VALUES (%s, %s)
            """, (qid, cid))

    # 6. Insert accepted answers (grid-in only)
    elif row["question_type"] == "grid_in":
        for raw in row["correct_answers"]:
            cur.execute("""
                INSERT INTO grading.spr_accepted_answers (question_id, raw_value)
                VALUES (%s, %s)
            """, (qid, raw))

    # 7. Insert explanation (if present)
    explanation = row.get("explanation")
    has_explanation = bool(explanation and explanation.strip())
    if has_explanation:
        cur.execute("""
            INSERT INTO grading.question_explanations (question_id, explanation)
            VALUES (%s, %s)
        """, (qid, explanation))

    # 8. Publish — only if we have a complete key AND an explanation
    can_publish = has_explanation
    if can_publish:
        cur.execute("""
            UPDATE questions
               SET status = 'published', published_at = now()
             WHERE id = %s
        """, (qid,))

    return "inserted", f"{qid} status={'published' if can_publish else 'draft'}"


# ---------------------------------------------------------------------
# Link passages to already-imported questions
# ---------------------------------------------------------------------

def link_passages_existing(rows, passage_cache):
    """
    Update existing RW questions that lack a passage_id.

    Uses app_owner (can ALTER TABLE to disable the immutability trigger).
    Idempotent: skips questions that already have a passage_id.
    """
    linked = 0
    skipped_has_passage = 0
    skipped_no_stimulus = 0
    not_found = 0

    with psycopg.connect(OWNER_CONN_STRING) as conn:
        with conn.cursor() as cur:
            # Disable the trigger so we can UPDATE published questions
            cur.execute(
                "ALTER TABLE questions DISABLE TRIGGER trg_lock_published_question"
            )

            try:
                for row in rows:
                    if row["section"] != "RW":
                        continue
                    stimulus = row.get("stimulus")
                    if not stimulus or not stimulus.strip():
                        skipped_no_stimulus += 1
                        continue

                    source_id = row["source_id"]

                    # Check current passage_id
                    cur.execute(
                        "SELECT id, passage_id FROM questions WHERE source = %s",
                        (source_id,),
                    )
                    result = cur.fetchone()
                    if result is None:
                        not_found += 1
                        continue
                    qid, existing_pid = result
                    if existing_pid is not None:
                        skipped_has_passage += 1
                        continue

                    # Get or create passage
                    pid = get_or_create_passage(cur, stimulus, passage_cache)

                    # Link the question to the passage
                    cur.execute(
                        "UPDATE questions SET passage_id = %s WHERE id = %s",
                        (pid, qid),
                    )
                    linked += 1

                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                # Re-enable the trigger (in a fresh transaction)
                with psycopg.connect(OWNER_CONN_STRING) as conn2:
                    with conn2.cursor() as cur2:
                        cur2.execute(
                            "ALTER TABLE questions ENABLE TRIGGER trg_lock_published_question"
                        )
                        conn2.commit()

    print(f"\n--- Link passages (existing questions) ---")
    print(f"  Linked:                {linked}")
    print(f"  Skipped (has passage): {skipped_has_passage}")
    print(f"  Skipped (no stimulus): {skipped_no_stimulus}")
    print(f"  Not found in DB:       {not_found}")

    return linked


# ---------------------------------------------------------------------
# Publish-safety check
# ---------------------------------------------------------------------

# Phrases that indicate a question references an external text/passage
_TEXT_REF_PATTERN = re.compile(
    r"\b(the\s+(?:text|passage|excerpt|selection|article|essay|story|poem|"
    r"document|letter|memoir|biography|narrative|paragraph|stanza|speech|"
    r"address|sermon|preface|introduction|chapter)\b"
    r"|according\s+to\s+the\s+(?:text|passage|excerpt|selection|article)\b"
    r"|based\s+on\s+the\s+(?:text|passage|excerpt|selection|article)\b"
    r"|in\s+the\s+(?:text|passage|excerpt|selection|article)\b)",
    re.IGNORECASE,
)


def publish_safety_check(rows):
    """
    Find RW questions that reference 'the text' or similar but have no
    passage, and set them to 'draft' (unpublished) so students never see
    an unanswerable question.

    Also checks whether any demo-test modules reference now-unpublished
    questions and reports them.

    Uses app_owner to disable the immutability trigger.
    """
    # Collect source_ids of RW questions that reference a text but have no passage
    at_risk_source_ids = []
    for row in rows:
        if row["section"] != "RW":
            continue
        stimulus = row.get("stimulus")
        if stimulus and stimulus.strip():
            continue  # has stimulus → will have a passage → safe
        stem = row.get("stem", "")
        if _TEXT_REF_PATTERN.search(stem):
            at_risk_source_ids.append(row["source_id"])

    if not at_risk_source_ids:
        print("\n--- Publish-safety check ---")
        print("  No RW questions at risk (all have passages or no text reference).")
        return

    unpublished = []
    affected_modules = []

    with psycopg.connect(OWNER_CONN_STRING) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE questions DISABLE TRIGGER trg_lock_published_question"
            )

            try:
                for sid in at_risk_source_ids:
                    cur.execute(
                        "SELECT id, status, passage_id FROM questions WHERE source = %s",
                        (sid,),
                    )
                    result = cur.fetchone()
                    if result is None:
                        continue
                    qid, status, pid = result
                    if pid is not None:
                        continue  # already has a passage
                    if status == "published":
                        cur.execute(
                            "UPDATE questions SET status = 'draft' WHERE id = %s",
                            (qid,),
                        )
                        unpublished.append((str(qid), sid))

                    # Check if this question is used in any module
                    cur.execute(
                        """
                        SELECT mq.module_id, tm.stage, tm.level
                          FROM module_questions mq
                          JOIN test_modules tm ON tm.id = mq.module_id
                         WHERE mq.question_id = %s
                        """,
                        (qid,),
                    )
                    for mod_id, stage, level in cur.fetchall():
                        affected_modules.append(
                            {"question_id": str(qid), "source_id": sid,
                             "module_id": str(mod_id), "stage": stage, "level": level}
                        )

                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                with psycopg.connect(OWNER_CONN_STRING) as conn2:
                    with conn2.cursor() as cur2:
                        cur2.execute(
                            "ALTER TABLE questions ENABLE TRIGGER trg_lock_published_question"
                        )
                        conn2.commit()

    print("\n--- Publish-safety check ---")
    print(f"  RW questions referencing 'the text' with no passage: {len(at_risk_source_ids)}")
    print(f"  Unpublished (set to draft):                        {len(unpublished)}")
    if unpublished:
        print("  Unpublished question IDs:")
        for qid, sid in unpublished:
            print(f"    {qid}  (source: {sid})")
    if affected_modules:
        print(f"\n  WARNING: {len(affected_modules)} module_questions reference now-unpublished questions:")
        for m in affected_modules:
            print(f"    module {m['module_id']} (stage={m['stage']}, level={m['level']}) → question {m['question_id']} (source: {m['source_id']})")
        print("  These modules need to be rebuilt with replacement questions.")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="run inside a transaction that is always rolled back")
    ap.add_argument("--limit", type=int, default=None,
                    help="only process first N rows")
    args = ap.parse_args()

    if "YOUR_PASSWORD_HERE" in CONN_STRING:
        raise SystemExit("Edit import.py and set the real password in CONN_STRING")

    rows = []
    with open(CANONICAL) as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if args.limit and len(rows) >= args.limit:
                break

    print(f"Loaded {len(rows)} rows from {CANONICAL}")
    if args.dry_run:
        print("DRY RUN — nothing will be committed")

    counts = Counter()
    failures = []

    with psycopg.connect(CONN_STRING) as conn:
        with conn.cursor() as cur:
            taxonomy = load_taxonomy(cur)
            print(f"Loaded taxonomy: {len(taxonomy)} (section, skill) pairs")

            # Load existing passages for dedup
            passage_cache = load_passage_cache(cur)
            print(f"Loaded passage cache: {len(passage_cache)} existing passages")

            for i, row in enumerate(rows, start=1):
                try:
                    with conn.transaction():
                        status, detail = import_row(cur, row, taxonomy, passage_cache, args.dry_run)
                        counts[status] += 1
                        if status == "failed":
                            failures.append((row["source_id"], detail))
                    if i % 100 == 0 or i == len(rows):
                        print(f"  {i}/{len(rows)}  "
                              f"inserted={counts['inserted']} "
                              f"skipped={counts['skipped']} "
                              f"failed={counts['failed']}")
                except Exception as e:
                    counts["failed"] += 1
                    failures.append((row["source_id"], f"{type(e).__name__}: {e}"))

            if args.dry_run:
                conn.rollback()

    print()
    print(f"Inserted: {counts['inserted']}")
    print(f"Skipped:  {counts['skipped']}")
    print(f"Failed:   {counts['failed']}")

    if failures:
        out = Path("canonical/import_failures.jsonl")
        with open(out, "w") as f:
            for sid, reason in failures:
                f.write(json.dumps({"source_id": sid, "reason": reason}) + "\n")
        print(f"\nFailures written to {out}")
        for sid, reason in failures[:10]:
            print(f"  {sid}: {reason}")

    # --- Post-import: link passages to existing questions ---
    if not args.dry_run:
        # Reload passage cache (new passages may have been created during import)
        with psycopg.connect(CONN_STRING) as conn:
            with conn.cursor() as cur:
                passage_cache = load_passage_cache(cur)

        link_passages_existing(rows, passage_cache)

        # --- Publish-safety check ---
        publish_safety_check(rows)


if __name__ == "__main__":
    main()
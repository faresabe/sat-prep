import psycopg

CONN = "postgresql://app_owner:fares@localhost:5432/satprep"
QID  = "8424d3ed-fad1-4997-84a5-0288b7f884e1"

with psycopg.connect(CONN) as conn, conn.cursor() as cur:
    cur.execute("SELECT stem, section, difficulty, status FROM questions WHERE id = %s", (QID,))
    stem, section, difficulty, status = cur.fetchone()

    print(f"=== {section} / {difficulty} / {status} ===")
    print()
    print("STEM:")
    print(stem)
    print()

    cur.execute("""
        SELECT c.label, c.content,
               (c.id = k.correct_choice_id) AS is_correct
          FROM question_choices c
          LEFT JOIN grading.question_keys k ON k.question_id = c.question_id
         WHERE c.question_id = %s
         ORDER BY c.position
    """, (QID,))
    print("CHOICES:")
    for label, content, is_correct in cur.fetchall():
        marker = " ← CORRECT" if is_correct else ""
        print(f"  {label}. {content}{marker}") 
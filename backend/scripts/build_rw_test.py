"""
build_rw_test.py — builds the RW demo adaptive test from configs/rw_demo.yaml.

Usage:
    cd backend
    python scripts/build_rw_test.py [--config ../configs/rw_demo.yaml]

Prints the test UUID on success. Idempotent: if a test with the same slug
already exists, it prints the existing UUID and exits.

Connects with app_owner (DATABASE_URL_MIGRATION) to bypass RLS.
"""
from __future__ import annotations

import asyncio
import random
import sys
import uuid
from pathlib import Path

import yaml

# Allow running from the backend/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings


CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "rw_demo.yaml"


async def main(config_path: Path = CONFIG_PATH) -> None:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    engine = create_async_engine(settings.database_url_migration, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # Check if test already exists
        existing = (
            await db.execute(
                text("SELECT id FROM tests WHERE slug = :slug"),
                {"slug": cfg["test"]["slug"]},
            )
        ).first()

        if existing:
            print(f"Test already exists: {existing[0]}")
            return

        # Create test — start as DRAFT, publish after sections+modules are created
        test_id = (
            await db.execute(
                text(
                    """
                    INSERT INTO tests (slug, title, description, test_type,
                                       is_adaptive, status)
                    VALUES (:slug, :title, :desc, :ttype, :adaptive, 'draft')
                    RETURNING id
                    """
                ),
                {
                    "slug": cfg["test"]["slug"],
                    "title": cfg["test"]["title"],
                    "desc": cfg["test"].get("description"),
                    "ttype": cfg["test"]["test_type"],
                    "adaptive": cfg["test"]["is_adaptive"],
                },
            )
        ).scalar_one()

        # Create section
        section_id = (
            await db.execute(
                text(
                    """
                    INSERT INTO test_sections (test_id, section, position,
                                               break_seconds, break_skippable)
                    VALUES (:tid, :sect, :pos, :brk, :skip)
                    RETURNING id
                    """
                ),
                {
                    "tid": str(test_id),
                    "sect": cfg["section"]["section"],
                    "pos": cfg["section"]["position"],
                    "brk": cfg["section"].get("break_seconds"),
                    "skip": cfg["section"]["break_skippable"],
                },
            )
        ).scalar_one()

        # Helper: create a module and assign questions
        async def create_module(module_cfg: dict) -> None:
            module_id = (
                await db.execute(
                    text(
                        """
                        INSERT INTO test_modules
                            (section_id, stage, level, time_limit_sec, question_target,
                             routing_threshold, routing_weight_easy,
                             routing_weight_medium, routing_weight_hard)
                        VALUES (:sid, :stage, :level, :tl, :qt, :thresh, :we, :wm, :wh)
                        RETURNING id
                        """
                    ),
                    {
                        "sid": str(section_id),
                        "stage": module_cfg["stage"],
                        "level": module_cfg["level"],
                        "tl": module_cfg["time_limit_sec"],
                        "qt": module_cfg["question_target"],
                        "thresh": module_cfg.get("routing_threshold"),
                        "we": module_cfg.get("routing_weight_easy"),
                        "wm": module_cfg.get("routing_weight_medium"),
                        "wh": module_cfg.get("routing_weight_hard"),
                    },
                )
            ).scalar_one()

            # Select questions
            sel = module_cfg["question_selection"]
            seed = sel.get("seed", 0)
            rng = random.Random(seed)

            dist = sel.get("difficulty_distribution")
            if dist:
                qids: list[uuid.UUID] = []
                for diff, count in dist.items():
                    rows = (
                        await db.execute(
                            text(
                                """
                                SELECT id FROM questions
                                 WHERE section = :sect
                                   AND difficulty = :diff
                                   AND status = 'published'
                                 ORDER BY random()
                                 LIMIT :n
                                """
                            ),
                            {"sect": sel.get("section", "RW"), "diff": diff, "n": count * 3},
                        )
                    ).scalars().all()
                    if len(rows) < count:
                        print(f"Warning: only {len(rows)} {diff} questions available (need {count})")
                    picked = rng.sample(rows, min(count, len(rows)))
                    qids.extend(picked)
                rng.shuffle(qids)
            else:
                rows = (
                    await db.execute(
                        text(
                            """
                            SELECT id FROM questions
                             WHERE section = :sect
                               AND status = 'published'
                             ORDER BY random()
                             LIMIT :n
                            """
                        ),
                        {"sect": sel.get("section", "RW"), "n": sel["count"] * 3},
                    )
                ).scalars().all()
                qids = rng.sample(rows, min(sel["count"], len(rows)))

            for pos, qid in enumerate(qids, start=1):
                await db.execute(
                    text(
                        "INSERT INTO module_questions (module_id, question_id, position) "
                        "VALUES (:mid, :qid, :pos)"
                    ),
                    {"mid": str(module_id), "qid": str(qid), "pos": pos},
                )

        await create_module(cfg["module_1"])
        await create_module(cfg["module_2_easy"])
        await create_module(cfg["module_2_hard"])

        # Publish after all content is in place
        await db.execute(
            text("UPDATE tests SET status='published', published_at=now() WHERE id=:id"),
            {"id": str(test_id)},
        )

        await db.commit()
        print(f"Created test: {test_id}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    asyncio.run(main(args.config))

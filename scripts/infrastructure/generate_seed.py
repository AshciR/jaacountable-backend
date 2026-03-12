#!/usr/bin/env python3
"""
Generate seed data for local development database.

Prerequisites:
  - Database running and migrated: ./scripts/infrastructure/init-db.sh
  - .env file with DATABASE_URL and OPENAI_API_KEY
  - Internet access (sitemap crawling)

Usage:
  uv run python scripts/infrastructure/generate_seed.py
  uv run python scripts/infrastructure/generate_seed.py --start-date 2026-03-03 --end-date 2026-03-09
  uv run python scripts/infrastructure/generate_seed.py --dry-run
  uv run python scripts/infrastructure/generate_seed.py --discovery-only
  uv run python scripts/infrastructure/generate_seed.py --pipeline-only
  uv run python scripts/infrastructure/generate_seed.py --dump-only
  uv run python scripts/infrastructure/generate_seed.py --pipeline-only --source observer
"""

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DISCOVERY_OUTPUT = PROJECT_ROOT / "scripts/production/discovery/output"
POSTGRES_CONTAINER = os.environ.get("POSTGRES_CONTAINER", "postgres")

# Hardcoded snapshot week defaults — update when regenerating seed data
DEFAULT_START_DATE = "2026-03-03"
DEFAULT_END_DATE = "2026-03-09"


def is_container_running(container: str) -> bool:
    result = subprocess.run(
        ["docker", "inspect", "--format={{.State.Running}}", container],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def discover_articles(script: str, step: str, start_date: str, end_date: str, output_file: Path) -> None:
    """Run a discovery script, skipping if the output file already exists."""
    if output_file.exists():
        print(f"[{step}] Skipping discovery (file exists: {output_file.name})")
        return
    print(f"[{step}] Running {Path(script).stem}...")
    run(
        [
            "uv", "run", "python", script,
            "--start-date", start_date,
            "--end-date", end_date,
            "--output-dir", str(DISCOVERY_OUTPUT),
        ],
        cwd=PROJECT_ROOT,
    )


def run_pipeline(sources: list[tuple[str, Path]]) -> None:
    """Run the extract + classify + store pipeline for each JSONL file."""
    print("[3/4] Running pipeline (extract + classify + store)...")
    for label, jsonl in sources:
        print(f"  Processing {label} ({jsonl.name})...")
        run(
            [
                "uv", "run", "python",
                "scripts/production/classification/process_articles_batch.py",
                "--input", str(jsonl),
                "--concurrency", "4",
                "--skip-existing",
            ],
            cwd=PROJECT_ROOT,
        )


def dump_database(seed_sql: Path, start_date: str, end_date: str) -> None:
    """Dump database to seed.sql (data-only, COPY format preserves sequences via SELECT setval(...))."""
    print("[4/4] Dumping database to seed.sql...")
    header = "\n".join(
        [
            "-- Seed data for jaacountable-backend local development",
            f"-- Generated: {date.today().isoformat()}",
            f"-- Date range: {start_date} to {end_date}",
            "-- Sources: Jamaica Gleaner (news_source_id=1), Jamaica Observer (news_source_id=2)",
            "-- Usage: uv run python scripts/infrastructure/seed_db.py",
            "",
        ]
    )
    dump = subprocess.run(
        [
            "docker", "exec", POSTGRES_CONTAINER,
            "pg_dump",
            "--username=user",
            "--dbname=jaacountable_db",
            "--data-only",
            "--no-owner",
            "--no-privileges",
            "--exclude-table=alembic_version",
            "--exclude-table=news_sources",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    seed_sql.write_text(header + dump.stdout)
    size_kb = seed_sql.stat().st_size // 1024
    print(f"Done! seed.sql: {size_kb} KB")
    print(f"Next: git add {seed_sql.relative_to(PROJECT_ROOT)} && git commit")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE,
        help=f"Start of date range YYYY-MM-DD (default: {DEFAULT_START_DATE})",
    )
    parser.add_argument(
        "--end-date",
        default=DEFAULT_END_DATE,
        help=f"End of date range YYYY-MM-DD (default: {DEFAULT_END_DATE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check prerequisites (container, discovery files, API key) without running anything",
    )
    parser.add_argument(
        "--dump-only",
        action="store_true",
        help="Skip discovery and pipeline; only run pg_dump to regenerate seed.sql from current DB state",
    )
    parser.add_argument(
        "--pipeline-only",
        action="store_true",
        help="Skip discovery; run pipeline then pg_dump (requires discovery JSONL files to already exist)",
    )
    parser.add_argument(
        "--discovery-only",
        action="store_true",
        help="Run discovery only; skip pipeline and pg_dump",
    )
    parser.add_argument(
        "--source",
        choices=["gleaner", "observer"],
        default=None,
        help="Limit pipeline to a single source (default: both). Applies to --pipeline-only and full runs.",
    )
    args = parser.parse_args()

    start_date = args.start_date
    end_date = args.end_date
    seed_sql = SCRIPT_DIR / "seed.sql"
    gleaner_jsonl = DISCOVERY_OUTPUT / f"gleaner_sitemap_{start_date}_to_{end_date}.jsonl"
    observer_jsonl = DISCOVERY_OUTPUT / f"jamaica_observer_{start_date}_to_{end_date}.jsonl"

    all_sources = [("Gleaner", gleaner_jsonl), ("Observer", observer_jsonl)]
    # When --source is given, restrict pipeline steps to that source only.
    # This lets you re-run a single source without reprocessing the other.
    selected_sources = (
        [(label, jsonl) for label, jsonl in all_sources if label.lower() == args.source]
        if args.source
        else all_sources
    )

    # Always check container first — fail early regardless of mode
    if not is_container_running(POSTGRES_CONTAINER):
        print(f"ERROR: Postgres container '{POSTGRES_CONTAINER}' is not running.")
        print("Run: ./scripts/infrastructure/start-db.sh")
        return 1

    if args.discovery_only:
        discover_articles(
            "scripts/production/discovery/discover_gleaner_archive_articles_via_sitemap.py",
            "1/2",
            start_date,
            end_date,
            gleaner_jsonl,
        )
        discover_articles(
            "scripts/production/discovery/discover_jamaica_observer_articles_via_sitemap.py",
            "2/2",
            start_date,
            end_date,
            observer_jsonl,
        )
        return 0

    if args.dump_only:
        dump_database(seed_sql, start_date, end_date)
        return 0

    if args.pipeline_only:
        load_dotenv(PROJECT_ROOT / ".env")
        if not os.environ.get("OPENAI_API_KEY"):
            print("ERROR: OPENAI_API_KEY required in .env")
            return 1
        for label, jsonl in selected_sources:
            if not jsonl.exists():
                print(f"ERROR: {label} JSONL not found: {jsonl}")
                print("Run without --pipeline-only to run discovery first.")
                return 1
        run_pipeline(selected_sources)
        print()
        dump_database(seed_sql, start_date, end_date)
        return 0

    if args.dry_run:
        load_dotenv(PROJECT_ROOT / ".env")
        api_key_present = bool(os.environ.get("OPENAI_API_KEY"))

        print(f"Dry-run preflight check ({start_date} to {end_date})")
        print(f"  Container '{POSTGRES_CONTAINER}': running")
        print(f"  Gleaner JSONL:  {'FOUND' if gleaner_jsonl.exists() else 'MISSING'} ({gleaner_jsonl.name})")
        print(f"  Observer JSONL: {'FOUND' if observer_jsonl.exists() else 'MISSING'} ({observer_jsonl.name})")
        print(f"  seed.sql:       {'EXISTS (will overwrite)' if seed_sql.exists() else 'not yet generated'}")
        print(f"  OPENAI_API_KEY: {'set' if api_key_present else 'MISSING'}")

        all_ok = gleaner_jsonl.exists() and observer_jsonl.exists() and api_key_present
        print()
        if all_ok:
            print("All prerequisites met. Discovery will be skipped (files already exist).")
        else:
            print("Some prerequisites are missing — see above.")
        return 0 if all_ok else 1

    # Load .env for API key validation
    load_dotenv(PROJECT_ROOT / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY required in .env")
        return 1

    print(f"Generating seed data: {start_date} to {end_date}")
    print()

    # Steps 1 & 2: Discover articles from each source
    discover_articles(
        "scripts/production/discovery/discover_gleaner_archive_articles_via_sitemap.py",
        "1/4",
        start_date,
        end_date,
        gleaner_jsonl,
    )
    discover_articles(
        "scripts/production/discovery/discover_jamaica_observer_articles_via_sitemap.py",
        "2/4",
        start_date,
        end_date,
        observer_jsonl,
    )

    # Step 3: Pipeline (extract + classify + store)
    run_pipeline(selected_sources)

    # Step 4: pg_dump
    print()
    dump_database(seed_sql, start_date, end_date)
    return 0


if __name__ == "__main__":
    sys.exit(main())

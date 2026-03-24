# Infrastructure Scripts

Scripts for managing the local development database and server.

---

## Everyday workflows

### Docker Compose stack — cold start (first time or after wiping volumes)
```bash
./scripts/infrastructure/compose-cold-start.sh
SEED_DB=true ./scripts/infrastructure/compose-cold-start.sh
```

### Standalone database — fresh setup (first time or after a clean)
```bash
./scripts/infrastructure/init-db.sh
```

### Standalone database — fresh setup with seed data
```bash
SEED_DB=true ./scripts/infrastructure/init-db.sh
```

### Standalone database — wipe everything and start over
```bash
./scripts/infrastructure/clean-db.sh && SEED_DB=true ./scripts/infrastructure/init-db.sh
```

---

## Script reference

### `compose-cold-start.sh`
Cold starts the full docker-compose stack from scratch. Tears down existing containers and volumes, starts postgres, runs migrations via `migrate.sh`, optionally seeds via `seed_db.sh`, then starts the app container.

Use this when the postgres volume doesn't exist yet (first run, or after `docker-compose down -v`). For normal restarts where the volume is intact, use `docker-compose up` directly.

```bash
./scripts/infrastructure/compose-cold-start.sh
SEED_DB=true ./scripts/infrastructure/compose-cold-start.sh
```

---

### `init-db.sh`
Starts the database container and runs all Alembic migrations. The go-to script for getting a working database.

Set `SEED_DB=true` to also load seed data after migrations.

```bash
./scripts/infrastructure/init-db.sh
SEED_DB=true ./scripts/infrastructure/init-db.sh
```

---

### `clean-db.sh`
Stops the database container and removes all data volumes. Leaves a clean slate.

Run `init-db.sh` afterwards to get back to a working state.

```bash
./scripts/infrastructure/clean-db.sh
```

---

### `start-db.sh`
Starts the PostgreSQL Docker container and waits for it to pass the health check. Called automatically by `init-db.sh` — use directly only if you need to start the container without running migrations.

```bash
./scripts/infrastructure/start-db.sh
```

---

### `migrate.sh`
Runs Alembic migrations against the database. Accepts an optional env file argument (defaults to `.env`).

```bash
./scripts/infrastructure/migrate.sh              # uses .env
./scripts/infrastructure/migrate.sh .staging.env
```

---

### `create-migration.sh`
Generates a new Alembic migration file. After running, edit the generated file in `alembic/versions/` to add your SQL DDL to the `upgrade()` and `downgrade()` functions.

```bash
./scripts/infrastructure/create-migration.sh "add classifications table"
```

---

### `seed_db.sh`
Loads `seed.sql` into the running database. The database must already be running and migrated. Use when you want to load seed data independently of `init-db.sh`.

```bash
./scripts/infrastructure/seed_db.sh
```

---

### `generate_seed.py`
Operator script that generates `seed.sql` by running discovery, classification pipeline, and `pg_dump`. Requires `OPENAI_API_KEY` and internet access. Intended to be run by maintainers when seed data needs to be regenerated.

**Flags:**

| Flag | Description |
|------|-------------|
| _(none)_ | Full run: discover → pipeline → dump |
| `--discovery-only` | Run discovery only, write JSONL files |
| `--pipeline-only` | Skip discovery, run pipeline → dump (JSONL files must exist) |
| `--dump-only` | Skip discovery and pipeline, just re-run `pg_dump` |
| `--dry-run` | Preflight check: verify container, JSONL files, and API key — no side effects |
| `--source gleaner\|observer` | Limit pipeline steps to a single source (combinable with `--pipeline-only`) |
| `--start-date` | Start of date range, YYYY-MM-DD (default: `2026-03-03`) |
| `--end-date` | End of date range, YYYY-MM-DD (default: `2026-03-09`) |

```bash
# Check readiness before a full run
uv run python scripts/infrastructure/generate_seed.py --dry-run

# Full run (discover both sources, classify, dump)
uv run python scripts/infrastructure/generate_seed.py

# Re-run pipeline for observer only (e.g. after fixing an extraction bug)
uv run python scripts/infrastructure/generate_seed.py --pipeline-only --source observer

# Re-dump without re-classifying (e.g. after a failed dump)
uv run python scripts/infrastructure/generate_seed.py --dump-only
```

After generating, commit the result:
```bash
git add scripts/infrastructure/seed.sql
git commit -m "chore: regenerate seed data 2026-03-03 to 2026-03-09"
```

---

### `start-server.sh`
Starts the FastAPI development server.

```bash
./scripts/infrastructure/start-server.sh
```

---

### `test-db-connection.py`
Verifies database connectivity and credentials. Works with both local Docker and remote databases (e.g. Supabase staging).

```bash
uv run python scripts/infrastructure/test-db-connection.py

# Against staging
set -a; source .staging.env; set +a
uv run python scripts/infrastructure/test-db-connection.py
```

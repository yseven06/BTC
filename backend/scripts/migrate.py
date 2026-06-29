"""
Tracked migration runner — versioned, ordered, recorded.

Applies migrations/000X_*.sql in filename order, recording each in a
``schema_migrations`` table so it is **never applied twice**. This is the project's
migration discipline:

  * Fresh deploy → ``migrate.py`` applies every migration once, in order.
  * Existing DB (already built via create_all + the earlier manual SQL) → run
    ``migrate.py stamp`` ONCE to mark the current migrations as applied **without
    re-running them** (critical: some migrations are destructive on re-run, e.g.
    0003 does ``DELETE FROM notification_settings``), then only NEW migrations run.

Each migration .sql must stay idempotent (IF NOT EXISTS / guarded) and use one
statement per line ending in ';' (no DO/$$ blocks — the splitter is line-based).

Why not Alembic: the live Supabase schema was bootstrapped via create_all + these
idempotent SQL files; retrofitting Alembic's autogenerate onto it is higher-risk
than this small tracked runner. Alembic stays available (dependency present) if
richer autogeneration is needed later.

Usage:
  python scripts/migrate.py status   # show applied / pending
  python scripts/migrate.py stamp    # mark all current migrations applied (existing-DB adoption); does NOT run them
  python scripts/migrate.py          # apply pending migrations in order
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(_BACKEND, "migrations")


def _migration_files():
    return sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql"))


def split_sql(sql: str):
    stmts, cur = [], []
    for line in sql.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        cur.append(line)
        if s.endswith(";"):
            stmts.append("\n".join(cur).strip().rstrip(";").strip())
            cur = []
    tail = "\n".join(cur).strip().rstrip(";").strip()
    if tail:
        stmts.append(tail)
    return [s for s in stmts if s]


async def _ensure_table(conn):
    await conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "filename VARCHAR(255) PRIMARY KEY, "
        "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )


async def _applied(conn):
    r = await conn.exec_driver_sql("SELECT filename FROM schema_migrations")
    return {row[0] for row in r}


async def main(mode: str):
    async with engine.begin() as conn:
        await _ensure_table(conn)
        applied = await _applied(conn)
        files = _migration_files()
        pending = [f for f in files if f not in applied]

        if mode == "status":
            print("APPLIED:", sorted(applied) or "(none)")
            print("PENDING:", pending or "(none)")
        elif mode == "stamp":
            for f in pending:
                await conn.exec_driver_sql(
                    f"INSERT INTO schema_migrations(filename) VALUES ('{f}') ON CONFLICT DO NOTHING"
                )
            print("STAMPED (marked applied, NOT run):", pending or "(none pending)")
        else:  # apply
            if not pending:
                print("Up to date — no pending migrations.")
            await conn.exec_driver_sql("SET lock_timeout = '5s'")
            await conn.exec_driver_sql("SET statement_timeout = '60s'")
            for f in pending:
                print(">> applying", f)
                with open(os.path.join(MIGRATIONS_DIR, f), encoding="utf-8") as fh:
                    for st in split_sql(fh.read()):
                        await conn.exec_driver_sql(st)
                await conn.exec_driver_sql(
                    f"INSERT INTO schema_migrations(filename) VALUES ('{f}')"
                )
            print("DONE. Applied:", pending or "(none)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "apply"))

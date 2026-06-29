"""
One-off migration runner. Executes a .sql file statement-by-statement inside a
single transaction with a short lock_timeout so an ALTER can never hang on an
idle-in-transaction lock (fails fast instead). Idempotent SQL expected.

Usage:  python scripts/run_migration.py migrations/0001_consent_log.sql
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine


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


async def main(path: str):
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    stmts = split_sql(sql)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("SET lock_timeout = '5s'")
        await conn.exec_driver_sql("SET statement_timeout = '30s'")
        for st in stmts:
            print(">>", st.splitlines()[0][:72])
            await conn.exec_driver_sql(st)
    await engine.dispose()
    print("MIGRATION OK")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))

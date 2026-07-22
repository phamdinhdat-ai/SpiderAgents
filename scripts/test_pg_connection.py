#!/usr/bin/env python3
"""Quick test: PostgreSQL connection + table creation."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openspider.db.engine import DatabaseManager, init_db


async def main():
    db = DatabaseManager()
    await db.start()
    print("[OK] Database connection established.")

    await init_db()
    print("[OK] Tables verified / created.")

    # List tables to confirm
    from openspider.db.engine import get_engine
    from sqlalchemy import text

    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        )
        tables = [row[0] for row in result]
        print(f"[OK] Tables in database ({len(tables)}):")
        for t in tables:
            print(f"     - {t}")

    await db.close()

if __name__ == "__main__":
    asyncio.run(main())

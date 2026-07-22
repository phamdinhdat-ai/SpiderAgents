#!/usr/bin/env python3
"""End-to-end test: Settings store with PG backend."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openspider.db.engine import DatabaseManager, init_db
from openspider.app.settings_store import SettingsStore


async def main():
    db = DatabaseManager()
    await db.start()
    await init_db()
    print("[OK] Database ready.")

    # Test SettingsStore (PG enabled)
    store = SettingsStore()
    print(f"  PG enabled: {store.pg_enabled}")

    # Save settings
    await store.save({
        "language": "vi",
        "builtin_skill_language": "vi",
        "storage_backends": {
            "file_storage": {"backend": "local"},
            "vector_store": {"backend": "auto"},
        },
    })
    print("[OK] Settings saved.")

    # Load settings
    data = await store.load()
    print(f"  Loaded: language={data.get('language')}, "
          f"storage_backends={data.get('storage_backends')}")

    assert data.get("language") == "vi"
    assert data.get("builtin_skill_language") == "vi"
    assert data["storage_backends"]["file_storage"]["backend"] == "local"

    print("[OK] Settings verified.")

    await db.close()
    print("[OK] All settings tests passed!")


if __name__ == "__main__":
    asyncio.run(main())

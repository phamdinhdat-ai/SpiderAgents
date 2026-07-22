#!/usr/bin/env python3
"""End-to-end test: PostgreSQL auth operations."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openspider.db.engine import DatabaseManager, init_db
from openspider.db.repos.pg_auth_store import (
    authenticate as pg_authenticate,
    register_user as pg_register,
    list_users as pg_list_users,
    verify_token as pg_verify,
    has_registered_users as pg_has_users,
    get_user_count as pg_count,
    delete_user as pg_delete,
)
from openspider.db.engine import get_session_factory


async def main():
    db = DatabaseManager()
    await db.start()
    await init_db()
    print("[OK] Database ready.")

    sf = get_session_factory()
    async with sf() as sess:
        # Check initial state
        has_users = await pg_has_users(sess)
        count = await pg_count(sess)
        print(f"  Initial: has_users={has_users}, count={count}")

        # Register a test user
        token = await pg_register(sess, "testuser", "testpass123")
        if token:
            print(f"[OK] Registered testuser, token={token[:20]}...")
        else:
            print("[FAIL] Registration failed")
            return

        # Verify the user exists
        has_users = await pg_has_users(sess)
        count = await pg_count(sess)
        print(f"  After register: has_users={has_users}, count={count}")

        # Authenticate
        auth_token = await pg_authenticate(sess, "testuser", "testpass123")
        if auth_token:
            print(f"[OK] Authenticated, token={auth_token[:20]}...")
        else:
            print("[FAIL] Authentication failed")
            return

        # Verify token
        result = await pg_verify(sess, auth_token)
        if result:
            username, role = result
            print(f"[OK] Token verified: username={username}, role={role}")
        else:
            print("[FAIL] Token verification failed")
            return

        # List users
        users = await pg_list_users(sess)
        print(f"[OK] Users: {users}")

        # Clean up
        deleted = await pg_delete(sess, "testuser")
        print(f"[OK] Deleted testuser: {deleted}")

        await sess.commit()

    await db.close()
    print("[OK] All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())

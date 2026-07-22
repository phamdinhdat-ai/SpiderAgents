# -*- coding: utf-8 -*-
"""PostgreSQL repository implementations.

Each module replaces a specific part of the legacy file/SQLite storage:
- :mod:`.pg_auth_store` — was ``auth.json``
- :mod:`.pg_user_data_store` — was ``user_data.db`` (SQLite)
- :mod:`.pg_chat_repository` — was ``chats.json``
- :mod:`.pg_user_storage` — was ``USERS_DIR/<hash>/`` (file tree)
"""

from .pg_auth_store import (
    authenticate,
    create_token,
    delete_user,
    get_user,
    get_user_count,
    has_registered_users,
    list_users,
    register_user,
    revoke_all_tokens,
    revoke_token,
    update_credentials,
    update_user_role,
    verify_password,
    verify_token,
)
from .pg_chat_repository import PgChatRepository
from .pg_user_data_store import PgUserDataStore
from .pg_user_storage import PgUserStorageManager

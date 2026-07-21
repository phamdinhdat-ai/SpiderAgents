# -*- coding: utf-8 -*-
"""File storage backends for knowledge base documents.

Provides pluggable backends:
- :class:`LocalStorageBackend` — local filesystem (default)
- :class:`MinioStorageBackend` — S3-compatible MinIO (optional, requires ``minio``)
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class StorageBackend(ABC):
    """Abstract file storage backend for knowledge base documents."""

    @abstractmethod
    async def start(self) -> None:
        """Initialise and connect to the backend."""

    @abstractmethod
    async def close(self) -> None:
        """Flush and release backend resources."""

    @abstractmethod
    async def store(
        self,
        source_path: Path,
        dest_dir: str,
        filename: str,
    ) -> str:
        """Persist a file and return its stored-path identifier.

        Args:
            source_path: Local path to the file to store.
            dest_dir: Logical destination directory (e.g. ``"alice"``).
            filename: Target filename (already de-duplicated by caller).

        Returns:
            An opaque stored-path identifier that can be passed back to
            :meth:`retrieve` and :meth:`delete`.
        """

    @abstractmethod
    async def retrieve(self, stored_path: str) -> Path:
        """Fetch a stored file to a local temp path.

        Returns the path to a *temporary* local copy.  Callers must
        clean up the returned file when done.
        """

    @abstractmethod
    async def delete(self, stored_path: str) -> bool:
        """Remove a stored file.  Returns ``True`` on success."""

    @abstractmethod
    async def exists(self, stored_path: str) -> bool:
        """Check whether a stored file exists."""


# ---------------------------------------------------------------------------
# Local filesystem backend
# ---------------------------------------------------------------------------


class LocalStorageBackend(StorageBackend):
    """Store files on the local filesystem.

    Files are written under ``{root_dir}/{dest_dir}/{filename}``.
    """

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir)

    async def start(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    async def close(self) -> None:
        pass  # nothing to flush

    async def store(
        self,
        source_path: Path,
        dest_dir: str,
        filename: str,
    ) -> str:
        dest = self._root / dest_dir / Path(filename).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source_path), str(dest))
        return str(dest)

    async def retrieve(self, stored_path: str) -> Path:
        p = Path(stored_path)
        if not p.is_file():
            raise FileNotFoundError(f"Stored file not found: {stored_path}")
        # For local storage we can return the path directly — no copy needed
        # since it is already on the local filesystem.
        return p

    async def delete(self, stored_path: str) -> bool:
        p = Path(stored_path)
        try:
            if p.is_file():
                p.unlink()
                return True
            return False
        except OSError:
            return False

    async def exists(self, stored_path: str) -> bool:
        return Path(stored_path).is_file()


# ---------------------------------------------------------------------------
# MinIO / S3 backend
# ---------------------------------------------------------------------------


class MinioStorageBackend(StorageBackend):
    """Store files in a MinIO (S3-compatible) bucket.

    Requires the ``minio`` package: ``pip install minio``.

    Objects are stored under the key prefix ``{prefix}/{dest_dir}/{filename}``.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str = "openspider-kb",
        secure: bool = False,
        prefix: str = "knowledge_base",
    ) -> None:
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._secure = secure
        self._prefix = prefix.strip("/")
        self._client: object = None  # minio.Minio

    async def start(self) -> None:
        try:
            from minio import Minio
        except ImportError:
            raise RuntimeError(
                "minio package is required for MinioStorageBackend. "
                "Install it: pip install minio",
            ) from None

        import asyncio

        def _init():
            client = Minio(
                self._endpoint,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=self._secure,
            )
            # Ensure bucket exists
            if not client.bucket_exists(self._bucket):
                client.make_bucket(self._bucket)
                logger.info("Created MinIO bucket: %s", self._bucket)
            return client

        self._client = await asyncio.to_thread(_init)
        logger.info(
            "MinioStorageBackend ready: endpoint=%s bucket=%s",
            self._endpoint,
            self._bucket,
        )

    async def close(self) -> None:
        self._client = None

    def _object_name(self, dest_dir: str, filename: str) -> str:
        safe_name = Path(filename).name
        prefix = f"{self._prefix}/{dest_dir}" if self._prefix else dest_dir
        return f"{prefix}/{safe_name}"

    @property
    def _mc(self):  # -> minio.Minio
        if self._client is None:
            raise RuntimeError("MinioStorageBackend not started")
        return self._client

    async def store(
        self,
        source_path: Path,
        dest_dir: str,
        filename: str,
    ) -> str:
        import asyncio

        obj_name = self._object_name(dest_dir, filename)

        def _put():
            self._mc.fput_object(
                self._bucket,
                obj_name,
                str(source_path),
            )

        await asyncio.to_thread(_put)
        # Return a URI-style identifier
        scheme = "https" if self._secure else "http"
        return f"s3://{self._bucket}/{obj_name}"

    async def retrieve(self, stored_path: str) -> Path:
        import asyncio

        # Parse s3://bucket/key → (bucket, key)
        if stored_path.startswith("s3://"):
            parts = stored_path[5:].split("/", 1)
            obj_name = parts[1] if len(parts) > 1 else ""
        else:
            obj_name = stored_path

        suffix = Path(obj_name).suffix
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.close()

        def _get():
            self._mc.fget_object(self._bucket, obj_name, tmp.name)

        await asyncio.to_thread(_get)
        return Path(tmp.name)

    async def delete(self, stored_path: str) -> bool:
        import asyncio

        if stored_path.startswith("s3://"):
            parts = stored_path[5:].split("/", 1)
            obj_name = parts[1] if len(parts) > 1 else ""
        else:
            obj_name = stored_path

        def _remove():
            try:
                self._mc.remove_object(self._bucket, obj_name)
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_remove)

    async def exists(self, stored_path: str) -> bool:
        import asyncio

        if stored_path.startswith("s3://"):
            parts = stored_path[5:].split("/", 1)
            obj_name = parts[1] if len(parts) > 1 else ""
        else:
            obj_name = stored_path

        def _check():
            try:
                self._mc.stat_object(self._bucket, obj_name)
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_check)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_storage_backend(
    config: Optional[dict] = None,
    root_dir: str = "",
) -> StorageBackend:
    """Create a :class:`StorageBackend` from configuration.

    Args:
        config: Backend configuration dict with keys:
            - ``backend``: ``"local"`` (default) or ``"minio"``
            - ``minio_endpoint``, ``minio_access_key``, ``minio_secret_key``,
              ``minio_bucket``, ``minio_secure``, ``minio_prefix``
        root_dir: Local root directory (used by ``LocalStorageBackend``).

    Returns:
        A configured :class:`StorageBackend`.
    """
    cfg = config or {}
    backend = cfg.get("backend", "local")

    if backend == "minio":
        endpoint = cfg.get("minio_endpoint", "")
        access_key = cfg.get("minio_access_key", "")
        secret_key = cfg.get("minio_secret_key", "")
        if not endpoint or not access_key or not secret_key:
            logger.warning(
                "MinIO config incomplete — falling back to local storage",
            )
            return LocalStorageBackend(root_dir)
        return MinioStorageBackend(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket=cfg.get("minio_bucket", "openspider-kb"),
            secure=cfg.get("minio_secure", False),
            prefix=cfg.get("minio_prefix", "knowledge_base"),
        )

    # Default: local
    return LocalStorageBackend(root_dir)

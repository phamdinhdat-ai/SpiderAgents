# -*- coding: utf-8 -*-
"""Agent Markdown manager for reading and writing markdown files in working
and memory directories."""
from datetime import datetime
from pathlib import Path

from ..utils.file_handling import read_text_file_with_encoding_fallback
from ...config.config import load_agent_config

# Files that are part of the agent's core configuration / identity.
# These are NOT user documents — they belong in Settings, not the Files tab.
_SYSTEM_FILE_NAMES: frozenset[str] = frozenset({
    "SOUL.md",
    "AGENTS.md",
    "BOOTSTRAP.md",
    "HEARTBEAT.md",
    "PROFILE.md",
    "MEMORY.md",
})


class AgentMdManager:
    """Manager for reading and writing markdown files in working and memory
    directories."""

    def __init__(
        self,
        working_dir: str | Path,
        agent_id: str | None = None,
    ):
        """Initialize directories for working and memory markdown files.

        Args:
            working_dir: Path to agent's working directory
            agent_id: Optional agent ID for loading memory_dir from config.
                      If None, uses default "memory" directory.
        """
        self.working_dir: Path = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)

        # Dynamically get memory_dir from config if agent_id provided
        if agent_id:
            agent_config = load_agent_config(agent_id)
            memory_dir_name = agent_config.running.daily_memory_dir
        else:
            memory_dir_name = "memory"

        self.memory_dir: Path = self.working_dir / memory_dir_name
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def list_working_mds(
        self,
        *,
        include_system: bool = False,
    ) -> list[dict]:
        """List markdown files with metadata in the working dir.

        Args:
            include_system: If False (default), system config files
                (SOUL.md, BOOTSTRAP.md, etc.) are excluded so the
                Files tab only shows user documents.

        Returns files sorted by modification time descending (newest first).

        Returns:
            list[dict]: A list of dictionaries, each containing:
                - filename: name of the file (with .md extension)
                - size: file size in bytes
                - created_time: file creation timestamp
                - modified_time: file modification timestamp
        """
        md_files = list(self.working_dir.glob("*.md"))
        # Sort by modification time descending (newest first)
        md_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        result = []
        for f in md_files:
            if f.is_file():
                # Exclude system config files from user document view
                if not include_system and f.name in _SYSTEM_FILE_NAMES:
                    continue
                stat = f.stat()
                result.append(
                    {
                        "filename": f.name,
                        "size": stat.st_size,
                        "path": str(f),
                        "created_time": datetime.fromtimestamp(
                            stat.st_ctime,
                        ).isoformat(),
                        "modified_time": datetime.fromtimestamp(
                            stat.st_mtime,
                        ).isoformat(),
                    },
                )
        return result

    def _file_info(self, f: Path) -> dict:
        """Build a file-info dict for a single file."""
        stat = f.stat()
        return {
            "filename": f.name,
            "size": stat.st_size,
            "path": str(f),
            "created_time": datetime.fromtimestamp(
                stat.st_ctime,
            ).isoformat(),
            "modified_time": datetime.fromtimestamp(
                stat.st_mtime,
            ).isoformat(),
        }

    def list_documents(self) -> list[dict]:
        """List all files in the ``documents/`` subdirectory.

        These are user-uploaded documents (PDFs, images, text files, etc.).
        Returns files sorted by modification time descending (newest first).
        """
        docs_dir = self.working_dir / "documents"
        if not docs_dir.is_dir():
            return []

        all_files = [f for f in docs_dir.iterdir() if f.is_file()]
        all_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        return [self._file_info(f) for f in all_files]

    def read_working_md(self, md_name: str) -> str:
        """Read markdown file content from the working directory.

        Returns:
            str: The file content as string
        """
        # Auto-append .md extension if not present
        if not md_name.endswith(".md"):
            md_name += ".md"
        file_path = self.working_dir / md_name
        if not file_path.exists():
            raise FileNotFoundError(f"Working md file not found: {md_name}")

        return read_text_file_with_encoding_fallback(file_path).strip()

    def write_working_md(self, md_name: str, content: str):
        """Write markdown content to a file in the working directory."""
        # Auto-append .md extension if not present
        if not md_name.endswith(".md"):
            md_name += ".md"
        file_path = self.working_dir / md_name
        file_path.write_text(content, encoding="utf-8")

    def list_memory_mds(self) -> list[dict]:
        """List all markdown files with metadata in the memory dir.

        Returns files sorted by modification time descending (newest first).

        Returns:
            list[dict]: A list of dictionaries, each containing:
                - filename: name of the file (with .md extension)
                - size: file size in bytes
                - created_time: file creation timestamp
                - modified_time: file modification timestamp
        """
        md_files = list(self.memory_dir.glob("*.md"))
        # Sort by modification time descending (newest first)
        md_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        result = []
        for f in md_files:
            if f.is_file():
                stat = f.stat()
                result.append(
                    {
                        "filename": f.name,
                        "size": stat.st_size,
                        "path": str(f),
                        "created_time": datetime.fromtimestamp(
                            stat.st_ctime,
                        ).isoformat(),
                        "modified_time": datetime.fromtimestamp(
                            stat.st_mtime,
                        ).isoformat(),
                    },
                )
        return result

    def read_memory_md(self, md_name: str) -> str:
        """Read markdown file content from the memory directory.

        Returns:
            str: The file content as string
        """
        # Auto-append .md extension if not present
        if not md_name.endswith(".md"):
            md_name += ".md"
        file_path = self.memory_dir / md_name
        if not file_path.exists():
            raise FileNotFoundError(f"Memory md file not found: {md_name}")

        return read_text_file_with_encoding_fallback(file_path).strip()

    def write_memory_md(self, md_name: str, content: str):
        """Write markdown content to a file in the memory directory."""
        # Auto-append .md extension if not present
        if not md_name.endswith(".md"):
            md_name += ".md"
        file_path = self.memory_dir / md_name
        file_path.write_text(content, encoding="utf-8")

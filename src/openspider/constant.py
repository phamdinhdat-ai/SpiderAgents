# -*- coding: utf-8 -*-
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

_logger = logging.getLogger(__name__)

# Load .env file from project root before reading any env vars
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


def _get_env(key: str, default: str = "") -> str:
    """Look up an env var with OPENSPIDER_ / QWENPAW_ / COPAW_ fallback.

    Lookup order:
    1. The key as-is (e.g. ``OPENSPIDER_FOO``).
    2. If the key starts with ``OPENSPIDER_``, the ``QWENPAW_`` variant
       is checked as a legacy fallback.
    3. If the key starts with ``QWENPAW_``, the ``OPENSPIDER_`` variant
       is checked first as the new canonical prefix.
    4. The corresponding ``COPAW_`` legacy variant is checked last so
       that existing deployments keep working.
    """
    if key in os.environ:
        return os.environ[key]
    if key.startswith("OPENSPIDER_"):
        suffix = key[len("OPENSPIDER_"):]
        qwenpaw_key = "OPENSPIDER_" + suffix
        if qwenpaw_key in os.environ:
            return os.environ[qwenpaw_key]
        legacy_key = "COPAW_" + suffix
        if legacy_key in os.environ:
            return os.environ[legacy_key]
    if key.startswith("OPENSPIDER_"):
        suffix = key[len("OPENSPIDER_"):]
        openspider_key = "OPENSPIDER_" + suffix
        if openspider_key in os.environ:
            return os.environ[openspider_key]
        legacy_key = "COPAW_" + suffix
        if legacy_key in os.environ:
            return os.environ[legacy_key]
    return default


class EnvVarLoader:
    """Utility to load and parse environment variables with type safety
    and defaults.  Pass OPENSPIDER_* keys; QWENPAW_* and COPAW_* legacy
    variants are checked automatically as a fallback inside _get_env.
    """

    @staticmethod
    def get_bool(env_var: str, default: bool = False) -> bool:
        """Get a boolean environment variable,
        interpreting common truthy values."""
        val = _get_env(env_var, str(default)).lower()
        return val in ("true", "1", "yes")

    @staticmethod
    def get_float(
        env_var: str,
        default: float = 0.0,
        min_value: float | None = None,
        max_value: float | None = None,
        allow_inf: bool = False,
    ) -> float:
        """Get a float environment variable with optional bounds
        and infinity handling."""
        raw = _get_env(env_var, str(default))
        try:
            value = float(raw)
            if min_value is not None and value < min_value:
                return min_value
            if max_value is not None and value > max_value:
                return max_value
            if not allow_inf and (
                value == float("inf") or value == float("-inf")
            ):
                return default
            return value
        except (TypeError, ValueError):
            if raw != str(default):
                _logger.warning(
                    "Invalid float value for env var %s=%r, "
                    "using default %s",
                    env_var,
                    raw,
                    default,
                )
            return default

    @staticmethod
    def get_int(
        env_var: str,
        default: int = 0,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        """Get an integer environment variable with optional bounds."""
        raw = _get_env(env_var, str(default))
        try:
            value = int(raw)
            if min_value is not None and value < min_value:
                return min_value
            if max_value is not None and value > max_value:
                return max_value
            return value
        except (TypeError, ValueError):
            if raw != str(default):
                _logger.warning(
                    "Invalid int value for env var %s=%r, "
                    "using default %s",
                    env_var,
                    raw,
                    default,
                )
            return default

    @staticmethod
    def get_str(env_var: str, default: str = "") -> str:
        """Get a string environment variable with a default fallback."""
        return _get_env(env_var, default)


# WORKING_DIR priority:
# 1. OPENSPIDER_WORKING_DIR / QWENPAW_WORKING_DIR / COPAW_WORKING_DIR env var → use it
# 2. Default → ~/.openspider (created if missing)
# 3. Legacy ~/.openspider / ~/.openspider are only used when explicitly set via env var
_explicit_working_dir = _get_env("OPENSPIDER_WORKING_DIR")
if _explicit_working_dir:
    WORKING_DIR = Path(_explicit_working_dir).expanduser().resolve()
else:
    WORKING_DIR = Path("~/.openspider").expanduser().resolve()
SECRET_DIR = (
    Path(
        EnvVarLoader.get_str(
            "OPENSPIDER_SECRET_DIR",
            f"{WORKING_DIR}.secret",
        ),
    )
    .expanduser()
    .resolve()
)

PROJECT_NAME = "OpenSpider"

# Default media directory for channels (cross-platform)
DEFAULT_MEDIA_DIR = WORKING_DIR / "media"

# Default local provider directory
DEFAULT_LOCAL_PROVIDER_DIR = WORKING_DIR / "local_models"

JOBS_FILE = EnvVarLoader.get_str("OPENSPIDER_JOBS_FILE", "jobs.json")

CHATS_FILE = EnvVarLoader.get_str("OPENSPIDER_CHATS_FILE", "chats.json")


# Builtin Q&A helper profile.  agent_id keeps "QwenPaw" prefix for existing
# workspaces and agent.json; do not rename.
def _discover_agent_languages() -> frozenset[str]:
    md_root = Path(__file__).resolve().parent / "agents" / "md_files"
    if md_root.is_dir():
        langs = {
            d.name
            for d in md_root.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and any(d.glob("*.md"))
        }
        if langs:
            return frozenset(langs)
    return frozenset({"en", "zh", "ru"})


SUPPORTED_AGENT_LANGUAGES: frozenset[str] = _discover_agent_languages()

BUILTIN_QA_AGENT_ID = "OPENSPIDER_QA_Agent_0.2"
BUILTIN_QA_AGENT_NAME = "QA Agent"
# Default skills when the builtin QA workspace is first created only.
BUILTIN_QA_AGENT_SKILL_NAMES: tuple[str, ...] = (
    "guidance",
    "QA_source_index",
)

# CoPaw-era builtin QA; may remain in config.json — disabled when the current
# ``BUILTIN_QA_AGENT_ID`` profile is first created (see ``migration``), not
# every startup, so users can re-enable this id if they want.
LEGACY_QA_AGENT_ID = "CoPaw_QA_Agent_0.1beta1"

TOKEN_USAGE_FILE = EnvVarLoader.get_str(
    "OPENSPIDER_TOKEN_USAGE_FILE",
    "token_usage.json",
)

CONFIG_FILE = EnvVarLoader.get_str("OPENSPIDER_CONFIG_FILE", "config.json")

HEARTBEAT_FILE = EnvVarLoader.get_str("OPENSPIDER_HEARTBEAT_FILE", "HEARTBEAT.md")
HEARTBEAT_TARGET_LAST = "last"

# Debug history file for /dump_history and /load_history commands
DEBUG_HISTORY_FILE = EnvVarLoader.get_str(
    "OPENSPIDER_DEBUG_HISTORY_FILE",
    "debug_history.jsonl",
)
# Env key for app log level (used by CLI and app load for reload child).
LOG_LEVEL_ENV = "OPENSPIDER_LOG_LEVEL"

# Env to indicate running inside a container (e.g. Docker). Set to 1/true/yes.
RUNNING_IN_CONTAINER = EnvVarLoader.get_bool(
    "OPENSPIDER_RUNNING_IN_CONTAINER",
    False,
)

# Timeout in seconds for checking if a provider is reachable.
MODEL_PROVIDER_CHECK_TIMEOUT = EnvVarLoader.get_float(
    "OPENSPIDER_MODEL_PROVIDER_CHECK_TIMEOUT",
    5.0,
    min_value=0,
    allow_inf=False,
)

# Playwright: use system Chromium when set (e.g. in Docker).
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH_ENV = "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"

# When True, expose /docs, /redoc, /openapi.json
# (dev only; keep False in prod).
DOCS_ENABLED = EnvVarLoader.get_bool("OPENSPIDER_OPENAPI_DOCS", False)

# Memory directory
MEMORY_DIR = WORKING_DIR / "memory"

# Backup directory
BACKUP_DIR = (
    Path(
        EnvVarLoader.get_str(
            "OPENSPIDER_BACKUP_DIR",
            f"{WORKING_DIR}.backups",
        ),
    )
    .expanduser()
    .resolve()
)

# Custom channel modules (installed via `openspider channels install`); manager
# loads BaseChannel subclasses from here.
CUSTOM_CHANNELS_DIR = WORKING_DIR / "custom_channels"

# Plugin directory (installed via `openspider plugin install`)
PLUGINS_DIR = WORKING_DIR / "plugins"

# Local models directory
MODELS_DIR = WORKING_DIR / "models"

MEMORY_COMPACT_KEEP_RECENT = EnvVarLoader.get_int(
    "OPENSPIDER_MEMORY_COMPACT_KEEP_RECENT",
    3,
    min_value=0,
)

# Memory compaction configuration
MEMORY_COMPACT_RATIO = EnvVarLoader.get_float(
    "OPENSPIDER_MEMORY_COMPACT_RATIO",
    0.7,
    min_value=0,
    allow_inf=False,
)

# CORS configuration — comma-separated list of allowed origins for dev mode.
# Example: OPENSPIDER_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
# When unset, CORS middleware is not applied.
CORS_ORIGINS = EnvVarLoader.get_str("OPENSPIDER_CORS_ORIGINS", "").strip()

# LLM API retry configuration
LLM_MAX_RETRIES = EnvVarLoader.get_int(
    "OPENSPIDER_LLM_MAX_RETRIES",
    3,
    min_value=0,
)

LLM_BACKOFF_BASE = EnvVarLoader.get_float(
    "OPENSPIDER_LLM_BACKOFF_BASE",
    1.0,
    min_value=0.1,
)

LLM_BACKOFF_CAP = EnvVarLoader.get_float(
    "OPENSPIDER_LLM_BACKOFF_CAP",
    10.0,
    min_value=0.5,
)

# LLM concurrency control
# Maximum number of concurrent in-flight LLM calls; excess requests wait on
# the semaphore.  Tune to your API quota: start conservatively at 3-5 and
# increase (e.g. OpenAI Tier 1 ~500 QPM allows ~25 at 3 s/call average).
LLM_MAX_CONCURRENT = EnvVarLoader.get_int(
    "OPENSPIDER_LLM_MAX_CONCURRENT",
    10,
    min_value=1,
)

# Maximum queries per minute (QPM), enforced via a 60-second sliding window.
# New requests that would exceed this limit will wait before being dispatched
# to the API — proactively preventing 429s rather than reacting to them.
# 0 = unlimited (disabled).
# Examples: Anthropic Tier-1 ≈ 50 QPM; OpenAI Tier-1 ≈ 500 QPM.
LLM_MAX_QPM = EnvVarLoader.get_int(
    "OPENSPIDER_LLM_MAX_QPM",
    600,
    min_value=0,
)

# Default global pause duration (seconds) applied to all waiters when a 429
# is received.  Overridden by the API's Retry-After header when present.
LLM_RATE_LIMIT_PAUSE = EnvVarLoader.get_float(
    "OPENSPIDER_LLM_RATE_LIMIT_PAUSE",
    5.0,
    min_value=1.0,
)

# Random jitter range (seconds) added on top of the pause remaining time so
# concurrent waiters stagger their wake-up and avoid a new burst.
LLM_RATE_LIMIT_JITTER = EnvVarLoader.get_float(
    "OPENSPIDER_LLM_RATE_LIMIT_JITTER",
    1.0,
    min_value=0.0,
)

# Maximum time (seconds) a caller will wait for a semaphore slot before
# giving up with a RuntimeError rather than blocking indefinitely.
LLM_ACQUIRE_TIMEOUT = EnvVarLoader.get_float(
    "OPENSPIDER_LLM_ACQUIRE_TIMEOUT",
    300.0,
    min_value=10.0,
)

# Tool guard approval timeout (seconds).
TOOL_GUARD_APPROVAL_TIMEOUT_SECONDS = EnvVarLoader.get_float(
    "OPENSPIDER_TOOL_GUARD_APPROVAL_TIMEOUT_SECONDS",
    300.0,
    min_value=1.0,
)

# Tool guard approval heartbeat interval (seconds).
# Sends periodic heartbeat messages during approval wait to keep SSE
# connection alive. Should be less than browser/proxy timeout (30-60s).
TOOL_GUARD_APPROVAL_HEARTBEAT_INTERVAL = EnvVarLoader.get_float(
    "OPENSPIDER_TOOL_GUARD_APPROVAL_HEARTBEAT_INTERVAL",
    15.0,
    min_value=5.0,
)

# Marker prepended to every truncation notice.
# Format:
#   <<<TRUNCATED>>>
#   The output above was truncated.
#   The full content is saved to the file and contains Z lines in total.
#   This excerpt starts at line X and covers the next N bytes.
#   If the current content is not enough, call `read_file` with
#   file_path=<path> start_line=Y to read more.
#
# Split output on this marker to recover the original (untruncated) portion:
#   original = output.split(TRUNCATION_NOTICE_MARKER)[0]
TRUNCATION_NOTICE_MARKER = "<<<TRUNCATED>>>"

# Placeholder text used when media blocks are stripped from messages
# because the model does not support multimodal content.
MEDIA_UNSUPPORTED_PLACEHOLDER = (
    "[Media content removed - model does not support this media type]"
)

# Maximum number of events that can queue in the token-usage buffer
# before new events are dropped with a warning.  Prevents unbounded
# memory growth when the disk-flush consumer falls behind producers.
TOKEN_USAGE_QUEUE_MAX = EnvVarLoader.get_int(
    "OPENSPIDER_TOKEN_USAGE_QUEUE_MAX",
    10_000,
    min_value=100,
)

# Signing secret for approval resolution tokens.
# HMAC-SHA256 tokens are generated for each pending approval and must
# be verified when resolving via the HTTP API.
# Override with a strong random value via OPENSPIDER_APPROVAL_SIGNING_SECRET.
# The default value is insecure and
# only suitable for local development / single-node deployments where the
# secret is kept in memory only.
import os as _os  # noqa: E402 — local import to avoid polluting module namespace
import secrets as _secrets  # noqa: E402

APPROVAL_SIGNING_SECRET: str = (
    _get_env("APPROVAL_SIGNING_SECRET")
    or _secrets.token_hex(32)  # fallback: per-process ephemeral secret
)

# ------------------------------------------------------------------
# Harness Engineering — Loop & Feedback Configuration
# ------------------------------------------------------------------

# Self-verification: agent checks its own tool results before committing.
# When enabled, after each tool call the agent verifies the result
# (e.g., read-back file content, check exit codes) and feeds failures
# back to the LLM as additional observations.
SELF_VERIFY_ENABLED = EnvVarLoader.get_bool(
    "OPENSPIDER_SELF_VERIFY_ENABLED",
    False,
)

SELF_VERIFY_MAX_RETRIES = EnvVarLoader.get_int(
    "OPENSPIDER_SELF_VERIFY_MAX_RETRIES",
    3,
    min_value=0,
    max_value=10,
)

# Loop detection: detect when the agent is stuck repeating the same
# tool call with identical arguments, and inject a corrective observation.
LOOP_DETECTION_ENABLED = EnvVarLoader.get_bool(
    "OPENSPIDER_LOOP_DETECTION_ENABLED",
    True,
)

LOOP_DETECTION_WINDOW = EnvVarLoader.get_int(
    "OPENSPIDER_LOOP_DETECTION_WINDOW",
    5,
    min_value=2,
    max_value=50,
)

LOOP_DETECTION_THRESHOLD = EnvVarLoader.get_int(
    "OPENSPIDER_LOOP_DETECTION_THRESHOLD",
    3,
    min_value=2,
    max_value=20,
)

# Tool-level retry: automatically retry failed tool executions with
# exponential backoff for transient errors (timeout, connection).
TOOL_RETRY_ENABLED = EnvVarLoader.get_bool(
    "OPENSPIDER_TOOL_RETRY_ENABLED",
    False,
)

TOOL_MAX_RETRIES = EnvVarLoader.get_int(
    "OPENSPIDER_TOOL_MAX_RETRIES",
    2,
    min_value=0,
    max_value=10,
)

TOOL_RETRY_BACKOFF_BASE = EnvVarLoader.get_float(
    "OPENSPIDER_TOOL_RETRY_BACKOFF_BASE",
    0.5,
    min_value=0.1,
)

# Lightweight snapshots: hash-based pre-state recording before
# destructive tool calls, enabling rollback on detected regression.
SNAPSHOT_ENABLED = EnvVarLoader.get_bool(
    "OPENSPIDER_SNAPSHOT_ENABLED",
    False,
)

SNAPSHOT_MAX_BACKUP_SIZE_MB = EnvVarLoader.get_int(
    "OPENSPIDER_SNAPSHOT_MAX_BACKUP_SIZE_MB",
    50,
    min_value=1,
    max_value=500,
)

# ------------------------------------------------------------------
# Auto-continue: when the model returns text-only (no tool calls),
# inject a hint and allow extra reasoning passes.
# ------------------------------------------------------------------

AUTO_CONTINUE_MAX_EXTRA = EnvVarLoader.get_int(
    "OPENSPIDER_AUTO_CONTINUE_MAX_EXTRA",
    1,
    min_value=0,
    max_value=10,
)

AUTO_CONTINUE_TAIL_CHARS = EnvVarLoader.get_int(
    "OPENSPIDER_AUTO_CONTINUE_TAIL_CHARS",
    600,
    min_value=50,
    max_value=10000,
)

AUTO_CONTINUE_HINT_EN = EnvVarLoader.get_str(
    "OPENSPIDER_AUTO_CONTINUE_HINT_EN",
    (
        "<system-hint>"
        "Your previous assistant turn had text only (no tool calls). "
        "Use the trailing excerpt in <previous-assistant-tail> (if present) "
        "plus the conversation to decide in this **reasoning** step: if the "
        "user's task still needs tools, emit tool_use now; if it is fully "
        "done, reply with a short text only (no tools). "
        "Do not stop with plans or code fences alone when tools are still "
        "needed."
        "</system-hint>"
    ),
)

AUTO_CONTINUE_HINT_VI = EnvVarLoader.get_str(
    "OPENSPIDER_AUTO_CONTINUE_HINT_VI",
    (
        "<system-hint>"
        "Lần trước trợ lý chỉ có văn bản, không gọi công cụ. "
        "Hãy sử dụng ngữ cảnh và <previous-assistant-tail> (nếu có) "
        "để quyết định trong bước **reasoning** này: nếu nhiệm vụ của "
        "người dùng vẫn cần công cụ, hãy phát hành tool_use ngay; nếu "
        "nó đã hoàn tất, hãy trả lời bằng văn bản ngắn gọn (không có "
        "công cụ)."
        "</system-hint>"
    ),
)

ROUND_END_NOTICE = EnvVarLoader.get_str(
    "OPENSPIDER_ROUND_END_NOTICE",
    (
        "\n\n---\n"
        "Maximum iterations reached for this round. "
        "Please send a new message to continue."
    ),
)

# ------------------------------------------------------------------
# Heartbeat defaults
# ------------------------------------------------------------------

HEARTBEAT_DEFAULT_EVERY = EnvVarLoader.get_str(
    "OPENSPIDER_HEARTBEAT_DEFAULT_EVERY",
    "6h",
)

HEARTBEAT_DEFAULT_TARGET = EnvVarLoader.get_str(
    "OPENSPIDER_HEARTBEAT_DEFAULT_TARGET",
    "main",
)

# ------------------------------------------------------------------
# History / debug
# ------------------------------------------------------------------

MAX_LOAD_HISTORY_COUNT = EnvVarLoader.get_int(
    "OPENSPIDER_MAX_LOAD_HISTORY_COUNT",
    10000,
    min_value=1,
)

# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------

LOG_MAX_BYTES = EnvVarLoader.get_int(
    "OPENSPIDER_LOG_MAX_BYTES",
    5 * 1024 * 1024,  # 5 MiB
    min_value=1024,
)

AUDIT_LOG_MAX_BYTES = EnvVarLoader.get_int(
    "OPENSPIDER_AUDIT_LOG_MAX_BYTES",
    10 * 1024 * 1024,  # 10 MiB
    min_value=1024,
)

AUDIT_LOG_BACKUP_COUNT = EnvVarLoader.get_int(
    "OPENSPIDER_AUDIT_LOG_BACKUP_COUNT",
    5,
    min_value=0,
    max_value=100,
)

# ------------------------------------------------------------------
# Tool output display
# ------------------------------------------------------------------

TOOL_OUTPUT_MAX_BYTES = EnvVarLoader.get_int(
    "OPENSPIDER_TOOL_OUTPUT_MAX_BYTES",
    50 * 1024,  # 50 KB
    min_value=1024,
)

# Maximum file size to read into memory (1 GB) — used by read_file tool.
# Files larger than this are rejected outright to avoid OOM.
FILE_READ_MAX_BYTES = EnvVarLoader.get_int(
    "OPENSPIDER_FILE_READ_MAX_BYTES",
    1024 * 1024 * 1024,  # 1 GB
    min_value=1024,
)

# ------------------------------------------------------------------
# File search tools
# ------------------------------------------------------------------

FILE_SEARCH_MAX_MATCHES = EnvVarLoader.get_int(
    "OPENSPIDER_FILE_SEARCH_MAX_MATCHES",
    200,
    min_value=1,
)

FILE_SEARCH_MAX_FILE_SIZE = EnvVarLoader.get_int(
    "OPENSPIDER_FILE_SEARCH_MAX_FILE_SIZE",
    2 * 1024 * 1024,  # 2 MB
    min_value=1024,
)

FILE_SEARCH_MAX_CONTEXT_LINES = EnvVarLoader.get_int(
    "OPENSPIDER_FILE_SEARCH_MAX_CONTEXT_LINES",
    5,
    min_value=0,
    max_value=100,
)

FILE_SEARCH_MAX_OUTPUT_CHARS = EnvVarLoader.get_int(
    "OPENSPIDER_FILE_SEARCH_MAX_OUTPUT_CHARS",
    50_000,
    min_value=100,
)

FILE_SEARCH_MAX_FILES_SCANNED = EnvVarLoader.get_int(
    "OPENSPIDER_FILE_SEARCH_MAX_FILES_SCANNED",
    10_000,
    min_value=1,
)

FILE_SEARCH_GREP_TIMEOUT = EnvVarLoader.get_int(
    "OPENSPIDER_FILE_SEARCH_GREP_TIMEOUT",
    30,
    min_value=1,
)

FILE_SEARCH_GLOB_TIMEOUT = EnvVarLoader.get_int(
    "OPENSPIDER_FILE_SEARCH_GLOB_TIMEOUT",
    15,
    min_value=1,
)

# ------------------------------------------------------------------
# Browser control
# ------------------------------------------------------------------

BROWSER_IDLE_TIMEOUT = EnvVarLoader.get_float(
    "OPENSPIDER_BROWSER_IDLE_TIMEOUT",
    600.0,
    min_value=1.0,
)

# ------------------------------------------------------------------
# Agent management API
# ------------------------------------------------------------------

AGENT_API_TIMEOUT = EnvVarLoader.get_float(
    "OPENSPIDER_AGENT_API_TIMEOUT",
    30.0,
    min_value=1.0,
)

# ------------------------------------------------------------------
# Mission runner
# ------------------------------------------------------------------

MISSION_DEFAULT_MAX_ITERATIONS = EnvVarLoader.get_int(
    "OPENSPIDER_MISSION_DEFAULT_MAX_ITERATIONS",
    20,
    min_value=1,
)

MISSION_MIN_MAX_ITERATIONS = EnvVarLoader.get_int(
    "OPENSPIDER_MISSION_MIN_MAX_ITERATIONS",
    1,
    min_value=1,
)

MISSION_MAX_MAX_ITERATIONS = EnvVarLoader.get_int(
    "OPENSPIDER_MISSION_MAX_MAX_ITERATIONS",
    100,
    min_value=1,
)

MISSION_MAX_PRD_FIX_ATTEMPTS = EnvVarLoader.get_int(
    "OPENSPIDER_MISSION_MAX_PRD_FIX_ATTEMPTS",
    2,
    min_value=0,
    max_value=10,
)

# ------------------------------------------------------------------
# Message statistics display
# ------------------------------------------------------------------

MSG_STAT_BLOCK_PREVIEW_LENGTH = EnvVarLoader.get_int(
    "OPENSPIDER_MSG_STAT_BLOCK_PREVIEW_LENGTH",
    100,
    min_value=10,
)

MSG_STAT_FORMATTER_TEXT_LENGTH = EnvVarLoader.get_int(
    "OPENSPIDER_MSG_STAT_FORMATTER_TEXT_LENGTH",
    1000,
    min_value=10,
)

# ------------------------------------------------------------------
# Skill system hub
# ------------------------------------------------------------------

SKILLS_HUB_MAX_ZIP_ENTRIES = EnvVarLoader.get_int(
    "OPENSPIDER_SKILLS_HUB_MAX_ZIP_ENTRIES",
    256,
    min_value=1,
)

SKILLS_HUB_MAX_ZIP_BYTES = EnvVarLoader.get_int(
    "OPENSPIDER_SKILLS_HUB_MAX_ZIP_BYTES",
    5 * 1024 * 1024,  # 5 MB
    min_value=1024,
)

SKILLS_HUB_CACHE_TTL = EnvVarLoader.get_int(
    "OPENSPIDER_SKILLS_HUB_CACHE_TTL",
    300,
    min_value=0,
)

# ------------------------------------------------------------------
# Skill store
# ------------------------------------------------------------------

SKILL_STORE_MAX_ZIP_BYTES = EnvVarLoader.get_int(
    "OPENSPIDER_SKILL_STORE_MAX_ZIP_BYTES",
    200 * 1024 * 1024,  # 200 MB
    min_value=1024,
)

# ------------------------------------------------------------------
# Memory
# ------------------------------------------------------------------

MEMORY_MAX_QUERY_TOKENS = EnvVarLoader.get_int(
    "OPENSPIDER_MEMORY_MAX_QUERY_TOKENS",
    50,
    min_value=1,
)

# ------------------------------------------------------------------
# Skill scanner
# ------------------------------------------------------------------

SKILL_SCAN_MAX_CACHE_ENTRIES = EnvVarLoader.get_int(
    "OPENSPIDER_SKILL_SCAN_MAX_CACHE_ENTRIES",
    64,
    min_value=1,
)

SKILL_SCAN_MAX_PATTERN_LENGTH = EnvVarLoader.get_int(
    "OPENSPIDER_SKILL_SCAN_MAX_PATTERN_LENGTH",
    1000,
    min_value=10,
)

SKILL_SCAN_MAX_FILES = EnvVarLoader.get_int(
    "OPENSPIDER_SKILL_SCAN_MAX_FILES",
    500,
    min_value=1,
)

SKILL_SCAN_MAX_FILE_SIZE = EnvVarLoader.get_int(
    "OPENSPIDER_SKILL_SCAN_MAX_FILE_SIZE",
    10 * 1024 * 1024,  # 10 MB
    min_value=1024,
)

# ------------------------------------------------------------------
# Knowledge base
# ------------------------------------------------------------------

KNOWLEDGE_MAX_FILE_SIZE_BYTES = EnvVarLoader.get_int(
    "OPENSPIDER_KNOWLEDGE_MAX_FILE_SIZE_BYTES",
    50 * 1024 * 1024,  # 50 MB
    min_value=1024,
)

# ------------------------------------------------------------------
# Tunnel binary download
# ------------------------------------------------------------------

TUNNEL_DOWNLOAD_TIMEOUT = EnvVarLoader.get_int(
    "OPENSPIDER_TUNNEL_DOWNLOAD_TIMEOUT",
    90,
    min_value=5,
)

# ------------------------------------------------------------------
# Agent ID validation
# ------------------------------------------------------------------

AGENT_ID_MIN_LENGTH = EnvVarLoader.get_int(
    "OPENSPIDER_AGENT_ID_MIN_LENGTH",
    2,
    min_value=1,
)

AGENT_ID_MAX_LENGTH = EnvVarLoader.get_int(
    "OPENSPIDER_AGENT_ID_MAX_LENGTH",
    64,
    min_value=1,
)

# ------------------------------------------------------------------
# Token usage buffer
# ------------------------------------------------------------------

TOKEN_USAGE_FLUSH_INTERVAL = EnvVarLoader.get_int(
    "OPENSPIDER_TOKEN_USAGE_FLUSH_INTERVAL",
    10,
    min_value=1,
)

# ------------------------------------------------------------------
# File lock / safe swap
# ------------------------------------------------------------------

LOCK_RETRY_INTERVAL = EnvVarLoader.get_float(
    "OPENSPIDER_LOCK_RETRY_INTERVAL",
    0.1,
    min_value=0.01,
)

LOCK_TIMEOUT = EnvVarLoader.get_float(
    "OPENSPIDER_LOCK_TIMEOUT",
    300.0,
    min_value=1.0,
)

# ------------------------------------------------------------------
# Plan hints
# ------------------------------------------------------------------

PLAN_DESC_LIMIT = EnvVarLoader.get_int(
    "OPENSPIDER_PLAN_DESC_LIMIT",
    80,
    min_value=10,
)

PLAN_PLAN_DESC_LIMIT = EnvVarLoader.get_int(
    "OPENSPIDER_PLAN_PLAN_DESC_LIMIT",
    200,
    min_value=10,
)

# ------------------------------------------------------------------
# PostgreSQL database
# ------------------------------------------------------------------

DATABASE_URL: str = EnvVarLoader.get_str(
    "OPENSPIDER_DATABASE_URL",
    "postgresql+asyncpg://5gai:Vht%402025@localhost:5433/5gai",
)
"""PostgreSQL connection URL (asyncpg driver).

Set ``OPENSPIDER_DATABASE_URL`` to override.  The default matches the
standalone ``docker-compose.postgres.yaml`` shipped in the repo root.
"""

DATABASE_ENABLED: bool = EnvVarLoader.get_bool(
    "OPENSPIDER_DATABASE_ENABLED",
    False,
)
"""Feature flag: when ``True``, PostgreSQL is used instead of SQLite + JSON.

Set ``OPENSPIDER_DATABASE_ENABLED=true`` to enable.  Existing data should
be migrated before enabling (see ``scripts/migrate_to_postgres.py``).
"""

# ------------------------------------------------------------------
# Multi-user data directories
# ------------------------------------------------------------------

USERS_DIR = (
    Path(
        EnvVarLoader.get_str(
            "OPENSPIDER_USERS_DIR",
            f"{WORKING_DIR}/users",
        ),
    )
    .expanduser()
    .resolve()
)
"""Root directory for per-user data isolation.

When authentication is enabled, each user's sessions, memory, files,
and config overrides are stored under ``USERS_DIR/<sha256(username)>/``.
When auth is disabled, the legacy ``workspace/<agent_id>/sessions/`` path
is used instead.
"""


def get_user_storage_dir(username: str) -> Path:
    """Return the per-user storage directory (hashed for privacy).

    Uses SHA-256 of the *username* so the directory name is deterministic,
    URL-safe, and does not leak the raw username in filesystem listings.

    Args:
        username: The authenticated username.

    Returns:
        Absolute path to ``USERS_DIR / sha256(username)``.
    """
    import hashlib

    user_hash = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return USERS_DIR / user_hash


def get_user_sessions_dir(username: str, agent_id: str) -> Path:
    """Return the per-user, per-agent session storage directory.

    Args:
        username: The authenticated username.
        agent_id: The agent/workspace identifier.

    Returns:
        Path like ``USERS_DIR/<hash>/workspaces/<agent_id>/sessions/``.
    """
    return get_user_storage_dir(username) / "workspaces" / agent_id / "sessions"


def get_user_memory_dir(username: str, agent_id: str) -> Path:
    """Return the per-user, per-agent daily-memory directory.

    Args:
        username: The authenticated username.
        agent_id: The agent/workspace identifier.

    Returns:
        Path like ``USERS_DIR/<hash>/workspaces/<agent_id>/memory/``.
    """
    return get_user_storage_dir(username) / "workspaces" / agent_id / "memory"


def get_user_files_dir(username: str) -> Path:
    """Return the per-user file uploads directory.

    Args:
        username: The authenticated username.

    Returns:
        Path like ``USERS_DIR/<hash>/files/``.
    """
    return get_user_storage_dir(username) / "files"


def get_user_config_path(username: str) -> Path:
    """Return the per-user config override file path.

    Args:
        username: The authenticated username.

    Returns:
        Path like ``USERS_DIR/<hash>/config.json``.
    """
    return get_user_storage_dir(username) / "config.json"

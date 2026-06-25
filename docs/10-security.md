# 10 — Security

> Tool guard engine, execution levels, YAML rules, secret store, skill scanner.

---

## Tool Guard Engine

```
ToolGuardEngine (lazy singleton: get_guard_engine())
    │
    ├── FilePathToolGuardian
    │   └── Detects access to sensitive paths
    │
    ├── RuleBasedToolGuardian
    │   └── YAML rules in security/tool_guard/rules/
    │       └── dangerous_shell_commands.yaml
    │
    └── ShellEvasionGuardian
        └── Detects obfuscation, encoding tricks
```

### Guard Flow

```python
# Engine orchestration
def guard(tool_name: str, tool_input: dict) -> ToolGuardResult:
    findings = []
    for guardian in [file_path, rule_based, shell_evasion]:
        findings.extend(guardian.guard(tool_name, tool_input))
    return ToolGuardResult(findings)
```

### `always_run` Flag

Guardians with `always_run=True` (like `FilePathToolGuardian`) run for ALL tools, not just explicitly guarded ones.

---

## Severity Levels

| Level | Auto-Deny? | Description |
|-------|-----------|-------------|
| `CRITICAL` | ✅ Yes | Immediate block |
| `HIGH` | — | Needs approval |
| `MEDIUM` | — | Needs approval (SMART mode) |
| `LOW` | — | Auto-allowed (SMART mode) |
| `INFO` | — | Auto-allowed (SMART mode) |
| `SAFE` | — | No action |

---

## Threat Categories

`command_injection`, `data_exfiltration`, `path_traversal`, `sensitive_file_access`, `network_abuse`, `credential_exposure`, `resource_abuse`, `prompt_injection`, `code_execution`, `privilege_escalation`

---

## Execution Levels

| Level | Behavior |
|-------|----------|
| `OFF` | No guard checks — bypass entirely |
| `AUTO` | Only guarded tools checked (backward compatible) |
| `SMART` | INFO/LOW auto-allowed, MEDIUM+ needs approval |
| `STRICT` | ALL tools require approval |

```python
class ToolExecutionLevel(Enum):
    STRICT = "strict"
    SMART = "smart"
    AUTO = "auto"
    OFF = "off"
    
    @classmethod
    def from_config(cls, value: str) -> "ToolExecutionLevel":
        # Case-insensitive, defaults to AUTO
```

---

## GuardFinding Model

```python
class GuardFinding(BaseModel):
    id: str
    rule_id: str
    category: GuardThreatCategory
    severity: GuardSeverity
    title: str
    description: str
    tool_name: str
    matched_pattern: str | None
    matched_value: str | None
    remediation: str | None
```

---

## Approval Flow (End-to-End)

```
Tool call → Guard check → "needs_approval"
    │
    ▼
ApprovalService.create_pending(session_id, tool_name, guard_result)
    │  Creates asyncio.Future + HMAC token
    ▼
Runner SUSPENDED (await future)
    │
    │  Frontend polls GET /api/console/push-messages
    │  → ApprovalCard rendered with severity, findings, timeout
    │
    │  User clicks Approve/Deny
    ▼
POST /api/approval/approve | /deny
    │  { request_id, session_id, reason }
    ▼
ApprovalService.resolve_request(request_id, decision)
    │  Verifies HMAC token
    ▼
Future.set_result(APPROVED/DENIED)
    │
    ▼
Runner RESUMES → tool executes or error returned
```

---

## Secret Store

### Encryption

Fernet (AES-128-CBC + HMAC-SHA256):
- Master key from OS keychain (`keyring` library) or fallback file
- Encrypted values prefixed with `ENC:` for transparent migration

```python
# Field-level encryption for Pydantic models
encrypt_dict_fields(config_dict, fields=["api_key", "token", ...])
decrypt_dict_fields(config_dict, fields=["api_key", "token", ...])

# Provider secret fields
PROVIDER_SECRET_FIELDS = ["api_key", "api_key_prefix", "token"]
```

---

## Skill Scanner

Static analysis of skill directories before install/activation:

```
security/skill_scanner/
├── scanner.py          # Entry point
├── analyzers/          # Analysis modules
├── rules/              # Detection rules
├── models.py           # SkillScanResult, SkillScanFinding
└── scan_policy.py      # Policy configuration
```

**Purpose**: Detect malicious or risky code in skill directories before they're activated. Runs on install and on startup for existing skills.

---

## YAML Rule Files

Located at `security/tool_guard/rules/signatures/`:

| Rule File | Detects |
|-----------|---------|
| `command_injection` | Shell command injection patterns |
| `data_exfiltration` | Data exfiltration attempts |
| `hardcoded_secrets` | Hardcoded credentials |
| `obfuscation` | Code obfuscation |
| `prompt_injection` | Prompt injection attacks |
| `social_engineering` | Social engineering patterns |
| `supply_chain` | Supply chain attacks |
| `unauthorized_tool_use` | Unauthorized tool usage |

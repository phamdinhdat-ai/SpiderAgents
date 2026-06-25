# 06 — Skill System

> Two-tier skill architecture, resolution, registration, 18 built-in skills.

---

## Architecture

```
┌─────────────────────────────────────┐
│          SKILL RESOLUTION           │
│                                     │
│  resolve_effective_skills(          │
│      agent_id, channel)             │
│         │                           │
│         ├──► Workspace skills       │
│         │    (<workspace>/skills/)  │
│         │                           │
│         ├──► Skill pool             │
│         │    (~/.openspider/        │
│         │     skill_pool/)          │
│         │                           │
│         └──► Env var overrides      │
│              OPENSPIDER_SKILL_      │
│              <NAME>_ENABLED=1       │
└─────────────────────────────────────┘
```

---

## Skill Structure

```
skills/<skill_name>-en/
├── SKILL.md          # Skill instructions (Markdown)
├── references/       # Reference documents
└── scripts/          # Python scripts (optional)
```

Each skill is bilingual (`-en/` and `-zh/` variants).

---

## Registration

```python
# Each skill directory is registered as an AgentScope "agent skill"
toolkit.register_agent_skill(str(skill_dir))
```

Skills are loaded during `QwenPawAgent.__init__()` via `_register_skills()`.

---

## Resolution (`resolve_effective_skills()`)

1. **Read workspace manifest** — `<workspace>/skills/manifest.json`
2. **Read pool manifest** — `~/.openspider/skill_pool/manifest.json`
3. **Apply env var overrides** — `OPENSPIDER_SKILL_<NAME>_ENABLED=1`
4. **Channel-aware filtering** — skills can be channel-specific
5. **Return** active skill names for the channel

---

## Two-Tier Architecture

| Tier | Location | Scope |
|------|----------|-------|
| **Workspace skills** | `<workspace>/skills/` | Per-agent |
| **Skill pool** | `~/.openspider/skill_pool/` | Shared across all agents |

### Services

| Service | Manages |
|---------|---------|
| `SkillService` | Workspace skills (per-agent) |
| `SkillPoolService` | Pool skills (shared) |

---

## 18 Built-in Skills (Bilingual en/zh)

| Skill | Purpose |
|-------|---------|
| `browser_cdp` | Browser automation via CDP |
| `browser_visible` | Visible browser automation |
| `chat_with_agent` | Inter-agent communication |
| `cron` | Scheduled task management |
| `docx` | Word document handling |
| `file_reader` | File reading with format support |
| `make_plan` | Task planning and decomposition |
| `multi_agent_collaboration` | Multi-agent coordination |
| `pdf` | PDF document handling |
| `pptx` | PowerPoint handling |
| `xlsx` | Excel spreadsheet handling |
| `news` | News digest generation |
| `QA_source_index` | Documentation indexing for QA |
| `dingtalk_channel` | DingTalk channel configuration |
| `guidance` | Agent guidance and onboarding |
| `mu-plugins` | Plugin management |
| `channels` | Channel configuration |
| `heartbeat` | Heartbeat/monitoring |

---

## Namesake Conflict Resolution

When a skill tool name conflicts with a built-in tool:

| Strategy | Behavior |
|----------|----------|
| `"skip"` | Don't register (default) |
| `"override"` | Replace built-in |
| `"raise"` | Throw error |
| `"rename"` | Auto-rename with prefix |

---

## CLI Management

```bash
# List skills
openspider skills list

# Enable/disable
openspider skills enable <name>
openspider skills disable <name>

# Install from hub
openspider skills install <url>
```

# OpenSpider — Documentation

> Comprehensive architecture and design documentation for the OpenSpider codebase.  
> **Active source**: `src/openspider/` | **Package**: `openspider`

## Bắt đầu sử dụng — tiếng Việt

- [Hướng dẫn sử dụng và chạy project trên Windows](19-huong-dan-su-dung.md):
  cài đặt, chạy dev/bundle, giữ dữ liệu preview, cấu hình LLM, Projects, KB,
  MCP, jobs, theme và xử lý lỗi.
- [Kiến trúc hệ thống hiện tại](20-kien-truc-he-thong.md): sơ đồ thành phần,
  luồng chat/approval, phân quyền, persistence thực tế và giới hạn triển khai.

Hai tài liệu trên được cập nhật ngày **16/10/2026** theo working tree hiện tại.
Các chương phân tích bên dưới cung cấp chi tiết từng module; khi có khác biệt
về tính năng mới, xem bản tổng quan hiện tại và source được dẫn liên kết.

---

## Reading Guide

| # | Document | What It Covers |
|---|----------|---------------|
| 01 | [Architecture Overview](01-overview.md) | High-level architecture diagram, package map, entry points |
| 02 | [Agent System](02-agent-system.md) | SpiderAgent class, ReAct loop, tool system, security guard, model factory |
| 03 | [Provider Pattern](03-providers.md) | LLM provider abstraction, rate limiting, retry, model capability cache |
| 04 | [Channel System](04-channels.md) | BaseChannel ABC, 17 channels, ChannelManager, registry |
| 05 | [Workspace & Runner](05-workspace-runner.md) | Workspace lifecycle, ServiceManager, MultiAgentManager, AgentRunner |
| 06 | [Skill System](06-skill-system.md) | Two-tier skill architecture, resolution, built-in skills |
| 07 | [Context & Memory](07-context-memory.md) | Memory stack, context compaction, ReMe integration |
| 08 | [Configuration](08-config-system.md) | Pydantic model hierarchy, env var system, config loading |
| 09 | [Plan & Mission Modes](09-plan-mission.md) | Plan state machine, tool gating, two-phase mission execution |
| 10 | [Security](10-security.md) | Tool guard engine, execution levels, secret store, skill scanner |
| 11 | [Frontend-Backend](11-frontend-backend.md) | API connection, SSE streaming, agent switching, approval UI |
| 12 | [CLI Architecture](12-cli.md) | LazyGroup pattern, command list, entry points |
| 13 | [ACP Protocol](13-acp-protocol.md) | Agent Communication Protocol server + hosted clients |
| 14 | [Design Patterns](14-design-patterns.md) | All design patterns + async patterns reference |
| 15 | [Agent Flows & Diagrams](15-agent-flows.md) | **Mermaid diagrams**: multi-agent, ReAct loop, tool registration, routing, mission, plan, channels |
| 16 | [Harness Engineering](16-harness-engineering.md) | **NEW** — Loop detection, self-verification, tool retry, snapshots, approval flow fix, pipeline architecture |
| 17 | [Projects / SpiderAgents Studio](17-projects.md) | Project briefs, user ownership, chat sessions, API and implementation limits |
| 18 | [Spider appearance and navigation](18-spider-appearance-and-navigation.md) | Theme palettes, custom colors, animations and Project → Chat fixes |
| 19 | [Hướng dẫn sử dụng](19-huong-dan-su-dung.md) | Windows startup, LLM config, Projects, KB, MCP, jobs and troubleshooting |
| 20 | [Kiến trúc hệ thống hiện tại](20-kien-truc-he-thong.md) | Current architecture, execution flows, persistence and verified limitations |
| 21 | [Release checkpoint 17/10/2026](21-release-checkpoint.md) | Scope, credential cleanup, verification and remaining limitations before the next version |

---

## Quick Navigation

### For New Developers
1. Start with [01-overview.md](01-overview.md) for the big picture
2. Then [02-agent-system.md](02-agent-system.md) to understand the core agent
3. Then [05-workspace-runner.md](05-workspace-runner.md) for the request lifecycle

### For Feature Development
- Adding a tool → [02-agent-system.md](02-agent-system.md#tool-system)
- Adding a provider → [03-providers.md](03-providers.md)
- Adding a channel → [04-channels.md](04-channels.md)
- Adding a skill → [06-skill-system.md](06-skill-system.md)

### For Backend Developers
- Request flow → [01-overview.md](01-overview.md#request-flow)
- Config → [08-config-system.md](08-config-system.md)
- Security → [10-security.md](10-security.md)

### For Frontend Developers
- API connection → [11-frontend-backend.md](11-frontend-backend.md)

---

## Key Design Principles

1. **Async-first**: All I/O is `async def`; never block the event loop
2. **Pydantic everywhere**: Config, provider info, plan schemas — all `BaseModel`
3. **Mixin-based extensions**: Security via `ToolGuardMixin` in MRO chain
4. **Lazy initialization**: Modules, CLI commands, workspaces — loaded on demand
5. **Singleton services**: Approval, rate limiting, provider management — global singletons
6. **Future-based suspension**: Approval flow suspends runner via `asyncio.Future`

# Projects / SpiderAgents Studio

Projects provide a personal, persistent space for data-science work without
replacing OpenSpider's existing agents, chat runner, or tool approval gate.

## User flow

1. Open `/projects` (also the console's default landing page).
2. Create a blank project or start from Data exploration, Machine learning,
   Data pipeline, or Research. Templates supply editable working instructions.
3. Set a name, description, objective, and agent instructions. Optionally select
   references to MCP connections owned by the current user.
4. Start a conversation using the agent selected in the sidebar. The conversation
   is recorded with project metadata and a dedicated project session ID.
5. On every console request, the server resolves the project and checks ownership
   before adding its current brief to the runner's environment context.
6. Return through the project banner above the conversation. Project details list
   conversations for the currently selected agent.
7. Archive a finished project, or restore it later. Archiving preserves chats and
   prevents starting or continuing project conversations until restored.

The refreshed shell uses SpiderAgents branding and Projects / Chat / Jobs /
Connections navigation. Projects includes search, status filters, template cards,
editable briefs, conversation lists, and connection reference details. It supports
light/dark appearance, keyboard focus, reduced motion, and mobile layouts.

## Data and authorization

- Implementation: `src/openspider/app/projects.py` and
  `src/openspider/app/routers/projects.py`.
- Storage uses `app.state.user_data_store` through its existing
  `get_setting` / `set_setting` contract. A validated JSON collection is stored
  at the reserved key `spideragents.projects.v1`, separately for every user.
- Both SQLite and PostgreSQL implement this contract. No new table or migration
  is needed for this initial implementation. Live PostgreSQL has not been tested
  in this delivery.
- A shared application lock protects read/modify/write operations in the existing
  single-worker application. Updates require the current `version`; stale writes
  return HTTP 409. A multi-process deployment would require database-level
  compare-and-swap or a dedicated projects repository.
- Maximum 500 projects per user, 50 connection references per project, and bounded
  brief/instruction lengths. Large-scale pagination and relational queries are
  outside this initial implementation.
- Owner identity comes from authenticated request context. It cannot be supplied
  in a project body. Another user's project returns 404, including for personal
  project endpoints called by an admin. Auth-disabled local mode uses `default`.
- Connection responses contain only ID, display name, transport, and enabled
  status. They do not return credentials, headers, or environment values.
- Connection references organize context; they do not grant or restrict agent
  tool access. Existing agent MCP configuration and ToolGuardMixin still apply.
- Project sessions use `project:<project UUID>:<session UUID>`. Client-supplied
  project instructions are not trusted; the console endpoint loads the brief
  from the caller's persisted project. Original user messages are not rewritten.

## API

All routes are under `/api/projects`:

| Method / route | Behavior |
|---|---|
| `GET /` | List the current user's projects |
| `POST /` | Create a project |
| `GET /connections` | List safe metadata for the user's MCP references |
| `GET /{project_id}` | Read an owned project |
| `PUT /{project_id}` | Replace editable fields with optimistic `version` checking |
| `GET /{project_id}/chats` | List owned project chats for the selected agent |
| `POST /{project_id}/chats` | Create an owned project conversation |
| `GET /chat-context/{chat_id}` | Resolve an owned chat's project for its UI banner |

The current agent is resolved using the existing `X-Agent-Id` mechanism.

## Validation performed

- 52 backend tests passed: new Projects tests plus chat update, console
  placeholder, and console channel regressions.
- 29 frontend tests passed: Projects interactions, API request handling, and
  agent store behavior. Ant Design emits jsdom pseudo-element warnings; the
  same interactions were separately verified in Chrome.
- TypeScript compilation passed. ESLint passed for the new Projects UI and API
  module. Repository-wide lint still reports existing errors in other modules.
- Production Vite build passed with `NODE_OPTIONS=--max-old-space-size=8192`.
  Existing large vendor chunks and circular chunk warnings remain.
- Real Chrome against the running API, in both development and production:
  create project, reload persistence, open project chat and banner, archive,
  restore, desktop, and 390px mobile. No page JavaScript errors or document
  horizontal overflow were recorded. Screenshots and logs are under `logs/`.
- No actual LLM call or infrastructure operation was made; existing credentials
  were not imported or changed. The preview runs on port 8089 with separate
  `logs/projects-preview` data and secret directories.

The persistence test exposed an existing SQLite write bug: `_execute` returned
before committing statements without result rows. The fix commits writes before
checking their result. Restart regression now verifies settings/projects, MCP
configuration, and knowledge records survive closing/reopening the database.

The broader existing settings-router test suite has outdated fixtures: it patches
`routers.settings._SETTINGS_FILE`, but settings now use `SettingsStore`. Its file
is not the active backend. Those failures are outside the Projects implementation;
the suite was not rewritten or treated as passing.

GitNexus impact was checked before editing existing functions. Final
`detect-changes --scope all` flags aggregate scope HIGH (21 indexed symbols,
13 flows), covering layout plus console/runner entry points. New files were also
reviewed and tested directly, because an existing index does not fully represent
new untracked symbols. No commit or legacy QwenPaw code modification was made.

## Boundaries of this delivery

Projects organize briefs, instructions, connection references, and conversations.
They do not yet provision isolated Python/GPU environments, implement notebook
execution, track ML experiments, scope scheduled jobs/artifacts to projects, or
create generic REST API adapters. Jobs and Connections navigation opens the
existing applications. These capabilities can be added behind the project ID
without presenting unavailable actions in the UI.

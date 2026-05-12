# Local Setup Guide

This guide explains how to run this project locally and how to customize it for your own use.

> **Note:** This repository is a fork of [QwenPaw](https://github.com/agentscope-ai/QwenPaw). The internal package name, CLI command, and Docker image are all still `qwenpaw`. All instructions below use those names.

---

## Prerequisites

### For Docker mode (quickest)
| Requirement | Minimum version |
|---|---|
| [Docker](https://docs.docker.com/get-started/get-docker/) | 20+ |
| [Docker Compose](https://docs.docker.com/compose/install/) | v2 (bundled with Docker Desktop) |

### For source / dev mode
| Requirement | Minimum version | Notes |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.10–3.13 | 3.12 recommended |
| [Node.js](https://nodejs.org/) | 18+ | Required to build the web UI |
| npm | bundled with Node.js | `pnpm` also works |
| Git | any | |

---

## Run mode 1 — Docker (recommended for quick start)

The `docker-compose.yml` in the root of this repository is all you need.

```bash
docker compose up -d
```

Then open **http://127.0.0.1:8088/** in your browser to configure your model and start chatting.

### What the volumes store
| Volume | Container path | Purpose |
|---|---|---|
| `qwenpaw-data` | `/app/working` | App config, memory, and data |
| `qwenpaw-secrets` | `/app/working.secret` | Provider API keys and secrets |
| `qwenpaw-backups` | `/app/working.backups` | Automatic backups |

Data persists across container restarts because it lives in named Docker volumes.

### Enable web login (optional)
Uncomment the `environment` block in `docker-compose.yml`:

```yaml
environment:
  - QWENPAW_AUTH_ENABLED=true
  - QWENPAW_AUTH_USERNAME=admin
  - QWENPAW_AUTH_PASSWORD=yourpassword
```

Then restart:

```bash
docker compose down && docker compose up -d
```

### Stop / remove
```bash
docker compose down          # stop containers, keep volumes
docker compose down -v       # stop containers AND delete all data volumes
```

---

## Run mode 2 — From source (for development and customization)

### 1. Clone and enter the repo

```bash
git clone https://github.com/phamdinhdat-ai/SpiderAgents.git
cd SpiderAgents
```

### 2. Create a Python virtual environment

```bash
python -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows (CMD)
# .venv\Scripts\Activate.ps1    # Windows (PowerShell)
```

### 3. Build the web UI frontend

The console frontend is a Vite/React app that must be compiled before the Python package can serve it.

```bash
cd console
npm ci
npm run build
cd ..
```

### 4. Copy the built frontend into the Python package

```bash
mkdir -p src/qwenpaw/console
cp -R console/dist/. src/qwenpaw/console/
```

### 5. Install the Python package

```bash
# Standard install
pip install -e .

# Dev install (includes pytest, coverage, pre-commit, etc.)
pip install -e ".[dev,full]"
```

### 6. Initialize and start

```bash
qwenpaw init --defaults   # first-time setup (accepts all defaults)
qwenpaw app               # start the app
```

Open **http://127.0.0.1:8088/** in your browser.

### Updating after a `git pull`

When pulling a new version that changes the frontend or Python package:

```bash
git pull
cd console && npm ci && npm run build && cd ..
cp -R console/dist/. src/qwenpaw/console/
pip install -e .
# Restart qwenpaw app, then hard-refresh your browser (Ctrl+Shift+R / Cmd+Shift+R)
```

---

## Run tests

Tests live in `tests/` and are driven by `scripts/run_tests.py`.

```bash
python scripts/run_tests.py          # all tests
python scripts/run_tests.py -u       # unit tests only
python scripts/run_tests.py -i       # integration tests only
python scripts/run_tests.py -a -c    # all tests + coverage report
python scripts/run_tests.py -h       # help
```

---

## Customization options

### A. Configure a model provider (API key or local model)

After starting the app, open the Console at **http://127.0.0.1:8088/** and go to **Settings → Models**. You can:

- Enter an API key for a cloud provider (OpenAI, Google Gemini, DashScope, Volcano Engine, etc.).
- Point at a local model running via Ollama or LM Studio.

If you prefer no cloud API key, install a local model and configure the base URL instead.

### B. Enable or disable channels

The app supports DingTalk, Feishu, WeChat, Discord, Telegram, Twilio, Matrix, and more.

- Enable channels through the Console UI (**Settings → Channels**) or via CLI:
  ```bash
  qwenpaw channels
  ```
- When running in Docker you can also filter channels at startup using environment variables:
  ```yaml
  environment:
    - QWENPAW_DISABLED_CHANNELS=imessage   # exclude specific channels
    # or:
    - QWENPAW_ENABLED_CHANNELS=dingtalk,discord  # whitelist only these
  ```

### C. Add or customize skills / plugins

Skills define what the agent can do (scheduling, PDF/Office handling, news digest, file reading, web browsing, etc.).

- Built-in skills: `src/qwenpaw/agents/skills/`
- Agent prompt templates: `src/qwenpaw/agents/md_files/`
- Plugin entry points: `plugins/`

Drop a new skill file into the skills directory and restart — skills are auto-loaded.

### D. Change or add model providers

Provider integrations live in `src/qwenpaw/providers/`. Add a new file following the existing patterns to support a new model API.

### E. Customize the web frontend

The frontend source is in `console/`. After making changes, rebuild and copy:

```bash
cd console && npm ci && npm run build && cd ..
cp -R console/dist/. src/qwenpaw/console/
```

For Docker deployments you will need to rebuild your custom image (see below).

### F. Customize security and auth

- Application-level auth: `src/qwenpaw/app/auth.py`
- Security rules and scanning: `src/qwenpaw/security/`

---

## Build and run your own Docker image

If you have customised the source and want to package it as a Docker image:

```bash
bash scripts/docker_build.sh spideragents:local
```

Then update `docker-compose.yml` to use your image:

```yaml
services:
  qwenpaw:
    image: spideragents:local   # was: agentscope/qwenpaw:latest
```

And restart:

```bash
docker compose down && docker compose up -d
```

---

## Full rebrand (optional, advanced)

The repository name is `SpiderAgents` but the internal package identity is still `qwenpaw`. If you want to rename it end-to-end, you need to update:

| Location | What to change |
|---|---|
| `pyproject.toml` | `name`, `[project.scripts]` entry points |
| `src/qwenpaw/` | rename directory; update all Python imports |
| `console/` | update branding text and assets |
| `deploy/Dockerfile` | update ENV variable names and paths |
| `docker-compose.yml` | update volume names, image name |
| `scripts/` | update references to `qwenpaw` |
| `README.md` and other docs | update branding |

This is a large refactor. For most use cases, customizing agents, prompts, providers, and the frontend without renaming internals is sufficient.

---

## Summary: minimum requirements

| Goal | Requirements |
|---|---|
| Run with Docker | Docker + Docker Compose |
| Run from source | Python 3.10–3.13 · Node.js 18+ · npm |
| Develop / contribute | All of the above + `pip install -e ".[dev,full]"` |
| Use cloud models | API key from your chosen provider |
| Use local models | Ollama or LM Studio running locally |
| Build custom Docker image | Docker + the source requirements above |

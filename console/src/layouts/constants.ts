// ── URLs ──────────────────────────────────────────────────────────────────

export const GITHUB_URL = "https://github.com/agentscope-ai/OpenSpider" as const;

// ── Navigation ────────────────────────────────────────────────────────────

export const DEFAULT_OPEN_KEYS = [
  "chat-group",
  "control-group",
  "agent-group",
  "settings-group",
];

export const KEY_TO_PATH: Record<string, string> = {
  chat: "/chat",
  channels: "/channels",
  sessions: "/sessions",
  "cron-jobs": "/cron-jobs",
  heartbeat: "/heartbeat",
  skills: "/skills",
  "skill-pool": "/skill-pool",
  tools: "/tools",
  mcp: "/mcp",
  acp: "/acp",
  "core-instruction": "/core-instruction",
  agents: "/agents",
  models: "/models",
  environments: "/environments",
  "agent-config": "/agent-config",
  "token-usage": "/token-usage",
  "agent-stats": "/agent-stats",
  backups: "/backups",
  "plugin-manager": "/plugin-manager",
  "knowledge-base": "/knowledge-base",
  "admin-settings": "/admin-settings",
  "user-management": "/user-management",
};

export const KEY_TO_LABEL: Record<string, string> = {
  chat: "nav.chat",
  channels: "nav.channels",
  sessions: "nav.sessions",
  "cron-jobs": "nav.cronJobs",
  heartbeat: "nav.heartbeat",
  skills: "nav.skills",
  "skill-pool": "nav.skillPool",
  tools: "nav.tools",
  mcp: "nav.mcp",
  acp: "nav.acp",
  "agent-config": "nav.agentConfig",
  workspace: "nav.workspace",
  models: "nav.models",
  environments: "nav.environments",
  security: "nav.security",
  "token-usage": "nav.tokenUsage",
  agents: "nav.agents",
  debug: "nav.debug",
  backups: "nav.backups",
};

// ── URL helpers ───────────────────────────────────────────────────────────

export const getWebsiteLang = (lang: string): string =>
  lang.startsWith("zh") ? "zh" : "en";

export const getDocsUrl = (lang: string): string =>
  `https://openspider.agentscope.io/docs/intro?lang=${getWebsiteLang(lang)}`;

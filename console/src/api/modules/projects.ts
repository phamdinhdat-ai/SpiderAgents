import { request } from "../request";
import type { ChatSpec } from "../types";

export type ProjectTemplate =
  | "exploration"
  | "machine-learning"
  | "pipeline"
  | "research";
export interface ProjectInput {
  name: string;
  description: string;
  objective: string;
  instructions: string;
  template: ProjectTemplate;
  status: "active" | "archived";
  connection_ids: string[];
}
export interface Project extends ProjectInput {
  id: string;
  version: number;
  created_at: string;
  updated_at: string;
}
export interface ProjectConnection {
  id: string;
  name: string;
  transport: string;
  enabled: boolean;
}
const path = (id: string) => `/projects/${encodeURIComponent(id)}`;
export const projectsApi = {
  list: (signal?: AbortSignal) => request<Project[]>("/projects", { signal }),
  get: (id: string, signal?: AbortSignal) =>
    request<Project>(path(id), { signal }),
  create: (body: ProjectInput) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: string, body: ProjectInput & { version: number }) =>
    request<Project>(path(id), { method: "PUT", body: JSON.stringify(body) }),
  connections: (signal?: AbortSignal) =>
    request<ProjectConnection[]>("/projects/connections", { signal }),
  chats: (id: string, signal?: AbortSignal) =>
    request<ChatSpec[]>(`${path(id)}/chats`, { signal }),
  createChat: (id: string) =>
    request<ChatSpec>(`${path(id)}/chats`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  chatContext: (id: string, signal?: AbortSignal) =>
    request<Project | null>(
      `/projects/chat-context/${encodeURIComponent(id)}`,
      { signal },
    ),
};

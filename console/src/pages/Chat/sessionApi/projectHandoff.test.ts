import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatSpec } from "../../../api/types";

const api = vi.hoisted(() => ({ listChats: vi.fn(), getChat: vi.fn() }));
vi.mock("../../../api", () => ({ default: api }));
vi.mock("../utils", () => ({ toDisplayUrl: (value: string) => value }));

const chat = (id: string): ChatSpec => ({
  id,
  session_id: `project:project-id:${id}`,
  user_id: "alice",
  channel: "console",
  name: `Project ${id}`,
  meta: { project_id: "project-id" },
  created_at: null,
  updated_at: null,
});
beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  api.listChats.mockResolvedValue([]);
  api.getChat.mockResolvedValue({ messages: [], status: "idle" });
});

describe("project chat handoff", () => {
  it("retains canonical session identity before the chat library loads its list", async () => {
    const { default: sessions } = await import("./index");
    sessions.adoptChat(chat("new-chat"));
    const result = await sessions.getSession("new-chat");
    expect(result).toMatchObject({
      sessionId: "project:project-id:new-chat",
      userId: "alice",
      meta: { project_id: "project-id" },
    });
    expect((window as Window & { currentSessionId?: string }).currentSessionId).toBe("project:project-id:new-chat");
  });

  it("does not lose the new project chat to a list response started before creation", async () => {
    let finish!: (value: ChatSpec[]) => void;
    api.listChats.mockImplementationOnce(
      () =>
        new Promise<ChatSpec[]>((resolve) => {
          finish = resolve;
        }),
    );
    const { default: sessions } = await import("./index");
    const pending = sessions.getSessionList();
    sessions.adoptChat(chat("new-chat"));
    finish([chat("older-chat")]);
    const list = await pending;
    expect(list[0].id).toBe("new-chat");
    expect(await sessions.getSession("new-chat")).toMatchObject({
      sessionId: "project:project-id:new-chat",
    });
  });

  it("does not let a slow previous chat overwrite the selected project's identity", async () => {
    let finish!: (value: { messages: []; status: string }) => void;
    api.getChat.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const { default: sessions } = await import("./index");
    const selected = vi.fn();
    sessions.onSessionSelected = selected;
    sessions.adoptChat(chat("old-chat"));
    const old = sessions.getSession("old-chat");
    sessions.adoptChat(chat("new-chat"));
    await sessions.getSession("new-chat");
    finish({ messages: [], status: "idle" });
    await old;
    expect((window as Window & { currentSessionId?: string }).currentSessionId).toBe("project:project-id:new-chat");
    expect(selected).toHaveBeenCalledTimes(1);
    expect(selected).toHaveBeenCalledWith("new-chat", null);
  });
});

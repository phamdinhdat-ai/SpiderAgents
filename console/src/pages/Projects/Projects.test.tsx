import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { App } from "antd";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ProjectsPage from "./index";
import { projectsApi, type Project } from "../../api/modules/projects";
import { emptyProject } from "./templates";

vi.mock("../../api/modules/projects", () => ({
  projectsApi: {
    list: vi.fn(),
    connections: vi.fn(),
    chats: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    createChat: vi.fn(),
  },
}));
vi.mock("../Chat/sessionApi", () => ({ default: { adoptChat: vi.fn() } }));
vi.mock("../../stores/agentStore", () => ({
  useAgentStore: (selector: (state: { selectedAgent: string }) => unknown) =>
    selector({ selectedAgent: "analyst" }),
}));
const project: Project = {
  ...emptyProject(),
  id: "p1",
  name: "Churn research",
  description: "Understand retention",
  objective: "Compare baselines",
  version: 1,
  created_at: "2026-10-16T00:00:00Z",
  updated_at: "2026-10-16T00:00:00Z",
};

function setup(path = "/projects") {
  return render(
    <App>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectsPage />} />
          <Route path="/chat/:chatId" element={<p>Conversation opened</p>} />
        </Routes>
      </MemoryRouter>
    </App>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(projectsApi.list).mockResolvedValue([project]);
  vi.mocked(projectsApi.connections).mockResolvedValue([]);
  vi.mocked(projectsApi.chats).mockResolvedValue([]);
});

describe("Projects workspace", () => {
  it("filters actual projects without creating demo data", async () => {
    setup();
    expect(
      await screen.findByRole("heading", { name: "Churn research" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Search projects" }), {
      target: { value: "not present" },
    });
    expect(
      screen.getByText("No projects match your search"),
    ).toBeInTheDocument();
    expect(projectsApi.create).not.toHaveBeenCalled();
  });

  it("creates a project from a template and opens its persisted detail", async () => {
    vi.mocked(projectsApi.list).mockResolvedValue([]);
    vi.mocked(projectsApi.create).mockResolvedValue(project);
    setup();
    fireEvent.click(
      await screen.findByRole("button", {
        name: /Machine learning.*Use template/,
      }),
    );
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Project name"), {
      target: { value: project.name },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Create project" }),
    );
    await waitFor(() => expect(projectsApi.create).toHaveBeenCalled());
    expect(vi.mocked(projectsApi.create).mock.calls[0][0]).toMatchObject({
      name: project.name,
      template: "machine-learning",
    });
    expect(
      await screen.findByRole("heading", { name: project.name }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Compare baselines")).toBeInTheDocument();
  });

  it("opens a real project conversation through the backend entry point", async () => {
    vi.mocked(projectsApi.createChat).mockResolvedValue({
      id: "chat1",
      name: "New",
      session_id: "sid",
      user_id: "alice",
      channel: "console",
      created_at: null,
      updated_at: null,
    });
    setup("/projects/p1");
    fireEvent.click(
      await screen.findByRole("button", { name: "New conversation" }),
    );
    expect(await screen.findByText("Conversation opened")).toBeInTheDocument();
    expect(projectsApi.createChat).toHaveBeenCalledWith("p1");
  });

  it("keeps edits open when the server rejects a stale version", async () => {
    vi.mocked(projectsApi.update).mockRejectedValue(
      new Error("Project changed. Reload before saving."),
    );
    setup("/projects/p1");
    fireEvent.click(await screen.findByRole("button", { name: "Customize" }));
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Save changes",
      }),
    );
    expect(
      await screen.findByText("Project changed. Reload before saving."),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(projectsApi.update).toHaveBeenCalledWith(
      "p1",
      expect.objectContaining({ version: 1 }),
    );
  });

  it("shows a recoverable loading error instead of an empty workspace", async () => {
    vi.mocked(projectsApi.list).mockRejectedValueOnce(new Error("Offline"));
    setup();
    expect(
      await screen.findByText("We couldn't load your projects"),
    ).toBeInTheDocument();
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Try again" })),
    );
    expect(
      await screen.findByRole("heading", { name: "Churn research" }),
    ).toBeInTheDocument();
  });
});

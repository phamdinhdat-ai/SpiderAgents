import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import PageTransition from "./index";

function Harness() {
  const navigate = useNavigate();
  const [revision, setRevision] = useState(0);
  return (
    <>
      <button onClick={() => navigate("/chat/project-chat")}>
        Open project chat
      </button>
      <button onClick={() => setRevision((n) => n + 1)}>Refresh parent</button>
      <PageTransition>
        <Routes>
          <Route
            path="/projects"
            element={<p>Project revision {revision}</p>}
          />
          <Route
            path="/chat/:id"
            element={<textarea aria-label="Project message" />}
          />
        </Routes>
      </PageTransition>
    </>
  );
}

afterEach(() => vi.useRealTimers());
describe("project to chat transition", () => {
  it("does not strand the chat in fade-out when a parent rerenders mid-navigation", () => {
    vi.useFakeTimers();
    const { container } = render(
      <MemoryRouter initialEntries={["/projects"]}>
        <Harness />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Open project chat"));
    fireEvent.click(screen.getByText("Refresh parent"));
    act(() => vi.advanceTimersByTime(200));
    expect(
      screen.getByRole("textbox", { name: "Project message" }),
    ).toBeInTheDocument();
    expect(container.querySelector(".page-transition")).not.toHaveClass(
      "page-transition-fadeOut",
    );
  });

  it("renders new route props immediately at the same URL", () => {
    render(
      <MemoryRouter initialEntries={["/projects"]}>
        <Harness />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText("Refresh parent"));
    expect(screen.getByText("Project revision 1")).toBeInTheDocument();
  });
});

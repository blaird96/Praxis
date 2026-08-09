import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import * as client from "./api/client";
import { setCapabilityTokenForTests } from "./api/token";

vi.mock("./components/FileEditor", () => ({
  FileEditor: ({
    path,
    content,
    onChange,
    onSave,
  }: {
    path: string;
    content: string;
    onChange: (value: string) => void;
    onSave: () => void;
  }) => (
    <textarea
      data-testid="monaco-mock"
      data-path={path}
      value={content}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
          e.preventDefault();
          onSave();
        }
      }}
    />
  ),
}));

vi.mock("./components/TerminalPane", () => ({
  TerminalPane: ({
    sessionId,
    restartToken,
  }: {
    sessionId: string;
    restartToken: number;
  }) => (
    <div
      data-testid="terminal-pane"
      data-session={sessionId}
      data-restart={restartToken}
    />
  ),
}));

const catalog: client.Catalog = {
  modules: [
    {
      id: "git",
      title: "Git",
      scenarios: [
        {
          id: "merge-conflict",
          title: "Resolve a merge conflict",
          description: "Finish a conflicted merge on main.",
          difficulty: "beginner",
        },
      ],
    },
  ],
};

const session: client.Session = {
  session_id: "abc123",
  module: "git",
  scenario: "merge-conflict",
  status: "active",
  workspace_path: "C:/tmp/ws",
  repo_path: "C:/tmp/ws/repo",
  assignment: {
    title: "Resolve a merge conflict",
    summary: "Fix the merge.",
    objectives: ["Stay on main"],
  },
  check: {
    passed: false,
    objectives: [
      {
        id: "on-main",
        description: "HEAD is attached to branch main",
        passed: true,
        detail: null,
      },
    ],
  },
  previous_session_id: null,
};

const rootListing: client.FileList = {
  path: ".",
  entries: [
    { name: "docs", path: "docs", kind: "directory" },
    { name: "greeting.txt", path: "greeting.txt", kind: "file" },
  ],
};

const docsListing: client.FileList = {
  path: "docs",
  entries: [{ name: "note.txt", path: "docs/note.txt", kind: "file" }],
};

describe("App start flow", () => {
  beforeEach(() => {
    setCapabilityTokenForTests("test-token");
    vi.restoreAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("renders catalog when there is no active session", async () => {
    vi.spyOn(client, "fetchCatalog").mockResolvedValue(catalog);
    vi.spyOn(client, "fetchSession").mockRejectedValue(
      new Error("No active Praxis session"),
    );

    render(<App />);

    expect(await screen.findByTestId("catalog")).toBeInTheDocument();
    expect(screen.getByText("Resolve a merge conflict")).toBeInTheDocument();
  });

  it("starts selected scenario and transitions to dashboard", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "fetchCatalog").mockResolvedValue(catalog);
    vi.spyOn(client, "fetchSession").mockRejectedValue(
      new Error("No active Praxis session"),
    );
    vi.spyOn(client, "listFiles").mockResolvedValue(rootListing);
    const start = vi.spyOn(client, "startSession").mockResolvedValue({
      ...session,
      previous_session_id: "oldsession",
    });

    render(<App />);
    await screen.findByTestId("catalog");
    await user.click(screen.getByTestId("start-git-merge-conflict"));

    await waitFor(() => {
      expect(start).toHaveBeenCalledWith("git", "merge-conflict");
    });
    expect(await screen.findByTestId("session-dashboard")).toBeInTheDocument();
    expect(
      screen.getByText(/Previous session retained: oldsession/),
    ).toBeInTheDocument();
  });

  it("New Exercise returns to catalog without calling reset/start", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "fetchCatalog").mockResolvedValue(catalog);
    vi.spyOn(client, "fetchSession").mockResolvedValue(session);
    vi.spyOn(client, "listFiles").mockResolvedValue(rootListing);
    const start = vi.spyOn(client, "startSession");
    const reset = vi.spyOn(client, "resetSession");

    render(<App />);
    expect(await screen.findByTestId("session-dashboard")).toBeInTheDocument();
    await user.click(screen.getByTestId("new-exercise-button"));
    expect(await screen.findByTestId("catalog")).toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
    expect(reset).not.toHaveBeenCalled();
  });
});

describe("Workbench file editing", () => {
  beforeEach(() => {
    setCapabilityTokenForTests("test-token");
    vi.restoreAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(client, "fetchCatalog").mockResolvedValue(catalog);
    vi.spyOn(client, "fetchSession").mockResolvedValue(session);
    vi.spyOn(client, "listFiles").mockResolvedValue(rootListing);
  });

  it("loads file tree from API and expands directories lazily", async () => {
    const user = userEvent.setup();
    const list = vi.spyOn(client, "listFiles").mockImplementation(async (path = ".") => {
      if (path === "." || path === "") return rootListing;
      if (path === "docs") return docsListing;
      throw new Error(`unexpected path ${path}`);
    });

    render(<App />);
    expect(await screen.findByTestId("tree-file-greeting.txt")).toBeInTheDocument();
    expect(list).toHaveBeenCalledWith(".");

    await user.click(screen.getByTestId("tree-dir-docs"));
    expect(await screen.findByTestId("tree-file-docs/note.txt")).toBeInTheDocument();
    expect(list).toHaveBeenCalledWith("docs");
  });

  it("selecting a file loads content and save sends expected_revision", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "listFiles").mockResolvedValue(rootListing);
    vi.spyOn(client, "readFile").mockResolvedValue({
      path: "greeting.txt",
      content: "old content",
      revision: "rev-1",
      size: 11,
    });
    const write = vi.spyOn(client, "writeFile").mockResolvedValue({
      path: "greeting.txt",
      revision: "rev-2",
      size: 12,
    });

    render(<App />);
    await user.click(await screen.findByTestId("tree-file-greeting.txt"));
    const editor = await screen.findByTestId("monaco-mock");
    expect(editor).toHaveValue("old content");

    await user.clear(editor);
    await user.type(editor, "new content");
    expect(screen.getByTestId("save-button")).not.toBeDisabled();
    await user.click(screen.getByTestId("save-button"));

    await waitFor(() => {
      expect(write).toHaveBeenCalledWith("greeting.txt", "new content", "rev-1");
    });
    await waitFor(() => {
      expect(screen.getByTestId("save-status")).toHaveTextContent("Saved");
    });
    expect(screen.getByTestId("save-button")).toBeDisabled();
  });

  it("stale save conflict is visible and keeps editor contents", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "listFiles").mockResolvedValue(rootListing);
    vi.spyOn(client, "readFile").mockResolvedValue({
      path: "greeting.txt",
      content: "mine",
      revision: "rev-1",
      size: 4,
    });
    vi.spyOn(client, "writeFile").mockRejectedValue(
      new client.ApiError("changed since loaded", 409, "file_conflict"),
    );

    render(<App />);
    await user.click(await screen.findByTestId("tree-file-greeting.txt"));
    const editor = await screen.findByTestId("monaco-mock");
    await user.type(editor, "!");
    await user.click(screen.getByTestId("save-button"));

    expect(await screen.findByTestId("save-conflict")).toBeInTheDocument();
    expect(editor).toHaveValue("mine!");
  });

  it("switching away from dirty content requires confirmation", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.spyOn(client, "listFiles").mockResolvedValue({
      path: ".",
      entries: [
        { name: "a.txt", path: "a.txt", kind: "file" },
        { name: "b.txt", path: "b.txt", kind: "file" },
      ],
    });
    vi.spyOn(client, "readFile").mockImplementation(async (path) => ({
      path,
      content: `content-${path}`,
      revision: `rev-${path}`,
      size: 10,
    }));

    render(<App />);
    await user.click(await screen.findByTestId("tree-file-a.txt"));
    const editor = await screen.findByTestId("monaco-mock");
    await user.type(editor, "x");
    await user.click(screen.getByTestId("tree-file-b.txt"));
    expect(confirm).toHaveBeenCalled();
    expect(editor).toHaveAttribute("data-path", "a.txt");
  });

  it("unsupported file shows useful feedback", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "listFiles").mockResolvedValue({
      path: ".",
      entries: [{ name: "blob.bin", path: "blob.bin", kind: "file" }],
    });
    vi.spyOn(client, "readFile").mockRejectedValue(
      new client.ApiError("blob.bin looks like a binary file", 415, "unsupported_text"),
    );

    render(<App />);
    await user.click(await screen.findByTestId("tree-file-blob.bin"));
    expect(await screen.findByTestId("file-load-error")).toHaveTextContent(/binary/i);
  });

  it("Reset clears editor, reloads tree, and remounts terminal", async () => {
    const user = userEvent.setup();
    const list = vi.spyOn(client, "listFiles").mockResolvedValue(rootListing);
    vi.spyOn(client, "readFile").mockResolvedValue({
      path: "greeting.txt",
      content: "conflicted",
      revision: "rev-1",
      size: 10,
    });
    vi.spyOn(client, "resetSession").mockResolvedValue({
      ...session,
      check: session.check,
    });

    render(<App />);
    await user.click(await screen.findByTestId("tree-file-greeting.txt"));
    expect(await screen.findByTestId("monaco-mock")).toBeInTheDocument();
    const term = screen.getByTestId("terminal-pane");
    expect(term).toHaveAttribute("data-restart", "0");
    const callsBefore = list.mock.calls.length;
    await user.click(screen.getByTestId("reset-button"));
    await waitFor(() => {
      expect(screen.queryByTestId("monaco-mock")).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(list.mock.calls.length).toBeGreaterThan(callsBefore);
    });
    expect(screen.getByTestId("terminal-pane")).toHaveAttribute("data-restart", "1");
  });

  it("Reload From Disk appears on stale revision conflict", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "listFiles").mockResolvedValue(rootListing);
    vi.spyOn(client, "readFile")
      .mockResolvedValueOnce({
        path: "greeting.txt",
        content: "mine",
        revision: "rev-1",
        size: 4,
      })
      .mockResolvedValueOnce({
        path: "greeting.txt",
        content: "from disk",
        revision: "rev-2",
        size: 9,
      });
    vi.spyOn(client, "writeFile").mockRejectedValue(
      new client.ApiError("changed since loaded", 409, "file_conflict"),
    );

    render(<App />);
    await user.click(await screen.findByTestId("tree-file-greeting.txt"));
    const editor = await screen.findByTestId("monaco-mock");
    await user.type(editor, "!");
    await user.click(screen.getByTestId("save-button"));
    expect(await screen.findByTestId("save-conflict")).toBeInTheDocument();
    await user.click(screen.getByTestId("reload-file-button"));
    await waitFor(() => {
      expect(screen.getByTestId("monaco-mock")).toHaveValue("from disk");
    });
  });

  it("Check continues using backend validation", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "listFiles").mockResolvedValue(rootListing);
    const check = vi.spyOn(client, "checkSession").mockResolvedValue({
      ...session,
      check: {
        passed: false,
        objectives: [
          {
            id: "no-markers",
            description: "No conflict markers",
            passed: false,
            detail: null,
          },
        ],
      },
    });

    render(<App />);
    await screen.findByTestId("session-dashboard");
    await user.click(screen.getByTestId("check-button"));
    await waitFor(() => expect(check).toHaveBeenCalled());
    expect(await screen.findByText("No conflict markers")).toBeInTheDocument();
  });
});

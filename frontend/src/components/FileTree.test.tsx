import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { FileTree } from "./FileTree";

describe("FileTree", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a new file in the repo root and opens it", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "listFiles").mockImplementation(async (path = ".") => {
      if (path === ".") {
        return { path: ".", entries: [{ name: "a.txt", path: "a.txt", kind: "file" }] };
      }
      return { path, entries: [] };
    });
    const createFile = vi
      .spyOn(client, "createFile")
      .mockResolvedValue({ path: "notes.txt", revision: "rev-1", size: 0 });
    const onSelectFile = vi.fn();

    render(
      <FileTree treeKey={0} selectedPath={null} onSelectFile={onSelectFile} />,
    );
    await screen.findByTestId("tree-file-a.txt");

    await user.click(screen.getByTestId("new-file-button"));
    await user.type(screen.getByTestId("file-tree-create-input"), "notes.txt");
    await user.click(screen.getByTestId("file-tree-create-confirm"));

    await waitFor(() => expect(createFile).toHaveBeenCalledWith("notes.txt"));
    expect(onSelectFile).toHaveBeenCalledWith("notes.txt");
    expect(screen.queryByTestId("file-tree-create-form")).not.toBeInTheDocument();
  });

  it("creates a new folder inside a selected directory", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "listFiles").mockImplementation(async (path = ".") => {
      if (path === ".") {
        return {
          path: ".",
          entries: [{ name: "docs", path: "docs", kind: "directory" }],
        };
      }
      return { path, entries: [] };
    });
    const createDirectory = vi
      .spyOn(client, "createDirectory")
      .mockResolvedValue({ path: "docs/nested", created: true });

    render(<FileTree treeKey={0} selectedPath={null} onSelectFile={vi.fn()} />);
    await user.click(await screen.findByTestId("tree-dir-docs"));

    await user.click(screen.getByTestId("new-folder-button"));
    await user.type(screen.getByTestId("file-tree-create-input"), "nested");
    await user.click(screen.getByTestId("file-tree-create-confirm"));

    await waitFor(() =>
      expect(createDirectory).toHaveBeenCalledWith("docs/nested"),
    );
  });

  it("shows an inline error and keeps the form open when creation fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "listFiles").mockResolvedValue({ path: ".", entries: [] });
    vi.spyOn(client, "createFile").mockRejectedValue(
      new client.ApiError("greeting.txt already exists", 409, "path_conflict"),
    );

    render(<FileTree treeKey={0} selectedPath={null} onSelectFile={vi.fn()} />);
    await user.click(screen.getByTestId("new-file-button"));
    await user.type(screen.getByTestId("file-tree-create-input"), "greeting.txt");
    await user.click(screen.getByTestId("file-tree-create-confirm"));

    expect(await screen.findByTestId("file-tree-create-error")).toHaveTextContent(
      /already exists/i,
    );
    expect(screen.getByTestId("file-tree-create-form")).toBeInTheDocument();
  });

  it("cancelling the create form hides it without calling the API", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "listFiles").mockResolvedValue({ path: ".", entries: [] });
    const createFile = vi.spyOn(client, "createFile");

    render(<FileTree treeKey={0} selectedPath={null} onSelectFile={vi.fn()} />);
    await user.click(screen.getByTestId("new-file-button"));
    await user.click(screen.getByText("Cancel"));

    expect(screen.queryByTestId("file-tree-create-form")).not.toBeInTheDocument();
    expect(createFile).not.toHaveBeenCalled();
  });
});

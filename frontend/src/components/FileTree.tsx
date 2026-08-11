import { useEffect, useState } from "react";
import { ApiError, createDirectory, createFile, listFiles, type DirEntry } from "../api/client";

type Props = {
  onSelectFile: (path: string) => void;
  selectedPath: string | null;
  treeKey: number;
};

type NodeState = {
  entries: DirEntry[] | null;
  expanded: boolean;
  loading: boolean;
  error: string | null;
};

type Creating = {
  kind: "file" | "folder";
  parentDir: string;
  name: string;
  error: string | null;
  submitting: boolean;
};

export function FileTree({ onSelectFile, selectedPath, treeKey }: Props) {
  const [root, setRoot] = useState<NodeState>({
    entries: null,
    expanded: true,
    loading: true,
    error: null,
  });
  const [dirs, setDirs] = useState<Record<string, NodeState>>({});
  const [targetDir, setTargetDir] = useState<string>(".");
  const [creating, setCreating] = useState<Creating | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRoot({ entries: null, expanded: true, loading: true, error: null });
    setDirs({});
    setTargetDir(".");
    setCreating(null);
    void listFiles(".")
      .then((listing) => {
        if (!cancelled) {
          setRoot({
            entries: listing.entries,
            expanded: true,
            loading: false,
            error: null,
          });
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setRoot({
            entries: null,
            expanded: true,
            loading: false,
            error: err.message,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [treeKey]);

  /** Re-fetch a single directory listing after a create, without a full tree refresh. */
  async function refreshDir(dirPath: string) {
    try {
      const listing = await listFiles(dirPath);
      if (dirPath === ".") {
        setRoot((prev) => ({ ...prev, entries: listing.entries, error: null }));
      } else {
        setDirs((prev) => ({
          ...prev,
          [dirPath]: {
            entries: listing.entries,
            expanded: true,
            loading: false,
            error: null,
          },
        }));
      }
    } catch {
      /* best-effort refresh; the create itself already succeeded */
    }
  }

  function startCreating(kind: "file" | "folder") {
    setCreating({ kind, parentDir: targetDir, name: "", error: null, submitting: false });
  }

  function cancelCreating() {
    setCreating(null);
  }

  async function submitCreating() {
    if (!creating || creating.submitting) return;
    const name = creating.name.trim();
    if (!name) {
      setCreating({ ...creating, error: "Name is required" });
      return;
    }
    const fullPath =
      creating.parentDir === "." ? name : `${creating.parentDir}/${name}`;
    setCreating({ ...creating, submitting: true, error: null });
    try {
      if (creating.kind === "file") {
        await createFile(fullPath);
      } else {
        await createDirectory(fullPath);
      }
      await refreshDir(creating.parentDir);
      setCreating(null);
      if (creating.kind === "file") {
        onSelectFile(fullPath);
      }
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err);
      setCreating({ ...creating, submitting: false, error: message });
    }
  }

  async function toggleDir(path: string) {
    const current = dirs[path];
    if (current?.expanded) {
      setDirs((prev) => ({
        ...prev,
        [path]: { ...current, expanded: false },
      }));
      return;
    }
    if (current?.entries) {
      setDirs((prev) => ({
        ...prev,
        [path]: { ...current, expanded: true },
      }));
      return;
    }
    setDirs((prev) => ({
      ...prev,
      [path]: {
        entries: null,
        expanded: true,
        loading: true,
        error: null,
      },
    }));
    try {
      const listing = await listFiles(path);
      setDirs((prev) => ({
        ...prev,
        [path]: {
          entries: listing.entries,
          expanded: true,
          loading: false,
          error: null,
        },
      }));
    } catch (err) {
      setDirs((prev) => ({
        ...prev,
        [path]: {
          entries: null,
          expanded: true,
          loading: false,
          error: err instanceof Error ? err.message : String(err),
        },
      }));
    }
  }

  function renderEntries(entries: DirEntry[], depth: number) {
    return (
      <ul className="file-tree-list" style={{ paddingLeft: depth ? 0.75 : 0 }}>
        {entries.map((entry) => {
          if (entry.kind === "directory") {
            const state = dirs[entry.path];
            const expanded = state?.expanded ?? false;
            return (
              <li key={entry.path}>
                <button
                  type="button"
                  className={
                    "file-tree-item dir" +
                    (targetDir === entry.path ? " selected" : "")
                  }
                  data-testid={`tree-dir-${entry.path}`}
                  onClick={() => {
                    setTargetDir(entry.path);
                    void toggleDir(entry.path);
                  }}
                >
                  <span className="tree-twist">{expanded ? "▾" : "▸"}</span>
                  {entry.name}
                </button>
                {expanded && state?.loading && (
                  <div className="muted tree-msg">Loading…</div>
                )}
                {expanded && state?.error && (
                  <div className="error tree-msg">{state.error}</div>
                )}
                {expanded && state?.entries && renderEntries(state.entries, depth + 1)}
              </li>
            );
          }
          if (entry.kind === "symlink") {
            return (
              <li key={entry.path}>
                <span
                  className="file-tree-item symlink muted"
                  title="Symlinks are not editable in the GUI"
                >
                  {entry.name} ↗
                </span>
              </li>
            );
          }
          return (
            <li key={entry.path}>
              <button
                type="button"
                className={
                  "file-tree-item file" +
                  (selectedPath === entry.path ? " selected" : "")
                }
                data-testid={`tree-file-${entry.path}`}
                onClick={() => onSelectFile(entry.path)}
              >
                {entry.name}
              </button>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <div className="file-tree" data-testid="file-tree">
      <h2>Files</h2>
      <div className="file-tree-toolbar">
        <button
          type="button"
          data-testid="new-file-button"
          onClick={() => startCreating("file")}
        >
          + File
        </button>
        <button
          type="button"
          data-testid="new-folder-button"
          onClick={() => startCreating("folder")}
        >
          + Folder
        </button>
      </div>
      <p className="muted file-tree-target">
        New items are added to:{" "}
        <button
          type="button"
          className="link-button"
          data-testid="tree-root-target"
          onClick={() => setTargetDir(".")}
        >
          {targetDir === "." ? "repo root" : targetDir}
        </button>
      </p>
      {creating && (
        <form
          className="file-tree-create-form"
          data-testid="file-tree-create-form"
          onSubmit={(e) => {
            e.preventDefault();
            void submitCreating();
          }}
        >
          <span className="muted">
            New {creating.kind} in{" "}
            {creating.parentDir === "." ? "repo root" : creating.parentDir}:
          </span>
          <input
            type="text"
            autoFocus
            data-testid="file-tree-create-input"
            placeholder={creating.kind === "file" ? "filename.txt" : "folder-name"}
            value={creating.name}
            disabled={creating.submitting}
            onChange={(e) =>
              setCreating({ ...creating, name: e.target.value, error: null })
            }
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                cancelCreating();
              }
            }}
          />
          <div className="actions">
            <button
              type="submit"
              className="primary"
              disabled={creating.submitting}
              data-testid="file-tree-create-confirm"
            >
              {creating.submitting ? "Creating…" : "Create"}
            </button>
            <button type="button" onClick={cancelCreating} disabled={creating.submitting}>
              Cancel
            </button>
          </div>
          {creating.error && (
            <div className="error tree-msg" data-testid="file-tree-create-error">
              {creating.error}
            </div>
          )}
        </form>
      )}
      {root.loading && <p className="muted">Loading…</p>}
      {root.error && <p className="error">{root.error}</p>}
      {root.entries && renderEntries(root.entries, 0)}
    </div>
  );
}

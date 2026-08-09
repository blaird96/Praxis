import { useEffect, useState } from "react";
import { listFiles, type DirEntry } from "../api/client";

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

export function FileTree({ onSelectFile, selectedPath, treeKey }: Props) {
  const [root, setRoot] = useState<NodeState>({
    entries: null,
    expanded: true,
    loading: true,
    error: null,
  });
  const [dirs, setDirs] = useState<Record<string, NodeState>>({});

  useEffect(() => {
    let cancelled = false;
    setRoot({ entries: null, expanded: true, loading: true, error: null });
    setDirs({});
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
                  className="file-tree-item dir"
                  data-testid={`tree-dir-${entry.path}`}
                  onClick={() => void toggleDir(entry.path)}
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
      {root.loading && <p className="muted">Loading…</p>}
      {root.error && <p className="error">{root.error}</p>}
      {root.entries && renderEntries(root.entries, 0)}
    </div>
  );
}

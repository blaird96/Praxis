import { useCallback, useState, type FunctionComponent } from "react";
import {
  DockviewReact,
  type DockviewApi,
  type DockviewReadyEvent,
  type IDockviewPanelProps,
  type SerializedDockview,
} from "dockview-react";
import "dockview-react/dist/styles/dockview.css";
import {
  ApiError,
  readFile,
  writeFile,
  type CheckResult,
  type Session,
} from "../api/client";
import { AssignmentPane } from "./AssignmentPane";
import { CoachPanel } from "./CoachPanel";
import { EditorPane } from "./EditorPane";
import { FileTree } from "./FileTree";
import { ObjectivesPane } from "./ObjectivesPane";
import { TerminalPane } from "./TerminalPane";
import {
  useWorkbench,
  WorkbenchContext,
  type OpenFile,
  type WorkbenchState,
} from "./WorkbenchContext";
import { WorkbenchSidebar } from "./WorkbenchSidebar";
import { buildDefaultLayout, LAYOUT_STORAGE_KEY } from "./workbenchLayout";

type Props = {
  session: Session;
  check: CheckResult | null;
  busy: boolean;
  info: string | null;
  onCheck: () => void;
  onReset: () => Promise<void>;
  onNewExercise: () => void;
  onOpenSettings: () => void;
};

function FilesPane() {
  const { treeKey, open, openFile } = useWorkbench();
  return (
    <aside className="workbench-files panel">
      <FileTree
        treeKey={treeKey}
        selectedPath={open?.path ?? null}
        onSelectFile={openFile}
      />
    </aside>
  );
}

function CoachPaneContent() {
  const { session, onOpenSettings } = useWorkbench();
  return (
    <CoachPanel
      sessionId={session.session_id}
      onOpenSettings={onOpenSettings}
    />
  );
}

function TerminalPaneContent() {
  const { session, terminalKey } = useWorkbench();
  return <TerminalPane sessionId={session.session_id} restartToken={terminalKey} />;
}

// Module-level (not recreated per render): none of these read anything but
// WorkbenchContext, so a fresh object each render would only cause needless
// panel component churn in Dockview.
const components: Record<string, FunctionComponent<IDockviewPanelProps>> = {
  assignment: AssignmentPane,
  files: FilesPane,
  editor: EditorPane,
  objectives: ObjectivesPane,
  coach: CoachPaneContent,
  terminal: TerminalPaneContent,
};

export function SessionDashboard({
  session,
  check,
  busy,
  info,
  onCheck,
  onReset,
  onNewExercise,
  onOpenSettings,
}: Props) {
  const assignment = session.assignment;
  const [treeKey, setTreeKey] = useState(0);
  const [terminalKey, setTerminalKey] = useState(0);
  const [open, setOpen] = useState<OpenFile | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [dockApi, setDockApi] = useState<DockviewApi | null>(null);

  const dirty = open !== null && open.content !== open.baseline;

  const clearEditor = useCallback(() => {
    setOpen(null);
    setLoadError(null);
    setSaveMsg(null);
    setConflict(null);
  }, []);

  const openFile = useCallback(
    (path: string) => {
      void (async () => {
        if (open && dirty) {
          const proceed = window.confirm(
            `Discard unsaved changes to ${open.path}?`,
          );
          if (!proceed) return;
        }
        setLoadError(null);
        setSaveMsg(null);
        setConflict(null);
        try {
          const file = await readFile(path);
          setOpen({
            path: file.path,
            content: file.content,
            revision: file.revision,
            baseline: file.content,
          });
        } catch (err) {
          clearEditor();
          setLoadError(err instanceof Error ? err.message : String(err));
        }
      })();
    },
    [open, dirty, clearEditor],
  );

  const reloadFromDisk = useCallback(() => {
    void (async () => {
      if (!open) return;
      if (dirty) {
        const proceed = window.confirm(
          `Discard unsaved changes to ${open.path} and reload from disk?`,
        );
        if (!proceed) return;
      }
      try {
        const file = await readFile(open.path);
        setOpen({
          path: file.path,
          content: file.content,
          revision: file.revision,
          baseline: file.content,
        });
        setConflict(null);
        setSaveMsg("Reloaded from disk");
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : String(err));
      }
    })();
  }, [open, dirty]);

  const save = useCallback(() => {
    void (async () => {
      if (!open || saving) return;
      setSaving(true);
      setConflict(null);
      setSaveMsg(null);
      try {
        const result = await writeFile(open.path, open.content, open.revision);
        setOpen((cur) =>
          cur ? { ...cur, revision: result.revision, baseline: cur.content } : cur,
        );
        setSaveMsg("Saved");
      } catch (err) {
        if (err instanceof ApiError && err.code === "file_conflict") {
          setConflict(err.message);
        } else {
          setSaveMsg(err instanceof Error ? err.message : String(err));
        }
      } finally {
        setSaving(false);
      }
    })();
  }, [open, saving]);

  const setEditorContent = useCallback((value: string) => {
    setOpen((cur) => (cur ? { ...cur, content: value } : cur));
  }, []);

  async function handleReset() {
    const message = dirty
      ? "Reset will discard unsaved editor changes and recreate the exercise repository. Continue?"
      : "Reset will recreate the exercise repository and discard saved exercise work. Continue?";
    if (!window.confirm(message)) return;
    await onReset();
    clearEditor();
    setTreeKey((k) => k + 1);
    setTerminalKey((k) => k + 1);
  }

  const onReady = useCallback((event: DockviewReadyEvent) => {
    const api = event.api;
    setDockApi(api);

    let restored = false;
    try {
      const saved = window.localStorage.getItem(LAYOUT_STORAGE_KEY);
      if (saved) {
        api.fromJSON(JSON.parse(saved) as SerializedDockview);
        restored = true;
      }
    } catch {
      restored = false;
    }
    if (!restored || api.panels.length === 0) {
      buildDefaultLayout(api);
    }

    let saveHandle: ReturnType<typeof window.setTimeout> | undefined;
    api.onDidLayoutChange(() => {
      if (saveHandle !== undefined) window.clearTimeout(saveHandle);
      saveHandle = window.setTimeout(() => {
        try {
          window.localStorage.setItem(
            LAYOUT_STORAGE_KEY,
            JSON.stringify(api.toJSON()),
          );
        } catch {
          // localStorage unavailable/full - layout just won't persist.
        }
      }, 250);
    });
  }, []);

  const workbenchValue: WorkbenchState = {
    session,
    check,
    busy,
    treeKey,
    terminalKey,
    open,
    dirty,
    loadError,
    saveMsg,
    conflict,
    saving,
    onOpenSettings,
    onCheck,
    openFile,
    reloadFromDisk,
    save,
    setEditorContent,
  };

  return (
    <div className="workbench" data-testid="session-dashboard">
      <div className="workbench-toolbar">
        <div>
          <strong>
            {session.module} / {assignment.title}
          </strong>
          <span className="muted toolbar-meta">
            {" "}
            · session <span className="mono">{session.session_id}</span>
          </span>
        </div>
        <div className="actions toolbar-actions">
          <button
            type="button"
            disabled={busy}
            data-testid="new-exercise-button"
            onClick={onNewExercise}
          >
            New Exercise
          </button>
          <button
            type="button"
            disabled={busy}
            data-testid="reset-button"
            onClick={() => void handleReset()}
          >
            Reset
          </button>
        </div>
      </div>

      {info && (
        <div className="panel info" role="status">
          {info}
        </div>
      )}

      <WorkbenchContext.Provider value={workbenchValue}>
        <div className="workbench-main">
          <WorkbenchSidebar api={dockApi} />
          <div className="workbench-dock-container">
            <DockviewReact
              className="dockview-theme-light workbench-dock"
              components={components}
              onReady={onReady}
            />
          </div>
        </div>
      </WorkbenchContext.Provider>
    </div>
  );
}

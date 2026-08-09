import { useCallback, useState } from "react";
import {
  ApiError,
  readFile,
  writeFile,
  type CheckResult,
  type Session,
} from "../api/client";
import { FileEditor } from "./FileEditor";
import { FileTree } from "./FileTree";

type Props = {
  session: Session;
  check: CheckResult | null;
  busy: boolean;
  info: string | null;
  onCheck: () => void;
  onReset: () => Promise<void>;
  onNewExercise: () => void;
};

type OpenFile = {
  path: string;
  content: string;
  revision: string;
  baseline: string;
};

export function SessionDashboard({
  session,
  check,
  busy,
  info,
  onCheck,
  onReset,
  onNewExercise,
}: Props) {
  const assignment = session.assignment;
  const [treeKey, setTreeKey] = useState(0);
  const [open, setOpen] = useState<OpenFile | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [assignmentOpen, setAssignmentOpen] = useState(false);

  const dirty = open !== null && open.content !== open.baseline;

  const clearEditor = useCallback(() => {
    setOpen(null);
    setLoadError(null);
    setSaveMsg(null);
    setConflict(null);
  }, []);

  async function openFile(path: string) {
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
  }

  async function save() {
    if (!open || saving) return;
    setSaving(true);
    setConflict(null);
    setSaveMsg(null);
    try {
      const result = await writeFile(open.path, open.content, open.revision);
      setOpen({
        ...open,
        revision: result.revision,
        baseline: open.content,
      });
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
  }

  async function handleReset() {
    const message = dirty
      ? "Reset will discard unsaved editor changes and recreate the exercise repository. Continue?"
      : "Reset will recreate the exercise repository and discard saved exercise work. Continue?";
    if (!window.confirm(message)) return;
    await onReset();
    clearEditor();
    setTreeKey((k) => k + 1);
  }

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

      <details
        className="assignment-details"
        open={assignmentOpen}
        onToggle={(e) => setAssignmentOpen((e.target as HTMLDetailsElement).open)}
      >
        <summary>Assignment</summary>
        <p>{assignment.summary}</p>
        <p className="muted">
          Exercise repo: <span className="mono">{session.repo_path}</span>
        </p>
        {assignment.objectives.length > 0 && (
          <ul>
            {assignment.objectives.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
      </details>

      <div className="workbench-grid">
        <aside className="workbench-files panel">
          <FileTree
            treeKey={treeKey}
            selectedPath={open?.path ?? null}
            onSelectFile={(path) => void openFile(path)}
          />
        </aside>

        <section className="workbench-editor panel">
          <div className="editor-toolbar">
            <div className="editor-title">
              {open ? (
                <>
                  <span className="mono">{open.path}</span>
                  {dirty && <span className="dirty-dot" title="Unsaved changes">●</span>}
                </>
              ) : (
                <span className="muted">Select a file to edit</span>
              )}
            </div>
            <div className="actions">
              <button
                className="primary"
                type="button"
                disabled={!open || !dirty || saving || busy}
                data-testid="save-button"
                onClick={() => void save()}
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
          {loadError && (
            <div className="panel error" role="alert" data-testid="file-load-error">
              {loadError}
            </div>
          )}
          {conflict && (
            <div className="panel error" role="alert" data-testid="save-conflict">
              {conflict} Your editor contents were not overwritten — reload the
              file to pick up external changes, or copy your edits first.
            </div>
          )}
          {saveMsg && !conflict && (
            <div
              className={saveMsg === "Saved" ? "save-toast" : "panel error"}
              role="status"
              data-testid="save-status"
            >
              {saveMsg}
            </div>
          )}
          {open ? (
            <FileEditor
              path={open.path}
              content={open.content}
              onChange={(value) => setOpen({ ...open, content: value })}
              onSave={() => void save()}
            />
          ) : (
            !loadError && (
              <p className="muted editor-placeholder">
                Open a text file from the tree. Git commands still use an external
                terminal until the in-app terminal arrives.
              </p>
            )
          )}
        </section>

        <aside className="workbench-objectives panel">
          <h2>Objectives</h2>
          {!check && <p className="muted">Run Check to evaluate the exercise.</p>}
          {check && (
            <>
              <p>
                {check.passed ? (
                  <span className="badge-pass">All objectives satisfied</span>
                ) : (
                  <span className="badge-fail">Not complete yet</span>
                )}
              </p>
              {check.objectives.map((objective) => (
                <div className="objective" key={objective.id}>
                  <span className={objective.passed ? "badge-pass" : "badge-fail"}>
                    {objective.passed ? "PASS" : "FAIL"}
                  </span>
                  <div>
                    <div>{objective.description}</div>
                    {objective.detail && (
                      <div className="muted">{objective.detail}</div>
                    )}
                  </div>
                </div>
              ))}
            </>
          )}
          <div className="actions">
            <button
              className="primary"
              type="button"
              disabled={busy}
              data-testid="check-button"
              onClick={onCheck}
            >
              {busy ? "Checking…" : "Check"}
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}

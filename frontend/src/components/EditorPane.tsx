import { FileEditor } from "./FileEditor";
import { useWorkbench } from "./WorkbenchContext";

export function EditorPane() {
  const {
    open,
    dirty,
    loadError,
    saveMsg,
    conflict,
    saving,
    busy,
    reloadFromDisk,
    save,
    setEditorContent,
  } = useWorkbench();

  return (
    <section className="workbench-editor panel">
      <div className="editor-toolbar">
        <div className="editor-title">
          {open ? (
            <>
              <span className="mono">{open.path}</span>
              {dirty && (
                <span className="dirty-dot" title="Unsaved changes">
                  ●
                </span>
              )}
            </>
          ) : (
            <span className="muted">Select a file to edit</span>
          )}
        </div>
        <div className="actions">
          {conflict && (
            <button
              type="button"
              data-testid="reload-file-button"
              onClick={reloadFromDisk}
            >
              Reload From Disk
            </button>
          )}
          <button
            className="primary"
            type="button"
            disabled={!open || !dirty || saving || busy}
            data-testid="save-button"
            onClick={save}
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
          {conflict} Your editor contents were not overwritten. Use Reload
          From Disk after copying any edits you want to keep.
        </div>
      )}
      {saveMsg && !conflict && (
        <div
          className={
            saveMsg === "Saved" || saveMsg.startsWith("Reloaded")
              ? "save-toast"
              : "panel error"
          }
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
          onChange={setEditorContent}
          onSave={save}
        />
      ) : (
        !loadError && (
          <p className="muted editor-placeholder">
            Open a text file from the tree. Use the terminal below for Git
            and shell commands.
          </p>
        )
      )}
    </section>
  );
}

import { useWorkbench } from "./WorkbenchContext";

export function ObjectivesPane() {
  const { check, busy, onCheck } = useWorkbench();

  return (
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
  );
}

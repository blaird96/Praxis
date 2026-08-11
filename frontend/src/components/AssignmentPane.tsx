import { Markdown } from "./Markdown";
import { useWorkbench } from "./WorkbenchContext";

export function AssignmentPane() {
  const { session } = useWorkbench();
  const assignment = session.assignment;

  return (
    <div className="workbench-assignment panel">
      <h2>{assignment.title}</h2>
      <Markdown>{assignment.summary}</Markdown>
      <p className="muted">
        Exercise repo: <span className="mono">{session.repo_path}</span>
      </p>
      {assignment.objectives.length > 0 && (
        <ul>
          {assignment.objectives.map((item) => (
            <li key={item}>
              <Markdown inline>{item}</Markdown>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

import type { Catalog, ScenarioInfo } from "../api/client";

type Props = {
  catalog: Catalog;
  startingKey: string | null;
  onStart: (moduleId: string, scenario: ScenarioInfo) => void;
};

export function CatalogView({ catalog, startingKey, onStart }: Props) {
  return (
    <div className="panel" data-testid="catalog">
      <h2>Choose an exercise</h2>
      <p className="muted">
        Start a disposable lab. You will solve it with real tools in the
        exercise environment.
      </p>
      {catalog.modules.map((module) => (
        <section key={module.id} className="catalog-module">
          <h3>{module.title}</h3>
          {module.scenarios.map((scenario) => {
            const key = `${module.id}/${scenario.id}`;
            const starting = startingKey === key;
            return (
              <article key={key} className="catalog-scenario">
                <h4>{scenario.title}</h4>
                <p>{scenario.description}</p>
                {scenario.difficulty && (
                  <p className="muted">Difficulty: {scenario.difficulty}</p>
                )}
                {scenario.concepts && scenario.concepts.length > 0 && (
                  <p className="muted">Concepts: {scenario.concepts.join(", ")}</p>
                )}
                <div className="actions">
                  <button
                    className="primary"
                    type="button"
                    disabled={startingKey !== null}
                    data-testid={`start-${module.id}-${scenario.id}`}
                    onClick={() => onStart(module.id, scenario)}
                  >
                    {starting ? "Starting exercise…" : "Start Exercise"}
                  </button>
                </div>
              </article>
            );
          })}
        </section>
      ))}
    </div>
  );
}

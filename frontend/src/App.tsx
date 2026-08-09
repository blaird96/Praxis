import { useCallback, useEffect, useState } from "react";
import {
  checkSession,
  fetchCatalog,
  fetchSession,
  resetSession,
  startSession,
  type Catalog,
  type ScenarioInfo,
  type Session,
} from "./api/client";
import { bootstrapCapabilityToken, getCapabilityToken } from "./api/token";
import { CatalogView } from "./components/CatalogView";
import { SessionDashboard } from "./components/SessionDashboard";

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [showCatalog, setShowCatalog] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [startingKey, setStartingKey] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    setToken(bootstrapCapabilityToken());
  }, []);

  const load = useCallback(async () => {
    if (!getCapabilityToken()) {
      return;
    }
    setError(null);
    try {
      const [cat, sess] = await Promise.all([
        fetchCatalog(),
        fetchSession(false).catch((err: Error) => {
          if (err.message.toLowerCase().includes("no active")) {
            return null;
          }
          throw err;
        }),
      ]);
      setCatalog(cat);
      setSession(sess);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    if (token) {
      void load();
    }
  }, [token, load]);

  async function onCheck() {
    setBusy(true);
    setError(null);
    try {
      const updated = await checkSession();
      setSession(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onReset() {
    setBusy(true);
    setError(null);
    try {
      const updated = await resetSession();
      setSession(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    } finally {
      setBusy(false);
    }
  }

  async function onStart(moduleId: string, scenario: ScenarioInfo) {
    const key = `${moduleId}/${scenario.id}`;
    setStartingKey(key);
    setError(null);
    setInfo(null);
    try {
      const started = await startSession(moduleId, scenario.id);
      if (started.previous_session_id) {
        setInfo(`Previous session retained: ${started.previous_session_id}`);
      }
      setSession(started);
      setShowCatalog(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStartingKey(null);
    }
  }

  function onNewExercise() {
    setError(null);
    setInfo(null);
    setShowCatalog(true);
    if (!catalog) {
      void fetchCatalog()
        .then(setCatalog)
        .catch((err: Error) =>
          setError(err instanceof Error ? err.message : String(err)),
        );
    }
  }

  const onDashboard = session !== null && !showCatalog;

  return (
    <div className={onDashboard ? "app-shell workbench-shell" : "app-shell"}>
      <header className="app-header">
        <h1>Praxis</h1>
        <span className="muted">Local lab</span>
      </header>

      {!token && (
        <div className="panel error">
          Missing capability token. Launch with <code>praxis app</code> so the
          browser URL includes <code>#token=…</code>.
        </div>
      )}

      {error && (
        <div className="panel error" role="alert">
          {error}
        </div>
      )}

      {onDashboard ? (
        <SessionDashboard
          session={session}
          check={session.check}
          busy={busy || startingKey !== null}
          info={info}
          onCheck={() => void onCheck()}
          onReset={onReset}
          onNewExercise={onNewExercise}
        />
      ) : (
        catalog && (
          <CatalogView
            catalog={catalog}
            startingKey={startingKey}
            onStart={(moduleId, scenario) => void onStart(moduleId, scenario)}
          />
        )
      )}
    </div>
  );
}

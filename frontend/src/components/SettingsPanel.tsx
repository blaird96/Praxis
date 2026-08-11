import { useEffect, useState } from "react";
import {
  ApiError,
  configureCoachKey,
  getCoachStatus,
  removeCoachKey,
  testCoachConnection,
  type CoachStatus,
} from "../api/client";

type Props = {
  onClose: () => void;
  onStatusChange?: (status: CoachStatus) => void;
};

export function SettingsPanel({ onClose, onStatusChange }: Props) {
  const [status, setStatus] = useState<CoachStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageIsError, setMessageIsError] = useState(false);

  async function refreshStatus() {
    try {
      const next = await getCoachStatus();
      setStatus(next);
      onStatusChange?.(next);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void refreshStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSubmitKey(e: React.FormEvent) {
    e.preventDefault();
    if (!apiKey.trim() || saving) return;
    setSaving(true);
    setMessage(null);
    try {
      const next = await configureCoachKey(apiKey.trim());
      // Clear the key from component state immediately after submit; it must
      // never linger in the browser beyond the request itself.
      setApiKey("");
      setStatus(next);
      onStatusChange?.(next);
      setMessageIsError(false);
      setMessage("OpenAI API key saved.");
    } catch (err) {
      setMessageIsError(true);
      setMessage(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setSaving(false);
    }
  }

  async function onRemove() {
    setRemoving(true);
    setMessage(null);
    try {
      const next = await removeCoachKey();
      setStatus(next);
      onStatusChange?.(next);
      setMessageIsError(false);
      setMessage("Stored API key removed.");
    } catch (err) {
      setMessageIsError(true);
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setRemoving(false);
    }
  }

  async function onTest() {
    setTesting(true);
    setMessage(null);
    try {
      const result = await testCoachConnection();
      setMessageIsError(!result.ok);
      setMessage(result.ok ? "Connection OK." : result.detail ?? "Connection failed.");
    } catch (err) {
      setMessageIsError(true);
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setTesting(false);
    }
  }

  const statusLabel = status
    ? status.configured
      ? `OpenAI API: Configured${status.source ? ` (${status.source})` : ""}`
      : "OpenAI API: Not configured"
    : "OpenAI API: Loading…";

  return (
    <div
      className="settings-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
      data-testid="settings-panel"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="settings-dialog panel">
        <div className="editor-toolbar">
          <h2>Settings</h2>
          <button type="button" onClick={onClose} data-testid="settings-close">
            Close
          </button>
        </div>

        <section className="settings-section">
          <h3>OpenAI Coaching</h3>
          {loadError && <p className="error">{loadError}</p>}
          <p data-testid="coach-status-label">
            <strong>{statusLabel}</strong>
          </p>
          <p className="muted">
            When enabled, the current exercise's assignment text and your chat
            messages are sent to OpenAI's API to power the coaching assistant.
            We recommend creating a dedicated OpenAI project/API key for
            Praxis rather than reusing a personal, general-purpose key.
          </p>

          <form onSubmit={(e) => void onSubmitKey(e)} className="settings-form">
            <label htmlFor="coach-api-key">
              {status?.configured ? "Replace API key" : "Configure API key"}
            </label>
            <input
              id="coach-api-key"
              type="password"
              autoComplete="off"
              placeholder="sk-..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              data-testid="coach-api-key-input"
            />
            <div className="actions">
              <button
                type="submit"
                className="primary"
                disabled={!apiKey.trim() || saving}
                data-testid="coach-save-key"
              >
                {saving ? "Saving…" : status?.configured ? "Replace" : "Configure"}
              </button>
              {status?.configured && status.source === "keyring" && (
                <button
                  type="button"
                  onClick={() => void onRemove()}
                  disabled={removing}
                  data-testid="coach-remove-key"
                >
                  {removing ? "Removing…" : "Remove"}
                </button>
              )}
              <button
                type="button"
                onClick={() => void onTest()}
                disabled={testing}
                data-testid="coach-test-connection"
              >
                {testing ? "Testing…" : "Test Connection"}
              </button>
            </div>
          </form>

          {status?.configured && status.source === "env" && (
            <p className="muted">
              Configured via the <code>PRAXIS_OPENAI_API_KEY</code> environment
              variable. Remove it from this app's environment to unset it.
            </p>
          )}

          {message && (
            <div
              className={messageIsError ? "error" : "save-toast"}
              role="status"
              data-testid="coach-settings-message"
            >
              {message}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

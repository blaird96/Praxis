import { useEffect, useState } from "react";
import type { DockviewApi } from "dockview-react";
import {
  addPane,
  buildDefaultLayout,
  LAYOUT_STORAGE_KEY,
  PANE_ORDER,
  PANE_TITLES,
  type PaneId,
} from "./workbenchLayout";

type Props = {
  api: DockviewApi | null;
};

function emptyVisibility(): Record<PaneId, boolean> {
  return Object.fromEntries(PANE_ORDER.map((id) => [id, false])) as Record<
    PaneId,
    boolean
  >;
}

/**
 * A slim always-visible rail with one toggle button per pane, plus a Reset
 * Layout action. Stays in sync with panes closed directly via Dockview's own
 * tab-close UI (not just this sidebar's own toggles) by re-reading
 * `api.getPanel()` on every layout change.
 */
export function WorkbenchSidebar({ api }: Props) {
  const [visible, setVisible] = useState<Record<PaneId, boolean>>(
    emptyVisibility,
  );

  useEffect(() => {
    if (!api) {
      setVisible(emptyVisibility());
      return;
    }

    const sync = () => {
      setVisible(
        Object.fromEntries(
          PANE_ORDER.map((id) => [id, Boolean(api.getPanel(id))]),
        ) as Record<PaneId, boolean>,
      );
    };
    sync();
    const disposable = api.onDidLayoutChange(sync);
    return () => disposable.dispose();
  }, [api]);

  function toggle(id: PaneId) {
    if (!api) return;
    const panel = api.getPanel(id);
    if (panel) {
      api.removePanel(panel);
    } else {
      addPane(api, id);
    }
  }

  function resetLayout() {
    if (!api) return;
    try {
      window.localStorage.removeItem(LAYOUT_STORAGE_KEY);
    } catch {
      // localStorage unavailable - the rebuilt layout just won't persist.
    }
    buildDefaultLayout(api);
  }

  return (
    <nav className="workbench-sidebar" aria-label="Workbench panes">
      {PANE_ORDER.map((id) => (
        <button
          key={id}
          type="button"
          className={
            visible[id]
              ? "sidebar-pane-toggle active"
              : "sidebar-pane-toggle"
          }
          data-testid={`sidebar-toggle-${id}`}
          aria-pressed={visible[id]}
          disabled={!api}
          title={
            visible[id] ? `Hide ${PANE_TITLES[id]}` : `Show ${PANE_TITLES[id]}`
          }
          onClick={() => toggle(id)}
        >
          {PANE_TITLES[id]}
        </button>
      ))}
      <button
        type="button"
        className="sidebar-reset-button"
        data-testid="sidebar-reset-layout"
        disabled={!api}
        title="Reset Layout"
        onClick={resetLayout}
      >
        Reset Layout
      </button>
    </nav>
  );
}

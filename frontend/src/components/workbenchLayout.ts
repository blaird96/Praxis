import type { AddPanelOptions, DockviewApi } from "dockview-react";

export type PaneId =
  | "assignment"
  | "files"
  | "editor"
  | "objectives"
  | "coach"
  | "terminal";

export const PANE_ORDER: PaneId[] = [
  "assignment",
  "files",
  "editor",
  "objectives",
  "coach",
  "terminal",
];

export const PANE_TITLES: Record<PaneId, string> = {
  assignment: "Assignment",
  files: "Files",
  editor: "Editor",
  objectives: "Objectives",
  coach: "Coach",
  terminal: "Terminal",
};

export const LAYOUT_STORAGE_KEY = "praxis-workbench-layout-v1";

type Direction = "left" | "right" | "above" | "below";

type Candidate =
  | { kind: "panel"; referencePanel: PaneId; direction: Direction }
  | { kind: "absolute"; direction: Direction };

/**
 * Where to dock a pane, in priority order, when it's re-shown from the
 * sidebar after being hidden. `assignment`/`terminal` always re-attach as a
 * full-width row; the middle-row panes prefer to sit beside whichever of
 * their usual neighbours still exists.
 */
const SHOW_CANDIDATES: Record<PaneId, Candidate[]> = {
  assignment: [{ kind: "absolute", direction: "above" }],
  terminal: [{ kind: "absolute", direction: "below" }],
  files: [
    { kind: "panel", referencePanel: "editor", direction: "left" },
    { kind: "panel", referencePanel: "objectives", direction: "left" },
    { kind: "panel", referencePanel: "coach", direction: "left" },
  ],
  editor: [
    { kind: "panel", referencePanel: "files", direction: "right" },
    { kind: "panel", referencePanel: "objectives", direction: "left" },
    { kind: "panel", referencePanel: "coach", direction: "left" },
  ],
  objectives: [
    { kind: "panel", referencePanel: "editor", direction: "right" },
    { kind: "panel", referencePanel: "coach", direction: "left" },
    { kind: "panel", referencePanel: "files", direction: "right" },
  ],
  coach: [
    { kind: "panel", referencePanel: "objectives", direction: "right" },
    { kind: "panel", referencePanel: "editor", direction: "right" },
    { kind: "panel", referencePanel: "files", direction: "right" },
  ],
};

/**
 * Add a pane back to the layout at a sensible default position. No-op if
 * it's already present. Used both by the sidebar's show/hide toggle and (via
 * `buildDefaultLayout`) as a fallback path.
 */
export function addPane(api: DockviewApi, id: PaneId): void {
  if (api.getPanel(id)) return;

  const base = {
    id,
    component: id,
    title: PANE_TITLES[id],
  };

  if (api.panels.length === 0) {
    api.addPanel(base);
    return;
  }

  for (const candidate of SHOW_CANDIDATES[id]) {
    if (candidate.kind === "absolute") {
      api.addPanel({
        ...base,
        position: { direction: candidate.direction },
      } as AddPanelOptions);
      return;
    }
    if (api.getPanel(candidate.referencePanel)) {
      api.addPanel({
        ...base,
        position: {
          direction: candidate.direction,
          referencePanel: candidate.referencePanel,
        },
      } as AddPanelOptions);
      return;
    }
  }

  // No usual neighbour is present (e.g. every other middle-row pane is
  // hidden) - dock beside whatever panel happens to exist.
  api.addPanel({
    ...base,
    position: { direction: "right", referencePanel: api.panels[0].id },
  } as AddPanelOptions);
}

/**
 * Build the default arrangement from an empty layout: Assignment as a
 * full-width row on top, Files/Editor/Objectives/Coach as a middle row, and
 * Terminal as a full-width row below.
 */
export function buildDefaultLayout(api: DockviewApi): void {
  api.clear();
  api.addPanel({
    id: "files",
    component: "files",
    title: PANE_TITLES.files,
    initialWidth: 260,
  });
  api.addPanel({
    id: "editor",
    component: "editor",
    title: PANE_TITLES.editor,
    initialWidth: 640,
    position: { direction: "right", referencePanel: "files" },
  });
  api.addPanel({
    id: "objectives",
    component: "objectives",
    title: PANE_TITLES.objectives,
    initialWidth: 320,
    position: { direction: "right", referencePanel: "editor" },
  });
  api.addPanel({
    id: "coach",
    component: "coach",
    title: PANE_TITLES.coach,
    initialWidth: 360,
    position: { direction: "right", referencePanel: "objectives" },
  });
  api.addPanel({
    id: "terminal",
    component: "terminal",
    title: PANE_TITLES.terminal,
    initialHeight: 260,
    position: { direction: "below" },
  });
  api.addPanel({
    id: "assignment",
    component: "assignment",
    title: PANE_TITLES.assignment,
    initialHeight: 180,
    position: { direction: "above" },
  });
}

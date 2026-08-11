import { createContext, useContext } from "react";
import type { CheckResult, Session } from "../api/client";

export type OpenFile = {
  path: string;
  content: string;
  revision: string;
  baseline: string;
};

/**
 * Everything the docked panels need. Dockview renders panel components
 * outside normal parent-render prop drilling, so all reactive session /
 * editor / check state and handlers live here instead of in panel `params`
 * (which are small, static values that get serialized into the saved layout).
 */
export type WorkbenchState = {
  session: Session;
  check: CheckResult | null;
  busy: boolean;
  /** Bumped on Reset so FileTree remounts its fetched state. */
  treeKey: number;
  /** Bumped on Reset to force a fresh terminal ticket + PTY. */
  terminalKey: number;
  open: OpenFile | null;
  dirty: boolean;
  loadError: string | null;
  saveMsg: string | null;
  conflict: string | null;
  saving: boolean;
  onOpenSettings: () => void;
  onCheck: () => void;
  openFile: (path: string) => void;
  reloadFromDisk: () => void;
  save: () => void;
  setEditorContent: (value: string) => void;
};

export const WorkbenchContext = createContext<WorkbenchState | null>(null);

export function useWorkbench(): WorkbenchState {
  const ctx = useContext(WorkbenchContext);
  if (!ctx) {
    throw new Error("useWorkbench must be used within a WorkbenchContext.Provider");
  }
  return ctx;
}

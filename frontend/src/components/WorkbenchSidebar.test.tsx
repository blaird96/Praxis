import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { DockviewApi } from "dockview-react";
import { WorkbenchSidebar } from "./WorkbenchSidebar";
import { buildDefaultLayout, PANE_ORDER } from "./workbenchLayout";

type FakePanel = { id: string; component: string; title?: string };

/** Minimal fake DockviewApi covering only what WorkbenchSidebar/workbenchLayout use. */
function createFakeApi(): DockviewApi {
  const panels = new Map<string, FakePanel>();
  const listeners = new Set<() => void>();
  const fire = () => listeners.forEach((listener) => listener());

  const api = {
    get panels() {
      return Array.from(panels.values());
    },
    getPanel(id: string) {
      return panels.get(id);
    },
    addPanel(options: FakePanel) {
      const panel: FakePanel = {
        id: options.id,
        component: options.component,
        title: options.title,
      };
      panels.set(options.id, panel);
      fire();
      return panel;
    },
    removePanel(panel: FakePanel) {
      panels.delete(panel.id);
      fire();
    },
    clear() {
      panels.clear();
      fire();
    },
    onDidLayoutChange(listener: () => void) {
      listeners.add(listener);
      return { dispose: () => listeners.delete(listener) };
    },
  };

  return api as unknown as DockviewApi;
}

describe("WorkbenchSidebar", () => {
  it("toggling a button hides then re-shows the pane via the Dockview API", async () => {
    const user = userEvent.setup();
    const api = createFakeApi();
    buildDefaultLayout(api);

    render(<WorkbenchSidebar api={api} />);

    const coachToggle = await screen.findByTestId("sidebar-toggle-coach");
    expect(coachToggle).toHaveAttribute("aria-pressed", "true");

    await user.click(coachToggle);
    expect(api.getPanel("coach")).toBeUndefined();
    await waitFor(() =>
      expect(coachToggle).toHaveAttribute("aria-pressed", "false"),
    );

    await user.click(coachToggle);
    expect(api.getPanel("coach")).toBeDefined();
    await waitFor(() =>
      expect(coachToggle).toHaveAttribute("aria-pressed", "true"),
    );
  });

  it("stays in sync when a pane is closed directly through the Dockview API", async () => {
    const api = createFakeApi();
    buildDefaultLayout(api);

    render(<WorkbenchSidebar api={api} />);

    const filesToggle = await screen.findByTestId("sidebar-toggle-files");
    expect(filesToggle).toHaveAttribute("aria-pressed", "true");

    // Simulate the pane being closed via Dockview's own tab-close UI rather
    // than the sidebar button.
    const panel = api.getPanel("files");
    expect(panel).toBeDefined();
    if (panel) api.removePanel(panel);

    await waitFor(() =>
      expect(filesToggle).toHaveAttribute("aria-pressed", "false"),
    );
  });

  it("Reset Layout restores every default pane", async () => {
    const user = userEvent.setup();
    const api = createFakeApi();
    buildDefaultLayout(api);
    const panel = api.getPanel("coach");
    if (panel) api.removePanel(panel);

    render(<WorkbenchSidebar api={api} />);
    await waitFor(() =>
      expect(screen.getByTestId("sidebar-toggle-coach")).toHaveAttribute(
        "aria-pressed",
        "false",
      ),
    );

    await user.click(screen.getByTestId("sidebar-reset-layout"));

    await waitFor(() => {
      for (const id of PANE_ORDER) {
        expect(api.getPanel(id)).toBeDefined();
      }
    });
  });
});

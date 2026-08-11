import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { SettingsPanel } from "./SettingsPanel";

describe("SettingsPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows Not configured status and lets the user configure a key", async () => {
    vi.spyOn(client, "getCoachStatus").mockResolvedValue({
      configured: false,
      source: null,
      model: "gpt-4o-mini",
    });
    const configure = vi.spyOn(client, "configureCoachKey").mockResolvedValue({
      configured: true,
      source: "keyring",
      model: "gpt-4o-mini",
    });

    const user = userEvent.setup();
    render(<SettingsPanel onClose={vi.fn()} />);

    expect(await screen.findByTestId("coach-status-label")).toHaveTextContent(
      "Not configured",
    );

    const input = screen.getByTestId("coach-api-key-input");
    await user.type(input, "sk-test-key");
    await user.click(screen.getByTestId("coach-save-key"));

    await waitFor(() => expect(configure).toHaveBeenCalledWith("sk-test-key"));
    expect(await screen.findByTestId("coach-status-label")).toHaveTextContent(
      "Configured (keyring)",
    );
    // The key must never linger in the input/component state after submit.
    expect(input).toHaveValue("");
    expect(screen.getByTestId("coach-remove-key")).toBeInTheDocument();
  });

  it("removes a stored key", async () => {
    vi.spyOn(client, "getCoachStatus").mockResolvedValue({
      configured: true,
      source: "keyring",
      model: "gpt-4o-mini",
    });
    const remove = vi.spyOn(client, "removeCoachKey").mockResolvedValue({
      configured: false,
      source: null,
      model: "gpt-4o-mini",
    });

    const user = userEvent.setup();
    render(<SettingsPanel onClose={vi.fn()} />);

    await screen.findByTestId("coach-remove-key");
    await user.click(screen.getByTestId("coach-remove-key"));

    await waitFor(() => expect(remove).toHaveBeenCalled());
    expect(await screen.findByTestId("coach-status-label")).toHaveTextContent(
      "Not configured",
    );
  });

  it("hides the Remove button for env-sourced keys and runs a connection test", async () => {
    vi.spyOn(client, "getCoachStatus").mockResolvedValue({
      configured: true,
      source: "env",
      model: "gpt-4o-mini",
    });
    const test = vi.spyOn(client, "testCoachConnection").mockResolvedValue({
      ok: true,
      detail: null,
    });

    const user = userEvent.setup();
    render(<SettingsPanel onClose={vi.fn()} />);

    await screen.findByTestId("coach-status-label");
    expect(screen.queryByTestId("coach-remove-key")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("coach-test-connection"));
    await waitFor(() => expect(test).toHaveBeenCalled());
    expect(await screen.findByTestId("coach-settings-message")).toHaveTextContent(
      "Connection OK.",
    );
  });

  it("calls onClose when the Close button is clicked", async () => {
    vi.spyOn(client, "getCoachStatus").mockResolvedValue({
      configured: false,
      source: null,
      model: "gpt-4o-mini",
    });
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<SettingsPanel onClose={onClose} />);

    await screen.findByTestId("coach-status-label");
    await user.click(screen.getByTestId("settings-close"));
    expect(onClose).toHaveBeenCalled();
  });
});

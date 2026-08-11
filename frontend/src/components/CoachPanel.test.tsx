import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { CoachPanel } from "./CoachPanel";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;

  url: string;
  readyState = MockWebSocket.OPEN;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.(new Event("open")));
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close"));
  }
}

describe("CoachPanel", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows a Configure CTA when OpenAI is not configured", async () => {
    const onOpenSettings = vi.fn();
    vi.spyOn(client, "getCoachStatus").mockResolvedValue({
      configured: false,
      source: null,
      model: "gpt-4o-mini",
    });

    render(<CoachPanel sessionId="sess1" onOpenSettings={onOpenSettings} />);

    const cta = await screen.findByTestId("coach-open-settings");
    expect(MockWebSocket.instances.length).toBe(0);

    const user = userEvent.setup();
    await user.click(cta);
    expect(onOpenSettings).toHaveBeenCalled();
  });

  it("connects with a ticket and streams deltas into an assistant bubble", async () => {
    vi.spyOn(client, "getCoachStatus").mockResolvedValue({
      configured: true,
      source: "keyring",
      model: "gpt-4o-mini",
    });
    vi.spyOn(client, "issueCoachTicket").mockResolvedValue({
      ticket: "ticket-xyz",
      expires_in: 30,
      session_id: "sess1",
    });

    const user = userEvent.setup();
    render(<CoachPanel sessionId="sess1" onOpenSettings={vi.fn()} />);

    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    expect(MockWebSocket.instances[0].url).toContain("/ws/coach?ticket=ticket-xyz");
    expect(await screen.findByTestId("coach-connection-status")).toHaveTextContent(
      "Connected",
    );

    const input = screen.getByTestId("coach-input");
    await user.type(input, "How do I resolve this conflict?");
    await user.click(screen.getByTestId("coach-send"));

    const ws = MockWebSocket.instances[0];
    expect(ws.sent.some((s) => s.includes("How do I resolve this conflict?"))).toBe(
      true,
    );

    act(() => {
      ws.onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({ type: "delta", content: "Try " }),
        }),
      );
      ws.onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({ type: "delta", content: "checking git status." }),
        }),
      );
      ws.onmessage?.(
        new MessageEvent("message", { data: JSON.stringify({ type: "done" }) }),
      );
    });

    expect(
      await screen.findByText("Try checking git status."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("coach-send")).toBeDisabled();
  });

  it("shows an error bubble when the server sends an error message", async () => {
    vi.spyOn(client, "getCoachStatus").mockResolvedValue({
      configured: true,
      source: "env",
      model: "gpt-4o-mini",
    });
    vi.spyOn(client, "issueCoachTicket").mockResolvedValue({
      ticket: "ticket-xyz",
      expires_in: 30,
      session_id: "sess1",
    });

    const user = userEvent.setup();
    render(<CoachPanel sessionId="sess1" onOpenSettings={vi.fn()} />);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));

    const input = screen.getByTestId("coach-input");
    await user.type(input, "hint please");
    await user.click(screen.getByTestId("coach-send"));

    const ws = MockWebSocket.instances[0];
    act(() => {
      ws.onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({ type: "error", message: "OpenAI request failed" }),
        }),
      );
    });

    expect(await screen.findByText(/OpenAI request failed/)).toBeInTheDocument();
  });
});

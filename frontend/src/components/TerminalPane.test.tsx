import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { TerminalPane } from "./TerminalPane";

const writeMock = vi.fn();
const disposeMock = vi.fn();
const loadAddonMock = vi.fn();
const openMock = vi.fn();
const onDataHandlers: Array<(data: string) => void> = [];

vi.mock("@xterm/xterm", () => ({
  Terminal: vi.fn(),
}));

vi.mock("@xterm/addon-fit", () => ({
  FitAddon: vi.fn().mockImplementation(() => ({
    fit: vi.fn(),
  })),
}));

vi.mock("@xterm/xterm/css/xterm.css", () => ({}));

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;

  url: string;
  readyState = MockWebSocket.OPEN;
  binaryType = "arraybuffer";
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

describe("TerminalPane", () => {
  beforeEach(async () => {
    onDataHandlers.length = 0;
    MockWebSocket.instances = [];
    writeMock.mockReset();
    disposeMock.mockReset();
    loadAddonMock.mockReset();
    openMock.mockReset();

    const xterm = await import("@xterm/xterm");
    vi.mocked(xterm.Terminal).mockImplementation(
      () =>
        ({
          cols: 80,
          rows: 24,
          loadAddon: loadAddonMock,
          open: openMock,
          write: writeMock,
          writeln: vi.fn(),
          onData: (cb: (data: string) => void) => {
            onDataHandlers.push(cb);
          },
          dispose: disposeMock,
        }) as unknown as InstanceType<typeof xterm.Terminal>,
    );

    vi.stubGlobal("WebSocket", MockWebSocket);
    vi.spyOn(client, "fetchTerminalTicket").mockResolvedValue({
      ticket: "ticket-abc",
      expires_in: 30,
      session_id: "sess1",
    });
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
        unobserve() {}
      },
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("requests a ticket and connects the WebSocket with it", async () => {
    render(<TerminalPane sessionId="sess1" restartToken={0} />);
    await waitFor(() => expect(client.fetchTerminalTicket).toHaveBeenCalled());
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    expect(MockWebSocket.instances[0].url).toContain(
      "/ws/terminal?ticket=ticket-abc",
    );
    expect(await screen.findByTestId("terminal-status")).toHaveTextContent(
      "Connected",
    );
    expect(
      MockWebSocket.instances[0].sent.some((s) => s.includes('"resize"')),
    ).toBe(true);
  });

  it("sends input and writes binary output to xterm", async () => {
    render(<TerminalPane sessionId="sess1" restartToken={0} />);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    const ws = MockWebSocket.instances[0];
    await waitFor(() => expect(onDataHandlers.length).toBeGreaterThan(0));
    act(() => {
      onDataHandlers[0]("git status\r");
    });
    expect(ws.sent.some((s) => s.includes("git status"))).toBe(true);

    act(() => {
      ws.onmessage?.(
        new MessageEvent("message", {
          data: new TextEncoder().encode("On branch main\r\n").buffer,
        }),
      );
    });
    expect(writeMock).toHaveBeenCalled();
  });

  it("shows exit state and Restart Terminal creates a new connection", async () => {
    const user = userEvent.setup();
    render(<TerminalPane sessionId="sess1" restartToken={0} />);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    act(() => {
      MockWebSocket.instances[0].onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({ type: "exit", code: 0 }),
        }),
      );
    });
    expect(await screen.findByTestId("terminal-status")).toHaveTextContent(
      /exited/i,
    );

    await user.click(screen.getByTestId("restart-terminal-button"));
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(2));
    expect(client.fetchTerminalTicket).toHaveBeenCalledTimes(2);
  });

  it("closes the WebSocket on unmount", async () => {
    const { unmount } = render(
      <TerminalPane sessionId="sess1" restartToken={0} />,
    );
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    const ws = MockWebSocket.instances[0];
    const closeSpy = vi.spyOn(ws, "close");
    unmount();
    expect(closeSpy).toHaveBeenCalled();
    expect(disposeMock).toHaveBeenCalled();
  });
});

import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { fetchTerminalTicket, terminalWebSocketUrl } from "../api/client";

type Props = {
  sessionId: string;
  /** Bump to force a fresh ticket + PTY (reset / restart). */
  restartToken: number;
};

type Status = "connecting" | "connected" | "exited" | "error" | "disconnected";

export function TerminalPane({ sessionId, restartToken }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<Status>("connecting");
  const [statusDetail, setStatusDetail] = useState<string | null>(null);
  const [localRestart, setLocalRestart] = useState(0);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let cancelled = false;
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      theme: {
        background: "#1c1917",
        foreground: "#f5f5f4",
        cursor: "#fafaf9",
      },
      convertEol: true,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host);
    fit.fit();
    termRef.current = term;
    fitRef.current = fit;

    const decoder = new TextDecoder("utf-8", { fatal: false });
    let socket: WebSocket | null = null;

    async function connect() {
      setStatus("connecting");
      setStatusDetail(null);
      try {
        const ticket = await fetchTerminalTicket();
        if (cancelled) return;
        const url = terminalWebSocketUrl(ticket.ticket);
        socket = new WebSocket(url);
        socket.binaryType = "arraybuffer";
        wsRef.current = socket;

        socket.onopen = () => {
          if (cancelled) return;
          setStatus("connected");
          fit.fit();
          const dims = { cols: term.cols, rows: term.rows };
          socket?.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
        };

        socket.onmessage = (event) => {
          if (typeof event.data === "string") {
            try {
              const msg = JSON.parse(event.data) as {
                type?: string;
                code?: number;
                message?: string;
              };
              if (msg.type === "exit") {
                setStatus("exited");
                setStatusDetail(
                  `Shell exited${msg.code != null ? ` (code ${msg.code})` : ""}`,
                );
              } else if (msg.type === "error" && msg.message) {
                setStatus("error");
                setStatusDetail(msg.message);
                term.writeln(`\r\n\x1b[31m${msg.message}\x1b[0m`);
              }
            } catch {
              /* ignore non-JSON text */
            }
            return;
          }
          const bytes =
            event.data instanceof ArrayBuffer
              ? new Uint8Array(event.data)
              : new Uint8Array(event.data as ArrayBuffer);
          term.write(decoder.decode(bytes, { stream: true }));
        };

        socket.onerror = () => {
          setStatus("error");
          setStatusDetail("Terminal connection error");
        };

        socket.onclose = () => {
          if (!cancelled) {
            setStatus((prev) => (prev === "exited" || prev === "error" ? prev : "disconnected"));
          }
          wsRef.current = null;
        };

        term.onData((data) => {
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "input", data }));
          }
        });
      } catch (err) {
        if (!cancelled) {
          setStatus("error");
          setStatusDetail(err instanceof Error ? err.message : String(err));
        }
      }
    }

    void connect();

    const onResize = () => {
      fit.fit();
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(
          JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }),
        );
      }
    };
    const observer = new ResizeObserver(onResize);
    observer.observe(host);
    window.addEventListener("resize", onResize);

    return () => {
      cancelled = true;
      observer.disconnect();
      window.removeEventListener("resize", onResize);
      if (socket) {
        socket.close();
      }
      wsRef.current = null;
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
    };
  }, [sessionId, restartToken, localRestart]);

  return (
    <div className="terminal-pane panel" data-testid="terminal-pane">
      <div className="terminal-toolbar">
        <h2>Terminal</h2>
        <span className="muted" data-testid="terminal-status">
          {status === "connecting" && "Connecting…"}
          {status === "connected" && "Connected"}
          {status === "exited" && (statusDetail ?? "Exited")}
          {status === "disconnected" && "Disconnected"}
          {status === "error" && (statusDetail ?? "Error")}
        </span>
        <button
          type="button"
          data-testid="restart-terminal-button"
          onClick={() => setLocalRestart((n) => n + 1)}
        >
          Restart Terminal
        </button>
      </div>
      <div className="terminal-host" ref={hostRef} data-testid="terminal-host" />
    </div>
  );
}

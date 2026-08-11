import { useEffect, useRef, useState } from "react";
import { coachWebSocketUrl, getCoachStatus, issueCoachTicket } from "../api/client";
import { Markdown } from "./Markdown";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type Props = {
  sessionId: string;
  onOpenSettings: () => void;
};

type Status = "checking" | "unconfigured" | "connecting" | "connected" | "error";

export function CoachPanel({ sessionId, onOpenSettings }: Props) {
  const [status, setStatus] = useState<Status>("checking");
  const [statusDetail, setStatusDetail] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const streamingRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;

    async function connect() {
      setStatus("connecting");
      setStatusDetail(null);
      try {
        const coachStatus = await getCoachStatus();
        if (cancelled) return;
        if (!coachStatus.configured) {
          setStatus("unconfigured");
          return;
        }
        const ticket = await issueCoachTicket();
        if (cancelled) return;
        socket = new WebSocket(coachWebSocketUrl(ticket.ticket));
        wsRef.current = socket;

        socket.onopen = () => {
          if (!cancelled) setStatus("connected");
        };

        socket.onmessage = (event) => {
          if (typeof event.data !== "string") return;
          let msg: { type?: string; content?: string; message?: string };
          try {
            msg = JSON.parse(event.data);
          } catch {
            return;
          }
          if (msg.type === "delta" && typeof msg.content === "string") {
            setMessages((prev) => {
              if (streamingRef.current && prev.length > 0) {
                const next = [...prev];
                const last = next[next.length - 1];
                next[next.length - 1] = {
                  ...last,
                  content: last.content + msg.content,
                };
                return next;
              }
              streamingRef.current = true;
              return [...prev, { role: "assistant", content: msg.content ?? "" }];
            });
          } else if (msg.type === "done") {
            streamingRef.current = false;
            setSending(false);
          } else if (msg.type === "error") {
            streamingRef.current = false;
            setSending(false);
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: `⚠️ ${msg.message ?? "Coach error"}` },
            ]);
          }
        };

        socket.onerror = () => {
          if (!cancelled) {
            setStatus("error");
            setStatusDetail("Coach connection error");
          }
        };

        socket.onclose = () => {
          wsRef.current = null;
          if (!cancelled) {
            setStatus((prev) => (prev === "error" ? prev : "error"));
          }
        };
      } catch (err) {
        if (!cancelled) {
          setStatus("error");
          setStatusDetail(err instanceof Error ? err.message : String(err));
        }
      }
    }

    void connect();

    return () => {
      cancelled = true;
      socket?.close();
      wsRef.current = null;
    };
  }, [sessionId]);

  function send() {
    const trimmed = input.trim();
    const socket = wsRef.current;
    if (!trimmed || !socket || socket.readyState !== WebSocket.OPEN || sending) {
      return;
    }
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    setSending(true);
    streamingRef.current = false;
    socket.send(JSON.stringify({ type: "message", content: trimmed, history }));
  }

  return (
    <div className="workbench-coach panel" data-testid="coach-panel">
      <div className="editor-toolbar">
        <h2>Coach</h2>
        <span className="muted" data-testid="coach-connection-status">
          {status === "checking" && "Checking…"}
          {status === "connecting" && "Connecting…"}
          {status === "connected" && "Connected"}
          {status === "error" && (statusDetail ?? "Disconnected")}
        </span>
      </div>

      {status === "unconfigured" ? (
        <div className="coach-empty-state">
          <p className="muted">
            Configure OpenAI to get AI coaching for this exercise.
          </p>
          <button
            type="button"
            className="primary"
            onClick={onOpenSettings}
            data-testid="coach-open-settings"
          >
            Configure OpenAI in Settings
          </button>
        </div>
      ) : (
        <>
          <div className="coach-messages" data-testid="coach-messages">
            {messages.length === 0 && (
              <p className="muted">
                Ask the coach for a hint about this exercise's objectives.
              </p>
            )}
            {messages.map((message, idx) => (
              <div
                key={idx}
                className={`coach-message coach-message-${message.role}`}
              >
                {message.role === "assistant" ? (
                  <Markdown>{message.content || "…"}</Markdown>
                ) : (
                  <p>{message.content}</p>
                )}
              </div>
            ))}
          </div>
          <form
            className="coach-input-row"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <input
              type="text"
              placeholder="Ask the coach for a hint…"
              value={input}
              disabled={status !== "connected" || sending}
              onChange={(e) => setInput(e.target.value)}
              data-testid="coach-input"
            />
            <button
              type="submit"
              className="primary"
              disabled={status !== "connected" || sending || !input.trim()}
              data-testid="coach-send"
            >
              {sending ? "…" : "Send"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}

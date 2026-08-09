import { authHeaders } from "./token";

export type Objective = {
  id: string;
  description: string;
  passed: boolean;
  detail: string | null;
};

export type CheckResult = {
  passed: boolean;
  objectives: Objective[];
};

export type Assignment = {
  title: string;
  summary: string;
  objectives: string[];
};

export type Session = {
  session_id: string;
  module: string;
  scenario: string;
  status: string;
  workspace_path: string;
  repo_path: string;
  assignment: Assignment;
  check: CheckResult | null;
  previous_session_id: string | null;
};

export type ScenarioInfo = {
  id: string;
  title: string;
  description: string;
  difficulty: string | null;
  concepts?: string[];
};

export type Catalog = {
  modules: Array<{
    id: string;
    title: string;
    scenarios: ScenarioInfo[];
  }>;
};

export type DirEntry = {
  name: string;
  path: string;
  kind: "file" | "directory" | "symlink";
};

export type FileList = {
  path: string;
  entries: DirEntry[];
};

export type FileContent = {
  path: string;
  content: string;
  revision: string;
  size: number;
};

export type FileWriteResult = {
  path: string;
  revision: string;
  size: number;
};

export class ApiError extends Error {
  status: number;
  code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    let code: string | null = null;
    try {
      const body = (await response.json()) as { detail?: string; code?: string };
      if (body.detail) detail = body.detail;
      if (body.code) code = body.code;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, response.status, code);
  }
  return (await response.json()) as T;
}

export function fetchCatalog(): Promise<Catalog> {
  return api<Catalog>("/api/catalog");
}

export function fetchSession(includeCheck = false): Promise<Session> {
  const q = includeCheck ? "?include_check=true" : "";
  return api<Session>(`/api/session${q}`);
}

export function checkSession(): Promise<Session> {
  return api<Session>("/api/session/check", { method: "POST" });
}

export function startSession(module: string, scenario: string): Promise<Session> {
  return api<Session>("/api/session/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ module, scenario }),
  });
}

export function resetSession(): Promise<Session> {
  return api<Session>("/api/session/reset", { method: "POST" });
}

export function listFiles(path = "."): Promise<FileList> {
  const q = new URLSearchParams({ path });
  return api<FileList>(`/api/session/files?${q}`);
}

export function readFile(path: string): Promise<FileContent> {
  const q = new URLSearchParams({ path });
  return api<FileContent>(`/api/session/file?${q}`);
}

export function writeFile(
  path: string,
  content: string,
  expectedRevision: string,
): Promise<FileWriteResult> {
  return api<FileWriteResult>("/api/session/file", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path,
      content,
      expected_revision: expectedRevision,
    }),
  });
}

export type TerminalTicket = {
  ticket: string;
  expires_in: number;
  session_id: string;
};

export function fetchTerminalTicket(): Promise<TerminalTicket> {
  return api<TerminalTicket>("/api/terminal/ticket", { method: "POST" });
}

/** Build the terminal WebSocket URL for a one-shot ticket (never put the capability token here). */
export function terminalWebSocketUrl(ticket: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/terminal?ticket=${encodeURIComponent(ticket)}`;
}

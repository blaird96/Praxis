/**
 * Capability token: read once from the URL fragment, then held in memory and
 * mirrored to `sessionStorage` (tab-scoped; cleared when the tab closes, never
 * sent to a server, never in localStorage/cookies/query string) so a page
 * reload doesn't strand the app with no way to re-authenticate.
 */

const STORAGE_KEY = "praxis_capability_token";

let memoryToken: string | null = null;
let bootstrapped = false;

function parseTokenFromFragment(hash: string): string | null {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!raw) return null;
  const params = new URLSearchParams(raw);
  return params.get("token");
}

function readStoredToken(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    // Storage disabled (e.g. private browsing) - fall back to memory-only.
    return null;
  }
}

function storeToken(token: string): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, token);
  } catch {
    /* ignore storage errors; token still works for this page's lifetime */
  }
}

/**
 * Read `#token=` once and strip it from the visible URL. Falls back to a
 * token already saved in `sessionStorage` from an earlier bootstrap in this
 * tab (e.g. after a reload), so the fragment only ever needs to be visited
 * once per tab.
 */
export function bootstrapCapabilityToken(): string | null {
  if (bootstrapped) {
    return memoryToken;
  }
  bootstrapped = true;
  const fromHash = parseTokenFromFragment(window.location.hash);
  if (fromHash) {
    memoryToken = fromHash;
    storeToken(fromHash);
    const url = new URL(window.location.href);
    url.hash = "";
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
    return memoryToken;
  }
  memoryToken = readStoredToken();
  return memoryToken;
}

export function getCapabilityToken(): string | null {
  if (!bootstrapped) {
    return bootstrapCapabilityToken();
  }
  return memoryToken;
}

/** Test helper: inject/clear in-memory token without touching the URL. */
export function setCapabilityTokenForTests(token: string | null): void {
  bootstrapped = true;
  memoryToken = token;
}

export function authHeaders(): HeadersInit {
  const token = getCapabilityToken();
  return token ? { "X-Praxis-Token": token } : {};
}

/** Capability token: fragment bootstrap → memory only (not cookies/storage). */

let memoryToken: string | null = null;
let bootstrapped = false;

function parseTokenFromFragment(hash: string): string | null {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!raw) return null;
  const params = new URLSearchParams(raw);
  return params.get("token");
}

/** Read `#token=` once, store in memory, strip from the visible URL. */
export function bootstrapCapabilityToken(): string | null {
  if (bootstrapped) {
    return memoryToken;
  }
  bootstrapped = true;
  const fromHash = parseTokenFromFragment(window.location.hash);
  if (fromHash) {
    memoryToken = fromHash;
    const url = new URL(window.location.href);
    url.hash = "";
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }
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

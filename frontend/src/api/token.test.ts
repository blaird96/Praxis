import { afterEach, describe, expect, it, vi } from "vitest";

const STORAGE_KEY = "praxis_capability_token";

describe("capability token fragment bootstrap", () => {
  afterEach(() => {
    vi.resetModules();
    window.history.replaceState(null, "", "/");
    sessionStorage.clear();
  });

  it("reads #token, stores in memory, and clears the hash", async () => {
    window.history.replaceState(null, "", "/#token=secret-fragment-token");
    const mod = await import("./token");
    const token = mod.bootstrapCapabilityToken();
    expect(token).toBe("secret-fragment-token");
    expect(mod.getCapabilityToken()).toBe("secret-fragment-token");
    expect(window.location.hash).toBe("");
    expect(window.location.search).toBe("");
  });

  it("ignores a token placed in the query string", async () => {
    window.history.replaceState(null, "", "/?token=query-should-be-ignored");
    const mod = await import("./token");
    expect(mod.bootstrapCapabilityToken()).toBeNull();
  });

  it("mirrors the token to sessionStorage so a reload can recover it", async () => {
    window.history.replaceState(null, "", "/#token=secret-fragment-token");
    const mod = await import("./token");
    mod.bootstrapCapabilityToken();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe("secret-fragment-token");
  });

  it("recovers the token from sessionStorage when the fragment is gone (reload)", async () => {
    sessionStorage.setItem(STORAGE_KEY, "token-from-earlier-in-this-tab");
    window.history.replaceState(null, "", "/");
    const mod = await import("./token");
    expect(mod.bootstrapCapabilityToken()).toBe("token-from-earlier-in-this-tab");
    expect(mod.getCapabilityToken()).toBe("token-from-earlier-in-this-tab");
  });

  it("has no token when neither the fragment nor sessionStorage has one", async () => {
    window.history.replaceState(null, "", "/");
    const mod = await import("./token");
    expect(mod.bootstrapCapabilityToken()).toBeNull();
  });
});

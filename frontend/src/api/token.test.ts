import { afterEach, describe, expect, it, vi } from "vitest";

describe("capability token fragment bootstrap", () => {
  afterEach(() => {
    vi.resetModules();
    window.history.replaceState(null, "", "/");
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

  it("does not use sessionStorage or query string", async () => {
    window.history.replaceState(null, "", "/?token=query-should-be-ignored");
    const mod = await import("./token");
    expect(mod.bootstrapCapabilityToken()).toBeNull();
    expect(sessionStorage.getItem("praxis_capability_token")).toBeNull();
  });
});

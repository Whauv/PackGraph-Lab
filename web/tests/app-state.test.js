import { describe, it, expect, beforeEach } from "vitest";
import "../assets/modules/app-state.js";

beforeEach(() => {
  window.localStorage.clear();
});

describe("PackGraphState", () => {

  it("attaches PackGraphState to window", () => {
    expect(window.PackGraphState).toBeDefined();
    expect(typeof window.PackGraphState.createDefaultState).toBe("function");
  });

  it("createDefaultState returns expected shape", () => {
    const state = window.PackGraphState.createDefaultState();
    expect(state.materials).toEqual([]);
    expect(state.products).toEqual([]);
    expect(state.suppliers).toEqual([]);
    expect(state.applications).toEqual([]);
    expect(state.regulations).toEqual([]);
    expect(state.currentSection).toBe("dashboard");
    expect(state.theme).toBe("light");
    expect(state.currentUser).toBeNull();
    expect(state.notifications).toEqual([]);
  });

  it("createDefaultState returns independent copies", () => {
    const a = window.PackGraphState.createDefaultState();
    const b = window.PackGraphState.createDefaultState();
    a.materials.push({ id: "test" });
    expect(b.materials).toEqual([]);
  });

  it("defaultActiveCase returns a case object", () => {
    const c = window.PackGraphState.defaultActiveCase();
    expect(c.case_id).toMatch(/^CASE-/);
    expect(c.status).toBe("discover");
    expect(c.workflow_step).toBe("Discover");
    expect(c.focus_material_id).toBeNull();
  });

  it("storageKeys are defined", () => {
    const keys = window.PackGraphState.storageKeys;
    expect(keys.sessionToken).toBe("packgraph-session-token");
    expect(keys.theme).toBe("packgraph-theme");
    expect(keys.activeCase).toBe("packgraph-active-case");
    expect(keys.graphPins).toBe("packgraph-graph-pins");
  });

  it("loadJson returns fallback for missing key", () => {
    expect(window.PackGraphState.loadJson("nonexistent", [])).toEqual([]);
  });

  it("saveJson and loadJson round-trip", () => {
    window.PackGraphState.saveJson("test-key", { a: 1 });
    expect(window.PackGraphState.loadJson("test-key", null)).toEqual({ a: 1 });
  });

  it("loadJson returns fallback for corrupted data", () => {
    window.localStorage.setItem("bad-json", "{broken");
    expect(window.PackGraphState.loadJson("bad-json", "default")).toBe("default");
  });
});

import { describe, it, expect, beforeEach } from "vitest";
import "../assets/modules/shared-ui.js";

beforeEach(() => {
  document.body.innerHTML = "";
  window.localStorage.clear();
});

describe("PackGraphUI", () => {

  it("attaches PackGraphUI to window", () => {
    expect(window.PackGraphUI).toBeDefined();
  });

  describe("escape", () => {
    it("escapes HTML special characters", () => {
      expect(window.PackGraphUI.escape('<script>alert("xss")</script>')).toBe(
        "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;"
      );
    });

    it("handles ampersands", () => {
      expect(window.PackGraphUI.escape("A & B")).toBe("A &amp; B");
    });

    it("handles single quotes", () => {
      expect(window.PackGraphUI.escape("it's")).toBe("it&#39;s");
    });

    it("handles null and undefined", () => {
      expect(window.PackGraphUI.escape(null)).toBe("");
      expect(window.PackGraphUI.escape(undefined)).toBe("");
    });

    it("coerces numbers to strings", () => {
      expect(window.PackGraphUI.escape(42)).toBe("42");
    });
  });

  describe("emptyState", () => {
    it("renders a placeholder with escaped title and text", () => {
      const html = window.PackGraphUI.emptyState("No items", "Try again later");
      expect(html).toContain("<strong>No items</strong>");
      expect(html).toContain("<p>Try again later</p>");
      expect(html).toContain("table-empty");
    });
  });

  describe("badge", () => {
    it("renders a tag span with escaped text", () => {
      expect(window.PackGraphUI.badge("Active")).toContain(
        '<span class="tag">Active</span>'
      );
    });

    it("accepts a custom class", () => {
      expect(window.PackGraphUI.badge("Draft", "pill")).toContain(
        '<span class="pill">Draft</span>'
      );
    });
  });

  describe("tonePill", () => {
    it("renders a status pill with tone", () => {
      const html = window.PackGraphUI.tonePill("Approved", "success");
      expect(html).toContain("status-pill-success");
      expect(html).toContain("Approved");
    });

    it("defaults to neutral tone", () => {
      const html = window.PackGraphUI.tonePill("Pending");
      expect(html).toContain("status-pill-neutral");
    });
  });

  describe("banner", () => {
    it("renders a banner with all parts", () => {
      const html = window.PackGraphUI.banner({
        eyebrow: "Alert",
        title: "Heads up",
        body: "Something happened",
        actions: "<button>OK</button>",
      });
      expect(html).toContain("ui-banner");
      expect(html).toContain("Alert");
      expect(html).toContain("Heads up");
      expect(html).toContain("Something happened");
      expect(html).toContain("<button>OK</button>");
    });

    it("omits missing parts", () => {
      const html = window.PackGraphUI.banner({ title: "Only title" });
      expect(html).toContain("Only title");
      expect(html).not.toContain("eyebrow");
      expect(html).not.toContain("ui-banner-actions");
    });
  });

  describe("tableList", () => {
    it("returns empty state when rows array is empty", () => {
      const html = window.PackGraphUI.tableList([], "No data", "Nothing found");
      expect(html).toContain("No data");
      expect(html).toContain("Nothing found");
      expect(html).toContain("table-empty");
    });

    it("renders rows when provided", () => {
      const html = window.PackGraphUI.tableList(["<div>Row 1</div>", "<div>Row 2</div>"]);
      expect(html).toContain("ui-table-list");
      expect(html).toContain("Row 1");
      expect(html).toContain("Row 2");
    });
  });

  describe("tableRow", () => {
    it("renders a row with all fields", () => {
      const html = window.PackGraphUI.tableRow({
        eyebrow: "Material",
        title: "HDPE",
        meta: "Updated today",
        tone: "success",
      });
      expect(html).toContain("ui-table-row-success");
      expect(html).toContain("Material");
      expect(html).toContain("HDPE");
      expect(html).toContain("Updated today");
    });
  });

  describe("toast", () => {
    it("creates toast container and appends a toast", () => {
      window.PackGraphUI.toast("Saved!", "success");
      const container = document.getElementById("toast-stack");
      expect(container).not.toBeNull();
      expect(container.querySelector(".toast-success")).not.toBeNull();
      expect(container.textContent).toContain("Saved!");
    });

    it("reuses existing toast container", () => {
      window.PackGraphUI.toast("First");
      window.PackGraphUI.toast("Second");
      const containers = document.querySelectorAll("#toast-stack");
      expect(containers.length).toBe(1);
    });
  });
});

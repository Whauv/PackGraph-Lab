window.PackGraphUI = {
  tour: {
    steps: [],
    index: 0,
    navigator: null,
    keyHandler: null,
  },

  escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  },

  emptyState(title, text) {
    return `
      <div class="table-empty">
        <span class="table-empty-illustration" aria-hidden="true"></span>
        <strong>${this.escape(title)}</strong>
        <p>${this.escape(text)}</p>
      </div>`;
  },

  loadingState(title, text = "Loading...") {
    return `
      <div class="table-empty">
        <span class="table-empty-illustration" aria-hidden="true"></span>
        <strong>${this.escape(title)}</strong>
        <p>${this.escape(text)}</p>
      </div>`;
  },

  statusState(tone, title, text) {
    return `
      <div class="table-empty table-empty-${this.escape(tone)}">
        <span class="table-empty-illustration" aria-hidden="true"></span>
        <strong>${this.escape(title)}</strong>
        <p>${this.escape(text)}</p>
      </div>`;
  },

  badge(text, className = "tag") {
    return `<span class="${className}">${this.escape(text)}</span>`;
  },

  tonePill(text, tone = "neutral") {
    return `<span class="status-pill status-pill-${tone}">${this.escape(text)}</span>`;
  },

  banner({ eyebrow = "", title = "", body = "", actions = "" } = {}) {
    return `
      <div class="ui-banner">
        <div class="ui-banner-copy">
          ${eyebrow ? `<p class="eyebrow">${this.escape(eyebrow)}</p>` : ""}
          ${title ? `<h3>${this.escape(title)}</h3>` : ""}
          ${body ? `<p>${this.escape(body)}</p>` : ""}
        </div>
        ${actions ? `<div class="ui-banner-actions">${actions}</div>` : ""}
      </div>`;
  },

  actionRow(actions = []) {
    return `<div class="ui-action-row">${actions.join("")}</div>`;
  },

  tableList(rows = [], emptyTitle = "Nothing here yet", emptyText = "There are no records to show.") {
    if (!rows.length) {
      return this.emptyState(emptyTitle, emptyText);
    }
    return `<div class="ui-table-list">${rows.join("")}</div>`;
  },

  tableRow({ eyebrow = "", title = "", meta = "", tone = "" } = {}) {
    return `
      <article class="ui-table-row${tone ? ` ui-table-row-${this.escape(tone)}` : ""}">
        <div class="ui-table-row-main">
          ${eyebrow ? `<span class="section-label">${this.escape(eyebrow)}</span>` : ""}
          <strong>${this.escape(title)}</strong>
        </div>
        ${meta ? `<div class="ui-table-row-meta">${this.escape(meta)}</div>` : ""}
      </article>`;
  },

  toast(message, tone = "success") {
    let container = document.getElementById("toast-stack");
    if (!container) {
      document.body.insertAdjacentHTML("beforeend", `<div id="toast-stack" class="toast-stack" aria-live="polite"></div>`);
      container = document.getElementById("toast-stack");
    }
    const node = document.createElement("div");
    node.className = `toast toast-${this.escape(tone)}`;
    node.textContent = message;
    container.prepend(node);
    window.setTimeout(() => {
      node.classList.add("toast-leaving");
      window.setTimeout(() => node.remove(), 220);
    }, 3200);
  },

  bindDisclosureMemory(root = document) {
    root.querySelectorAll("details[data-disclosure-key]").forEach((details) => {
      const key = `packgraph-disclosure:${details.dataset.disclosureKey}`;
      details.open = window.localStorage.getItem(key) === "open";
      details.addEventListener("toggle", () => {
        if (details.open) {
          window.localStorage.setItem(key, "open");
        } else {
          window.localStorage.removeItem(key);
        }
      });
    });
  },

  initHelpMenu() {
    const button = document.getElementById("guided-tour-button");
    if (!button || document.getElementById("help-menu")) return;
    button.insertAdjacentHTML("afterend", `
      <div id="help-menu" class="help-menu" hidden>
        <button type="button" data-help-action="tour">Guided tour</button>
        <button type="button" data-help-action="commands">Run commands</button>
        <button type="button" data-help-action="shortcuts">Keyboard shortcuts</button>
      </div>
    `);
    const menu = document.getElementById("help-menu");
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      menu.hidden = !menu.hidden;
    });
    menu.addEventListener("click", (event) => {
      const action = event.target?.dataset?.helpAction;
      if (!action) return;
      menu.hidden = true;
      if (action === "tour") this.startGuidedTour();
      if (action === "commands") {
        document.getElementById("command-center-panel")?.removeAttribute("hidden");
        document.getElementById("command-center-input")?.focus();
      }
      if (action === "shortcuts") {
        this.toast("Shortcuts: Ctrl/Cmd+K opens search, Esc closes panels, arrow keys move through the tour.", "info");
      }
    });
    document.addEventListener("click", (event) => {
      if (!menu.hidden && !menu.contains(event.target) && event.target !== button) {
        menu.hidden = true;
      }
    });
  },

  initGuidedTour({ steps, navigator }) {
    this.tour.steps = steps || [];
    this.tour.navigator = navigator || null;
    this.ensureTourChrome();
    const button = document.getElementById("guided-tour-button");
    if (button) {
      this.initHelpMenu();
    }
  },

  ensureTourChrome() {
    if (document.getElementById("guided-tour-overlay")) return;
    document.body.insertAdjacentHTML("beforeend", `
      <div id="guided-tour-overlay" class="guided-tour-overlay" hidden></div>
      <div id="guided-tour-tooltip" class="guided-tour-tooltip" hidden>
        <div class="guided-tour-step"></div>
        <h4 id="guided-tour-title"></h4>
        <p id="guided-tour-body"></p>
        <div class="guided-tour-actions">
          <button type="button" id="guided-tour-back" class="secondary">Back</button>
          <button type="button" id="guided-tour-skip" class="secondary">Skip</button>
          <button type="button" id="guided-tour-next">Next</button>
        </div>
      </div>
    `);
    document.getElementById("guided-tour-back").addEventListener("click", () => this.stepGuidedTour(-1));
    document.getElementById("guided-tour-next").addEventListener("click", () => this.stepGuidedTour(1));
    document.getElementById("guided-tour-skip").addEventListener("click", () => this.stopGuidedTour());
  },

  async startGuidedTour() {
    if (!this.tour.steps.length) return;
    this.tour.index = 0;
    this.tour.keyHandler = (event) => {
      if (event.key === "Escape") this.stopGuidedTour();
      if (event.key === "ArrowRight" || event.key === "Enter") this.stepGuidedTour(1);
      if (event.key === "ArrowLeft") this.stepGuidedTour(-1);
    };
    window.addEventListener("keydown", this.tour.keyHandler);
    await this.renderGuidedTourStep();
  },

  async stepGuidedTour(direction) {
    const nextIndex = this.tour.index + direction;
    if (nextIndex < 0) return;
    if (nextIndex >= this.tour.steps.length) {
      this.stopGuidedTour();
      return;
    }
    this.tour.index = nextIndex;
    await this.renderGuidedTourStep();
  },

  stopGuidedTour() {
    document.getElementById("guided-tour-overlay")?.setAttribute("hidden", "hidden");
    document.getElementById("guided-tour-tooltip")?.setAttribute("hidden", "hidden");
    document.querySelectorAll(".guided-tour-target").forEach((node) => node.classList.remove("guided-tour-target"));
    if (this.tour.keyHandler) {
      window.removeEventListener("keydown", this.tour.keyHandler);
      this.tour.keyHandler = null;
    }
  },

  async renderGuidedTourStep() {
    const step = this.tour.steps[this.tour.index];
    if (!step) return;
    if (typeof this.tour.navigator === "function") {
      await this.tour.navigator(step);
    }
    document.querySelectorAll(".guided-tour-target").forEach((node) => node.classList.remove("guided-tour-target"));
    const target = document.querySelector(step.selector);
    if (!target) return;
    target.classList.add("guided-tour-target");
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    const rect = target.getBoundingClientRect();
    const overlay = document.getElementById("guided-tour-overlay");
    const tooltip = document.getElementById("guided-tour-tooltip");
    overlay.removeAttribute("hidden");
    tooltip.removeAttribute("hidden");
    overlay.style.clipPath = `polygon(0 0, 100% 0, 100% 100%, 0 100%, 0 0, ${rect.left}px ${rect.top}px, ${rect.left}px ${rect.bottom}px, ${rect.right}px ${rect.bottom}px, ${rect.right}px ${rect.top}px, ${rect.left}px ${rect.top}px)`;
    document.querySelector(".guided-tour-step").textContent = `Step ${this.tour.index + 1} of ${this.tour.steps.length}`;
    document.getElementById("guided-tour-title").textContent = step.title;
    document.getElementById("guided-tour-body").textContent = step.body;
    const tooltipTop = Math.min(window.innerHeight - 220, rect.bottom + 16);
    const tooltipLeft = Math.min(window.innerWidth - 360, Math.max(16, rect.left));
    tooltip.style.top = `${tooltipTop}px`;
    tooltip.style.left = `${tooltipLeft}px`;
    document.getElementById("guided-tour-back").disabled = this.tour.index === 0;
    document.getElementById("guided-tour-next").textContent = this.tour.index === this.tour.steps.length - 1 ? "Finish" : "Next";
  },
};

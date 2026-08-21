(function () {
  const STORAGE_KEY = "packgraph-chat-context";
  const OPEN_KEY = "packgraph-chat-open";

  const state = {
    context: null,
    request: null,
    onResult: null,
    initialized: false,
  };

  function safeParse(value, fallback = null) {
    try {
      return JSON.parse(value);
    } catch {
      return fallback;
    }
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatLabel(value) {
    return String(value || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (token) => token.toUpperCase());
  }

  function normalizeContext(context) {
    if (!context || typeof context !== "object") return null;
    const normalized = {
      entity_type: String(context.entity_type || "").trim(),
      entity_id: context.entity_id ? String(context.entity_id).trim() : "",
      entity_name: context.entity_name ? String(context.entity_name).trim() : "",
      metadata: context.metadata && typeof context.metadata === "object" ? { ...context.metadata } : {},
    };
    if (!normalized.entity_type && !normalized.entity_id && !normalized.entity_name) {
      return null;
    }
    return normalized;
  }

  function drawer() {
    return document.getElementById("graph-chat-drawer");
  }

  function overlay() {
    return document.getElementById("graph-chat-overlay");
  }

  function input() {
    return document.getElementById("graph-chat-input");
  }

  function setStatus(message = "", tone = "") {
    const node = document.getElementById("graph-chat-status");
    if (!node) return;
    node.className = `upload-status${tone ? ` ${tone}` : ""}`;
    node.textContent = message;
  }

  function persistContext() {
    if (state.context) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state.context));
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }

  function persistOpenState(open) {
    if (open) {
      window.localStorage.setItem(OPEN_KEY, "1");
    } else {
      window.localStorage.removeItem(OPEN_KEY);
    }
  }

  function quickPromptsForContext(context) {
    switch ((context.entity_type || "").toLowerCase()) {
      case "material":
        return ["Show suppliers for this", "Show evidence for this", "Compare this to alternatives"];
      case "supplier":
        return ["Show supplied materials for this", "Show risk for this supplier", "Show evidence for this"];
      case "regulation":
        return ["Show affected materials for this", "Show evidence for this", "What needs attention for this"];
      default:
        return ["Show evidence for this", "What should I inspect next for this", "Compare this to alternatives"];
    }
  }

  function renderContext() {
    const target = document.getElementById("graph-chat-context");
    const quickActions = document.getElementById("graph-chat-quick-actions");
    if (!target || !quickActions) return;
    if (!state.context) {
      target.innerHTML = `
        <div class="graph-chat-context-empty">
          <strong>No selected entity</strong>
          <p>Select a material, supplier, regulation, or detail card anywhere in the product to carry it into chat.</p>
        </div>`;
      quickActions.innerHTML = "";
      return;
    }

    const metadata = Object.entries(state.context.metadata || {})
      .filter(([, value]) => value !== null && value !== undefined && value !== "")
      .slice(0, 4);

    target.innerHTML = `
      <div class="graph-chat-context-card">
        <div class="graph-chat-context-top">
          <span class="tag">${escapeHtml(state.context.entity_type)}</span>
          ${state.context.entity_id ? `<span class="tag">${escapeHtml(state.context.entity_id)}</span>` : ""}
        </div>
        <strong>${escapeHtml(state.context.entity_name || "Selected entity")}</strong>
        ${metadata.length ? `
          <div class="graph-chat-context-meta">
            ${metadata.map(([key, value]) => `<div class="fact"><span>${escapeHtml(formatLabel(key))}</span><strong>${escapeHtml(String(value))}</strong></div>`).join("")}
          </div>` : `<p class="graph-chat-context-copy">Use the quick prompts below or ask a custom question.</p>`}
      </div>`;

    const prompts = quickPromptsForContext(state.context);
    quickActions.innerHTML = prompts.map((prompt) => `
      <button type="button" class="mini-action" data-chat-prompt="${escapeHtml(prompt)}">${escapeHtml(prompt)}</button>
    `).join("");
    quickActions.querySelectorAll("[data-chat-prompt]").forEach((button) => {
      button.addEventListener("click", () => {
        if (input()) {
          input().value = button.dataset.chatPrompt;
          input().focus();
        }
      });
    });
  }

  function renderMessage(author, body, tone = "") {
    const feed = document.getElementById("graph-chat-messages");
    if (!feed) return;
    const node = document.createElement("div");
    node.className = `graph-chat-message${tone ? ` ${tone}` : ""}`;
    node.innerHTML = `<span class="graph-chat-author">${escapeHtml(author)}</span><div>${escapeHtml(body)}</div>`;
    feed.prepend(node);
  }

  function open() {
    const panel = drawer();
    const backdrop = overlay();
    if (!panel || !backdrop) return;
    panel.hidden = false;
    backdrop.hidden = false;
    requestAnimationFrame(() => {
      panel.classList.add("open");
      backdrop.classList.add("open");
    });
    persistOpenState(true);
  }

  function close() {
    const panel = drawer();
    const backdrop = overlay();
    if (!panel || !backdrop) return;
    panel.classList.remove("open");
    backdrop.classList.remove("open");
    panel.hidden = true;
    backdrop.hidden = true;
    persistOpenState(false);
  }

  function toggle() {
    if (drawer()?.classList.contains("open")) {
      close();
    } else {
      open();
    }
  }

  async function submit(question) {
    if (!question || !state.request) return;
    setStatus("Running graph chat...", "info");
    renderMessage("You", question);
    try {
      const response = await state.request({
        question,
        context: state.context,
      });
      renderMessage("PackGraph", response.message || "No answer returned.");
      if (typeof state.onResult === "function") {
        state.onResult(question, response, state.context);
      }
      setStatus(
        response.resolved_question && response.resolved_question !== question
          ? `Resolved with selected context: ${response.resolved_question}`
          : "Answer ready.",
        "success"
      );
    } catch (error) {
      renderMessage("PackGraph", error.message || "Graph chat failed.", "error");
      setStatus(error.message || "Graph chat failed.", "error");
    }
  }

  function setContext(context, options = {}) {
    state.context = normalizeContext(context);
    persistContext();
    renderContext();
    if (options.prompt && input()) {
      input().value = options.prompt;
    }
    if (options.open) {
      open();
    }
  }

  function init(config = {}) {
    if (state.initialized) return;
    state.initialized = true;
    state.request = config.request || null;
    state.onResult = config.onResult || null;

    document.getElementById("graph-chat-launcher")?.addEventListener("click", toggle);
    document.getElementById("graph-chat-close")?.addEventListener("click", close);
    overlay()?.addEventListener("click", close);
    document.getElementById("graph-chat-clear-context")?.addEventListener("click", () => setContext(null));
    document.getElementById("graph-chat-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const value = input()?.value.trim();
      if (!value) return;
      input().value = "";
      await submit(value);
    });

    const stored = normalizeContext(safeParse(window.localStorage.getItem(STORAGE_KEY)));
    if (stored) {
      state.context = stored;
    }
    renderContext();
    if (window.localStorage.getItem(OPEN_KEY) === "1") {
      open();
    }
  }

  window.PackGraphChat = {
    init,
    open,
    close,
    toggle,
    submit,
    setContext,
    getContext() {
      return state.context ? { ...state.context, metadata: { ...(state.context.metadata || {}) } } : null;
    },
  };
})();

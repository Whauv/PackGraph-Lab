(function () {
  const STORAGE_KEY = "packgraph-chat-context";
  const HISTORY_KEY = "packgraph-chat-context-history";
  const OPEN_KEY = "packgraph-chat-open";
  const LOCK_KEY = "packgraph-chat-context-lock";
  const MODE_KEY = "packgraph-chat-mode";
  const MESSAGE_PREFIX = "packgraph-chat-messages:";

  const state = {
    context: null,
    history: [],
    request: null,
    onResult: null,
    initialized: false,
    contextLocked: false,
    mode: "quick_ask",
    workflowStatus: null,
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

  function modeSelect() {
    return document.getElementById("graph-chat-mode");
  }

  function contextKey(context = state.context) {
    if (!context) return "global";
    return `${context.entity_type || "entity"}:${context.entity_id || context.entity_name || "unknown"}`;
  }

  function contextPlaceholder(context) {
    switch ((context?.entity_type || "").toLowerCase()) {
      case "material":
        return `Ask about ${context.entity_name || "this material"}: suppliers, evidence, substitutes, or risk`;
      case "supplier":
        return `Ask about ${context.entity_name || "this supplier"}: supplied materials, evidence, or risk`;
      case "product":
        return `Ask about ${context.entity_name || "this product"}: linked materials, alternatives, or evidence`;
      case "document":
      case "report":
      case "test_report":
      case "source":
      case "uploaded_record":
        return `Ask about ${context.entity_name || "this record"}: extracted fields, provenance, or linked entities`;
      default:
        return "Ask the graph about the selected entity";
    }
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
    if (state.history.length) {
      window.localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history));
    } else {
      window.localStorage.removeItem(HISTORY_KEY);
    }
  }

  function persistOpenState(open) {
    if (open) {
      window.localStorage.setItem(OPEN_KEY, "1");
    } else {
      window.localStorage.removeItem(OPEN_KEY);
    }
  }

  function persistModeAndLock() {
    window.localStorage.setItem(MODE_KEY, state.mode);
    if (state.contextLocked) {
      window.localStorage.setItem(LOCK_KEY, "1");
    } else {
      window.localStorage.removeItem(LOCK_KEY);
    }
  }

  function messageStorageKey(context = state.context) {
    return `${MESSAGE_PREFIX}${contextKey(context)}`;
  }

  function readMessages(context = state.context) {
    const rows = safeParse(window.localStorage.getItem(messageStorageKey(context)), []);
    return Array.isArray(rows) ? rows.slice(0, 12) : [];
  }

  function writeMessages(messages, context = state.context) {
    window.localStorage.setItem(messageStorageKey(context), JSON.stringify(messages.slice(0, 12)));
  }

  function quickPromptsForContext(context) {
    const workflowPrompts = state.workflowStatus?.follow_up_suggestions || [];
    switch ((context.entity_type || "").toLowerCase()) {
      case "material":
        return ["Show suppliers for this", "Show evidence for this", "Compare this to alternatives", ...workflowPrompts].slice(0, 5);
      case "supplier":
        return ["Show supplied materials for this", "Show risk for this supplier", "Show evidence for this", ...workflowPrompts].slice(0, 5);
      case "regulation":
        return ["Show affected materials for this", "Show evidence for this", "What needs attention for this", ...workflowPrompts].slice(0, 5);
      default:
        return ["Show evidence for this", "What should I inspect next for this", "Compare this to alternatives", ...workflowPrompts].slice(0, 5);
    }
  }

  function renderContextStack() {
    const stack = document.getElementById("graph-chat-context-stack");
    if (!stack) return;
    const rows = state.history || [];
    stack.innerHTML = rows.length
      ? `<div class="graph-chat-stack-label">Recent contexts</div>${rows.map((item) => `
          <button type="button" class="graph-chat-stack-item" data-chat-context-key="${escapeHtml(contextKey(item))}">
            <span>${escapeHtml(formatLabel(item.entity_type))}</span>
            <strong>${escapeHtml(item.entity_name || item.entity_id || "Entity")}</strong>
          </button>
        `).join("")}`
      : "";
    stack.querySelectorAll("[data-chat-context-key]").forEach((button) => {
      button.addEventListener("click", () => {
        const next = rows.find((item) => contextKey(item) === button.dataset.chatContextKey);
        if (next) setContext(next, { force: true });
      });
    });
  }

  function renderContext() {
    const target = document.getElementById("graph-chat-context");
    const quickActions = document.getElementById("graph-chat-quick-actions");
    const messageInput = input();
    if (!target || !quickActions) return;
    if (!state.context) {
      if (messageInput) {
        messageInput.placeholder = "Select an entity, then ask the graph a focused question";
      }
      target.innerHTML = `
        <div class="graph-chat-context-empty">
          <strong>No selected entity</strong>
          <p>Select a material, supplier, regulation, or detail card anywhere in the product to carry it into chat.</p>
        </div>`;
      quickActions.innerHTML = "";
      renderContextStack();
      return;
    }
    if (messageInput) {
      messageInput.placeholder = contextPlaceholder(state.context);
    }

    const metadata = Object.entries(state.context.metadata || {})
      .filter(([, value]) => value !== null && value !== undefined && value !== "")
      .slice(0, 4);

    target.innerHTML = `
      <div class="graph-chat-context-card">
        <div class="graph-chat-context-top">
          <span class="tag">${escapeHtml(state.context.entity_type)}</span>
          ${state.context.entity_id ? `<span class="tag">${escapeHtml(state.context.entity_id)}</span>` : ""}
          ${state.contextLocked ? `<span class="tag status-warning">Locked</span>` : ""}
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
    renderContextStack();
    renderStoredMessages();
  }

  function renderStoredMessages() {
    const feed = document.getElementById("graph-chat-messages");
    if (!feed) return;
    feed.innerHTML = "";
    readMessages().forEach((item) => renderMessage(item.author, item.body, item.tone, { persist: false }));
  }

  function renderMessage(author, body, tone = "", options = {}) {
    const feed = document.getElementById("graph-chat-messages");
    if (!feed) return;
    const node = document.createElement("div");
    node.className = `graph-chat-message${tone ? ` ${tone}` : ""}`;
    node.innerHTML = `<span class="graph-chat-author">${escapeHtml(author)}</span><div>${escapeHtml(body)}</div>`;
    feed.prepend(node);
    if (options.persist !== false) {
      writeMessages([{ author, body, tone }, ...readMessages()]);
    }
  }

  function provisionalBadge(row) {
    const isProvisional = row?.source_type === "llm_inferred" || row?.assertion_kind === "LLM_INFERRED" || row?.validation_status === "pending";
    return isProvisional ? `<span class="tag status-warning">Provisional</span>` : `<span class="tag status-success">Verified KG</span>`;
  }

  function renderAssistantResponse(response) {
    const feed = document.getElementById("graph-chat-messages");
    if (!feed) return;
    const rows = response.results || response.rows || [];
    const route = response.route_preview || {};
    const quality = response.answer_quality || {};
    const enrichment = response.enrichment_request;
    const provenance = response.provenance || {};
    const node = document.createElement("div");
    node.className = "graph-chat-message graph-chat-answer";
    node.innerHTML = `
      <span class="graph-chat-author">PackGraph</span>
      <div class="graph-chat-answer-summary">${escapeHtml(response.message || "No answer returned.")}</div>
      <div class="graph-chat-answer-meta">
        <span class="tag">${escapeHtml(formatLabel(route.intent || response.intent || "graph answer"))}</span>
        <span class="tag">Confidence ${escapeHtml(Math.round((response.confidence || 0) * 100))}%</span>
        <span class="tag">${escapeHtml(response.latency_ms || 0)}ms</span>
        ${quality.needs_review ? `<span class="tag status-warning">Review needed</span>` : `<span class="tag status-success">Cleared</span>`}
      </div>
      ${rows.length ? `
        <div class="graph-chat-result-list">
          ${rows.slice(0, 4).map((row) => `
            <div class="graph-chat-result-row">
              <div>${provisionalBadge(row)} <strong>${escapeHtml(row.label || row.name || row.entity_id || "Result")}</strong></div>
              <small>${escapeHtml(row.preview || row.validation_status || row.verification_status || "")}</small>
              ${(row.validation_status || row.verification_status || row.promotion_status || row.edge_key) ? `
                <div class="graph-chat-source-meta">
                  ${row.validation_status ? `<span>Validation: ${escapeHtml(row.validation_status)}</span>` : ""}
                  ${row.verification_status ? `<span>Verification: ${escapeHtml(row.verification_status)}</span>` : ""}
                  ${row.promotion_status ? `<span>Promotion: ${escapeHtml(row.promotion_status)}</span>` : ""}
                  ${row.edge_key ? `<button type="button" class="mini-action" data-copy-edge="${escapeHtml(row.edge_key)}">Copy edge key</button>` : ""}
                </div>` : ""}
            </div>
          `).join("")}
        </div>` : ""}
      ${enrichment ? `
        <div class="graph-chat-enrichment">
          <strong>${escapeHtml(response.empty_state?.title || "Data gap detected")}</strong>
          <p>${escapeHtml(response.empty_state?.message || "A provisional enrichment request was staged for review.")}</p>
          <div class="graph-chat-source-meta">
            <span>${escapeHtml(enrichment.source)} -> ${escapeHtml(enrichment.relationship)} -> ${escapeHtml(enrichment.target)}</span>
            <button type="button" class="mini-action" data-copy-edge="${escapeHtml(enrichment.edge_key)}">Copy edge key</button>
          </div>
        </div>` : ""}
      <details class="graph-chat-provenance">
        <summary>Source details</summary>
        <p>Verified KG rows: ${escapeHtml((provenance.verified_kg || []).length || rows.length)} | Provisional inferred rows: ${escapeHtml((provenance.provisional || []).length || 0)}</p>
        <p>Route: ${escapeHtml(route.route || response.source || "graph")} | Template: ${escapeHtml(route.template || response.execution_metadata?.template || "read-only")}</p>
      </details>
    `;
    node.querySelectorAll("[data-copy-edge]").forEach((button) => {
      button.addEventListener("click", async () => {
        await navigator.clipboard?.writeText(button.dataset.copyEdge || "");
        setStatus("Copied edge key.", "success");
      });
    });
    feed.prepend(node);
    writeMessages([{ author: "PackGraph", body: response.message || "No answer returned.", tone: "answer" }, ...readMessages()]);
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
        mode: state.mode,
        context: {
          ...state.context,
          history: state.history,
        },
      });
      renderAssistantResponse(response);
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
    const normalized = normalizeContext(context);
    const previous = state.context;
    if (state.contextLocked && normalized && !options.force && previous && contextKey(previous) !== contextKey(normalized)) {
      state.history = [normalized, ...state.history.filter((item) => contextKey(item) !== contextKey(normalized))].slice(0, 5);
      persistContext();
      renderContext();
      setStatus(`Context is locked to ${previous.entity_name || previous.entity_id}. New selection was added to recent contexts.`, "info");
      return;
    }
    if (
      previous
      && normalized
      && (previous.entity_id !== normalized.entity_id || previous.entity_type !== normalized.entity_type)
    ) {
      state.history = [previous, ...state.history.filter((item) => !(item.entity_id === previous.entity_id && item.entity_type === previous.entity_type))]
        .slice(0, 4);
    }
    if (!normalized) {
      state.history = [];
    }
    state.context = normalized;
    persistContext();
    renderContext();
    renderStoredMessages();
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
    state.workflowStatus = config.workflowStatus || null;
    state.mode = window.localStorage.getItem(MODE_KEY) || "quick_ask";
    state.contextLocked = window.localStorage.getItem(LOCK_KEY) === "1";
    if (modeSelect()) modeSelect().value = state.mode;
    const lockButton = document.getElementById("graph-chat-lock");
    if (lockButton) {
      lockButton.textContent = state.contextLocked ? "Context locked" : "Lock context";
      lockButton.setAttribute("aria-pressed", state.contextLocked ? "true" : "false");
    }

    document.getElementById("graph-chat-launcher")?.addEventListener("click", toggle);
    document.getElementById("graph-chat-close")?.addEventListener("click", close);
    overlay()?.addEventListener("click", close);
    document.getElementById("graph-chat-clear-context")?.addEventListener("click", () => setContext(null));
    document.getElementById("graph-chat-lock")?.addEventListener("click", () => {
      state.contextLocked = !state.contextLocked;
      persistModeAndLock();
      const button = document.getElementById("graph-chat-lock");
      if (button) {
        button.textContent = state.contextLocked ? "Context locked" : "Lock context";
        button.setAttribute("aria-pressed", state.contextLocked ? "true" : "false");
      }
      renderContext();
    });
    modeSelect()?.addEventListener("change", (event) => {
      state.mode = event.target.value || "quick_ask";
      persistModeAndLock();
      setStatus(state.mode === "research_review" ? "Research Review mode will emphasize evidence and risk." : "Quick Ask mode is active.", "info");
    });
    document.getElementById("graph-chat-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const value = input()?.value.trim();
      if (!value) return;
      input().value = "";
      await submit(value);
    });

    const stored = normalizeContext(safeParse(window.localStorage.getItem(STORAGE_KEY)));
    const storedHistory = safeParse(window.localStorage.getItem(HISTORY_KEY), []);
    if (stored) {
      state.context = stored;
    }
    state.history = Array.isArray(storedHistory) ? storedHistory.map((item) => normalizeContext(item)).filter(Boolean).slice(0, 4) : [];
    renderContext();
    renderStoredMessages();
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
      return state.context
        ? {
            ...state.context,
            metadata: { ...(state.context.metadata || {}) },
            history: state.history.map((item) => ({ ...item, metadata: { ...(item.metadata || {}) } })),
        }
        : null;
    },
    setWorkflowStatus(payload) {
      state.workflowStatus = payload || null;
      renderContext();
    },
  };
})();

(function () {
  let deps = null;

  function renderProfile(payload) {
    const { escapeHtml, titleCase } = deps;
    const container = document.getElementById("source-intake-profile");
    if (!container) return;
    if (!payload) {
      container.innerHTML = window.PackGraphUI
        ? window.PackGraphUI.emptyState("No source uploaded yet", "Upload a JSON or PDF source to extract fields and answer future questions from it.")
        : "";
      return;
    }
    const profile = payload.schema_profile || {};
    const fields = profile.fields || [];
    const source = payload.source || {};
    const parseErrors = payload.parse_errors || [];
    container.innerHTML = `
      <div class="metric-card">
        <span>Source</span>
        <strong>${escapeHtml(source.title || "Uploaded source")}</strong>
        <small>${escapeHtml(titleCase(source.source_type || "source"))} ready for future questions</small>
      </div>
      <div class="metric-card">
        <span>Extracted fields</span>
        <strong>${Number(profile.record_count || payload.stored_record_count || 0).toLocaleString()}</strong>
        <small>${Number(profile.field_count || 0).toLocaleString()} fields available</small>
      </div>
      <div class="metric-card">
        <span>Question ready</span>
        <strong>${parseErrors.length ? "Needs review" : "Ready"}</strong>
        <small>${parseErrors.length ? "Open diagnostics for parser details" : "Can now answer from this source"}</small>
      </div>
      <details class="table-card source-schema-table advanced-diagnostics" data-disclosure-key="source-intake-advanced">
        <summary>Advanced diagnostics <span>For developers</span></summary>
        <div class="metric-card">
          <span>File</span>
          <strong>${Number(source.file_size || 0).toLocaleString()} bytes</strong>
          <small>${escapeHtml(source.filename || "local upload")}</small>
        </div>
        <div class="metric-card">
          <span>Parser</span>
          <strong>${parseErrors.length ? "Review parser output" : "Parsed cleanly"}</strong>
          <small>${parseErrors.length} parse issue(s)</small>
        </div>
        <div class="metric-card">
          <span>Schema</span>
          <strong>${Number(profile.field_count || 0).toLocaleString()} fields</strong>
        <small>${Number(profile.record_count || payload.stored_record_count || 0).toLocaleString()} reusable records</small>
        </div>
        ${fields.length
          ? `<table><thead><tr><th>Field</th><th>Type</th><th>Count</th></tr></thead><tbody>${fields.slice(0, 8).map((field) => `<tr><td>${escapeHtml(field.path)}</td><td>${escapeHtml((field.types || []).join(", "))}</td><td>${escapeHtml(field.count)}</td></tr>`).join("")}</tbody></table>`
          : window.PackGraphUI.emptyState("No structured fields", "The file was stored as searchable text for future prompts.")}
      </details>
    `;
  }

  function renderSources() {
    const { state, renderTableCard, escapeHtml, titleCase, setChatContext, setStatus } = deps;
    const formatUpdated = (value) => value ? new Date(value).toLocaleDateString() : "Just now";
    renderTableCard(
      "source-intake-sources",
      [
        { label: "Source", render: (item) => `<button type="button" class="table-entity-link" data-source-chat="${escapeHtml(item.source_id)}"><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.filename || "")}</small></button>` },
        { label: "Type", render: (item) => `<span class="table-badge">${escapeHtml(titleCase(item.source_type || "source"))}</span>` },
        { label: "Schema", render: (item) => `${Number(item.field_count || 0)} fields<br /><small>${Number(item.record_count || 0)} records</small>` },
        { label: "Last updated", render: (item) => `<small>${escapeHtml(formatUpdated(item.uploaded_at || item.created_at || item.updated_at))}</small>` },
        { label: "Action", render: (item) => `<button type="button" class="mini-action" data-source-chat="${escapeHtml(item.source_id)}">Ask about this</button>` },
      ],
      state.sourceIntakeSources || [],
      "No uploaded sources yet. Try supplier, material, regulation, or document names after you add one."
    );
    document.querySelectorAll("[data-source-chat]").forEach((button) => {
      button.addEventListener("click", () => {
        const source = (state.sourceIntakeSources || []).find((item) => item.source_id === button.dataset.sourceChat);
        if (!source) return;
        setChatContext(
          {
            entity_type: "uploaded_record",
            entity_id: source.source_id,
            entity_name: source.title,
            metadata: {
              source_type: source.source_type,
              record_count: source.record_count,
              field_count: source.field_count,
            },
          },
          { open: true }
        );
        setStatus("source-intake-status", `${source.title} can now answer questions in Ask PackGraph.`, "info");
      });
    });
  }

  async function loadSources() {
    const { state, fetchJson } = deps;
    try {
      state.sourceIntakeSources = await fetchJson("/source-intake/sources?limit=20");
    } catch {
      state.sourceIntakeSources = [];
    }
    renderSources();
    renderProfile(state.latestSourceIntakeProfile);
  }

  async function upload() {
    const { state, fetchJson, setStatus, setChatContext, syncProjectMemory } = deps;
    const fileInput = document.getElementById("source-intake-file");
    const file = fileInput?.files?.[0];
    if (!file) {
      setStatus("source-intake-status", "Choose a JSON or PDF source before uploading.", "error");
      return;
    }
      setStatus("source-intake-status", "Uploading source and extracting fields...", "info");
    const formData = new FormData();
    formData.set("file", file);
    const sourceType = document.getElementById("source-intake-type").value;
    const title = document.getElementById("source-intake-title").value.trim();
    if (sourceType) formData.set("source_type", sourceType);
    if (title) formData.set("title", title);
    try {
      const payload = await fetchJson("/source-intake/upload", {
        method: "POST",
        body: formData,
        retries: 0,
        timeoutMs: 30000,
      });
      state.latestSourceIntakeProfile = payload;
      const source = payload.source || {};
      renderProfile(payload);
      window.PackGraphUI?.bindDisclosureMemory?.(document);
      await loadSources();
      setChatContext(
        {
          entity_type: "uploaded_record",
          entity_id: source.source_id,
          entity_name: source.title,
          metadata: {
            source_type: source.source_type,
            record_count: source.record_count,
            field_count: source.field_count,
          },
        },
        { open: true }
      );
      await syncProjectMemory({ uploaded_file_references: [source.source_id], saved_entities: [source.source_id] });
      document.getElementById("source-intake-title").value = "";
      fileInput.value = "";
      setStatus("source-intake-status", `Uploaded ${source.title}. PackGraph can now answer questions from this source.`, "success");
    } catch (error) {
      setStatus("source-intake-status", error.message || "Source extraction failed.", "error");
    }
  }

  function init(nextDeps) {
    deps = nextDeps;
    renderProfile(nextDeps.state.latestSourceIntakeProfile);
    window.PackGraphUI?.bindDisclosureMemory?.(document);
  }

  window.PackGraphSourceIntake = { init, loadSources, upload };
})();

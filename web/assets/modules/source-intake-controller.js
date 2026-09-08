(function () {
  let deps = null;

  function renderProfile(payload) {
    const { escapeHtml, titleCase } = deps;
    const container = document.getElementById("source-intake-profile");
    if (!container) return;
    if (!payload) {
      container.innerHTML = window.PackGraphUI
        ? window.PackGraphUI.emptyState("No source extracted yet", "Upload a JSON or PDF source to see schema fields and reusable records.")
        : "";
      return;
    }
    const profile = payload.schema_profile || {};
    const fields = profile.fields || [];
    const source = payload.source || {};
    container.innerHTML = `
      <div class="metric-card">
        <span>Source</span>
        <strong>${escapeHtml(source.title || "Uploaded source")}</strong>
        <small>${escapeHtml(titleCase(source.source_type || "source"))} | ${Number(source.file_size || 0).toLocaleString()} bytes</small>
      </div>
      <div class="metric-card">
        <span>Schema</span>
        <strong>${Number(profile.field_count || 0).toLocaleString()} fields</strong>
        <small>${Number(profile.record_count || payload.stored_record_count || 0).toLocaleString()} reusable records</small>
      </div>
      <div class="metric-card">
        <span>Quality</span>
        <strong>${payload.parse_errors?.length ? "Needs review" : "Parsed"}</strong>
        <small>${payload.parse_errors?.length || 0} parse issues detected</small>
      </div>
      <div class="table-card source-schema-table">
        ${fields.length
          ? `<table><thead><tr><th>Field</th><th>Type</th><th>Count</th></tr></thead><tbody>${fields.slice(0, 8).map((field) => `<tr><td>${escapeHtml(field.path)}</td><td>${escapeHtml((field.types || []).join(", "))}</td><td>${escapeHtml(field.count)}</td></tr>`).join("")}</tbody></table>`
          : window.PackGraphUI.emptyState("No structured fields", "The file was stored as searchable text for future prompts.")}
      </div>
    `;
  }

  function renderSources() {
    const { state, renderTableCard, escapeHtml, titleCase, setChatContext, setStatus } = deps;
    renderTableCard(
      "source-intake-sources",
      [
        { label: "Source", render: (item) => `<strong>${escapeHtml(item.title)}</strong><br /><small>${escapeHtml(item.filename || "")}</small>` },
        { label: "Type", render: (item) => `<span class="table-badge">${escapeHtml(titleCase(item.source_type || "source"))}</span>` },
        { label: "Schema", render: (item) => `${Number(item.field_count || 0)} fields<br /><small>${Number(item.record_count || 0)} records</small>` },
        { label: "Action", render: (item) => `<button type="button" class="mini-action" data-source-chat="${escapeHtml(item.source_id)}">Use in graph chat</button>` },
      ],
      state.sourceIntakeSources || [],
      "No uploaded workspace sources yet."
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
        setStatus("source-intake-status", `${source.title} is now active in graph chat.`, "info");
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
      setStatus("source-intake-status", "Choose a JSON or PDF source before extracting.", "error");
      return;
    }
    setStatus("source-intake-status", "Extracting schema and storing reusable records...", "info");
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
      setStatus("source-intake-status", `Stored ${source.title}. Future prompts can now use this source.`, "success");
    } catch (error) {
      setStatus("source-intake-status", error.message || "Source extraction failed.", "error");
    }
  }

  function init(nextDeps) {
    deps = nextDeps;
    renderProfile(nextDeps.state.latestSourceIntakeProfile);
  }

  window.PackGraphSourceIntake = { init, loadSources, upload };
})();

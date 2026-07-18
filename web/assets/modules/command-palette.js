window.PackGraphCommandPalette = {
  open() {
    const modal = document.getElementById("command-palette");
    if (!modal) return;
    modal.hidden = false;
    document.getElementById("command-search-input")?.focus();
  },

  close() {
    const modal = document.getElementById("command-palette");
    if (!modal) return;
    modal.hidden = true;
  },

  render(payload, onSelect) {
    const container = document.getElementById("command-search-results");
    if (!container) return;
    const groups = [
      ["Results", payload.results || []],
      ["Workspaces", payload.workspaces || []],
      ["Contributions", payload.contributions || []],
      ["Community", payload.posts || []],
    ].filter(([, items]) => items.length);
    if (!groups.length) {
      container.innerHTML = window.PackGraphUI.emptyState("No matches", "Try a material, supplier, regulation, workspace, or discussion title.");
      return;
    }
    container.innerHTML = groups.map(([title, items]) => `
      <div class="detail-card">
        <h5>${window.PackGraphUI.escape(title)}</h5>
        <div class="card-list compact-list">
          ${items.map((item) => `
            <button type="button" class="row-card command-result-card" data-command-target="${window.PackGraphUI.escape(item.entity_type)}::${window.PackGraphUI.escape(item.entity_id)}">
              <strong>${window.PackGraphUI.escape(item.title)}</strong>
              <small>${window.PackGraphUI.escape(item.subtitle || "")}</small>
            </button>`).join("")}
        </div>
      </div>`).join("");
    container.querySelectorAll("[data-command-target]").forEach((button) => {
      button.addEventListener("click", () => {
        const [entityType, entityId] = button.dataset.commandTarget.split("::");
        onSelect(entityType, entityId);
      });
    });
  },
};

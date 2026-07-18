window.PackGraphExplorePage = {
  renderTabs(currentTab, onSelect) {
    const container = document.getElementById("explore-tabs");
    if (!container) return;
    const tabs = [
      ["materials", "Materials"],
      ["applications", "Applications"],
      ["suppliers", "Suppliers"],
      ["news", "News"],
    ];
    container.innerHTML = tabs.map(([value, label]) => `
      <button type="button" class="tab explore-tab${value === currentTab ? " active" : ""}" data-explore-tab="${value}">${label}</button>
    `).join("");
    container.querySelectorAll("[data-explore-tab]").forEach((button) => {
      button.addEventListener("click", () => onSelect(button.dataset.exploreTab));
    });
  },

  renderResults(items, onOpen, activeId, onCompare) {
    const container = document.getElementById("explore-results");
    if (!container) return;
    if (!items.length) {
      container.innerHTML = `
        <div class="table-empty">
          <span class="table-empty-illustration" aria-hidden="true"></span>
          <strong>No browse results yet</strong>
          <p>Adjust the filters or switch tabs to widen the research scope.</p>
        </div>`;
      return;
    }
    container.innerHTML = items.map((item) => `
      <article class="row-card explore-result-card${item.entity_id === activeId ? " active" : ""}">
        <div class="explore-result-top">
          <span class="table-badge">${this.escape(item.entity_type)}</span>
          <strong>${this.escape(item.title)}</strong>
        </div>
        <p>${this.escape(item.subtitle || "")}</p>
        <small>${this.escape(item.meta || "")}</small>
        ${item.match_reason ? `<div class="match-reason">${this.escape(item.match_reason)}</div>` : ""}
        ${(item.tags || []).length ? `<div class="tags">${item.tags.map((tag) => `<span class="tag">${this.escape(tag)}</span>`).join("")}</div>` : ""}
        <div class="row-actions">
          <button type="button" class="mini-action" data-open-explore="${this.escape(item.entity_type)}::${this.escape(item.entity_id)}">Open detail</button>
          ${item.entity_type === "material" ? `<button type="button" class="mini-action secondary" data-compare-explore="${this.escape(item.entity_id)}">Compare</button>` : ""}
        </div>
      </article>
    `).join("");
    container.querySelectorAll("[data-open-explore]").forEach((button) => {
      button.addEventListener("click", () => {
        const [entityType, entityId] = button.dataset.openExplore.split("::");
        onOpen(entityType, entityId);
      });
    });
    container.querySelectorAll("[data-compare-explore]").forEach((button) => {
      button.addEventListener("click", () => onCompare(button.dataset.compareExplore));
    });
  },

  renderDetail(detail, onJump) {
    const container = document.getElementById("explore-detail");
    if (!container) return;
    if (!detail) {
      container.innerHTML = `
        <div class="detail-card">
          <h4>Explore detail panel</h4>
          <p>Select a material, application, supplier, or news item to inspect the linked research context.</p>
        </div>`;
      return;
    }
    const related = detail.related || {};
    container.innerHTML = `
      <div class="detail-card">
        <h5>${this.escape(detail.entity_type)}</h5>
        <h4>${this.escape(detail.title)}</h4>
        <p>${this.escape(detail.summary || "")}</p>
        <div class="key-facts">
          ${(detail.facts || []).map((item) => `
            <div class="fact">
              <span>${this.escape(item.label)}</span>
              <strong>${this.escape(item.value)}</strong>
            </div>
          `).join("")}
        </div>
      </div>
      <div class="detail-card">
        <h5>Linked context</h5>
        <h4>What this connects to</h4>
        ${Object.entries(related).map(([label, values]) => `
          <div class="subsection">
            <div class="subsection-heading">${this.escape(label)}</div>
            <div class="tags">${(values || []).length ? values.map((value) => `<span class="tag">${this.escape(value)}</span>`).join("") : `<span class="tag">None</span>`}</div>
          </div>
        `).join("")}
        <div class="subsection">
          <div class="subsection-heading">Jump to dashboard</div>
          <p>Open the graph-backed workspace with a focused question already prepared from this entity.</p>
          <div class="row-actions">
            <button type="button" id="explore-jump-dashboard">Ask in Dashboard</button>
          </div>
        </div>
      </div>`;
    const button = document.getElementById("explore-jump-dashboard");
    if (button) {
      button.addEventListener("click", () => onJump(detail));
    }
  },

  escape(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  },
};

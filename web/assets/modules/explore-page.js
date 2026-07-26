window.PackGraphExplorePage = {
  renderTabs(currentTab, onSelect) {
    const container = document.getElementById("explore-tabs");
    if (!container) return;
    const tabs = [
      ["materials", "Materials"],
      ["products", "Products"],
      ["news", "News"],
    ];
    container.innerHTML = tabs.map(([value, label]) => `
      <button type="button" class="tab explore-tab${value === currentTab ? " active" : ""}" data-explore-tab="${value}">${label}</button>
    `).join("");
    container.querySelectorAll("[data-explore-tab]").forEach((button) => {
      button.addEventListener("click", () => onSelect(button.dataset.exploreTab));
    });
  },

  renderViewSwitcher(currentView, onSelect) {
    document.querySelectorAll("[data-explore-view]").forEach((button) => {
      button.classList.toggle("active", button.dataset.exploreView === currentView);
      button.onclick = () => onSelect(button.dataset.exploreView);
    });
  },

  renderResults(items, onOpen, activeId, onCompare, view = "cards") {
    const container = document.getElementById("explore-results");
    if (!container) return;
    if (!items.length) {
      container.innerHTML = `
        <div class="table-empty">
          <span class="table-empty-illustration" aria-hidden="true"></span>
          <strong>No results</strong>
          <p>Broaden the filters or switch modes.</p>
        </div>`;
      return;
    }
    if (view === "map") {
      this.renderMap(items, onOpen);
      return;
    }
    if (view === "graph") {
      this.renderGraph(items, onOpen, activeId);
      return;
    }
    container.innerHTML = `<div class="explore-card-grid">${items.map((item) => `
      <article class="explore-card${item.entity_id === activeId ? " active" : ""}">
        <button type="button" class="explore-card-button" data-open-explore="${this.escape(item.entity_type)}::${this.escape(item.entity_id)}">
          <div class="explore-thumb">
            <span>${this.escape(item.thumbnail || item.entity_type)}</span>
          </div>
          <div class="explore-card-body">
            <div class="explore-card-top">
              <span class="table-badge">${this.escape(item.classification || item.entity_type)}</span>
              <strong>${this.escape(item.title)}</strong>
            </div>
            <p>${this.escape(item.subtitle || "")}</p>
            <small>${this.escape(item.meta || "")}</small>
            ${(item.tags || []).length ? `<div class="tags">${item.tags.map((tag) => `<span class="tag">${this.escape(tag)}</span>`).join("")}</div>` : ""}
          </div>
        </button>
        <div class="row-actions">
          <button type="button" class="mini-action" data-open-explore="${this.escape(item.entity_type)}::${this.escape(item.entity_id)}">Open detail</button>
          ${item.entity_type === "material" ? `<button type="button" class="mini-action secondary" data-compare-explore="${this.escape(item.entity_id)}">Compare</button>` : ""}
        </div>
      </article>
    `).join("")}</div>`;
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

  renderMap(items, onOpen) {
    const container = document.getElementById("explore-results");
    const regionCoords = {
      "North America": { x: 18, y: 34 },
      Europe: { x: 48, y: 28 },
      "Asia Pacific": { x: 74, y: 38 },
      "Latin America": { x: 26, y: 68 },
      "Middle East": { x: 56, y: 42 },
      Africa: { x: 50, y: 62 },
    };
    const markers = [];
    items.forEach((item) => {
      (item.location_summary || []).forEach((region) => {
        if (!regionCoords[region]) return;
        markers.push({ region, x: regionCoords[region].x, y: regionCoords[region].y, item });
      });
    });
    container.innerHTML = `
      <div class="explore-map-surface">
        <div class="explore-map-board">
          ${Object.entries(regionCoords).map(([region, coord]) => `<span class="explore-map-region" style="left:${coord.x}%; top:${coord.y}%;">${this.escape(region)}</span>`).join("")}
          ${markers.map((marker, index) => `
            <button
              type="button"
              class="explore-map-marker"
              style="left:${marker.x}%; top:${marker.y + (index % 3) * 2}%"
              data-open-explore="${this.escape(marker.item.entity_type)}::${this.escape(marker.item.entity_id)}"
              title="${this.escape(marker.item.title)}"
            ></button>
          `).join("")}
        </div>
        <div class="explore-map-list">
          ${items.slice(0, 10).map((item) => `
            <button type="button" class="row-card saved-search-card" data-open-explore="${this.escape(item.entity_type)}::${this.escape(item.entity_id)}">
              <strong>${this.escape(item.title)}</strong>
              <small>${this.escape((item.location_summary || []).join(", ") || "No geography")}</small>
            </button>
          `).join("")}
        </div>
      </div>`;
    container.querySelectorAll("[data-open-explore]").forEach((button) => {
      button.addEventListener("click", () => {
        const [entityType, entityId] = button.dataset.openExplore.split("::");
        onOpen(entityType, entityId);
      });
    });
  },

  renderGraph(items, onOpen, activeId) {
    const container = document.getElementById("explore-results");
    const anchor = items[0];
    container.innerHTML = `
      <div class="explore-graph-surface">
        <div class="explore-graph-column">
          ${items.slice(0, 4).map((item) => `
            <button type="button" class="explore-graph-node${item.entity_id === activeId ? " active" : ""}" data-open-explore="${this.escape(item.entity_type)}::${this.escape(item.entity_id)}">
              <span>${this.escape(item.classification || item.entity_type)}</span>
              <strong>${this.escape(item.title)}</strong>
            </button>
          `).join("")}
        </div>
        <div class="explore-graph-anchor">
          <div class="explore-graph-center">
            <span>Current browse set</span>
            <strong>${this.escape(anchor?.classification || "Graph")}</strong>
            <p>${this.escape(anchor?.title || "Select a node")}</p>
          </div>
        </div>
        <div class="explore-graph-column">
          ${items.slice(4, 8).map((item) => `
            <button type="button" class="explore-graph-node${item.entity_id === activeId ? " active" : ""}" data-open-explore="${this.escape(item.entity_type)}::${this.escape(item.entity_id)}">
              <span>${this.escape(item.classification || item.entity_type)}</span>
              <strong>${this.escape(item.title)}</strong>
            </button>
          `).join("")}
        </div>
      </div>`;
    container.querySelectorAll("[data-open-explore]").forEach((button) => {
      button.addEventListener("click", () => {
        const [entityType, entityId] = button.dataset.openExplore.split("::");
        onOpen(entityType, entityId);
      });
    });
  },

  renderDetail(detail, onJump) {
    const container = document.getElementById("explore-detail");
    if (!container) return;
    if (!detail) {
      container.innerHTML = `
        <div class="detail-card">
          <h4>Select a result</h4>
          <p>Open a material, product, or update to inspect the context.</p>
        </div>`;
      return;
    }
    const related = detail.related || {};
    const sections = detail.sections || {};
    container.innerHTML = `
      <div class="detail-card explore-detail-hero-card">
        <div class="explore-thumb large-thumb"><span>${this.escape(detail.thumbnail || detail.entity_type)}</span></div>
        <div>
          <h5>${this.escape(detail.classification || detail.entity_type)}</h5>
          <h4>${this.escape(detail.title)}</h4>
          <p>${this.escape(detail.summary || "")}</p>
        </div>
        <div class="key-facts">
          ${(detail.facts || []).map((item) => `
            <div class="fact">
              <span>${this.escape(item.label)}</span>
              <strong>${this.escape(item.value)}</strong>
            </div>
          `).join("")}
        </div>
      </div>
      ${this.renderSection("Overview", sections.overview?.facts || [], sections.overview?.summary || "")}
      ${this.renderApplicationSection(sections.applications || [])}
      ${this.renderListSection("Suppliers", sections.suppliers || [], ["name", "location", "regions", "lead_time"])}
      ${this.renderListSection("Buyers", sections.buyers || [], ["name", "region", "signal"])}
      ${this.renderSignalSection("Market signals", sections.market_signals || [])}
      ${this.renderSignalSection("Sustainability metrics", sections.sustainability_metrics || [])}
      ${this.renderListSection("Regulatory requirements", sections.regulatory_requirements || [], ["name", "region", "effective_on"])}
      ${sections.alternate_materials ? this.renderListSection("Alternate materials", sections.alternate_materials, ["name", "reason"]) : ""}
      <div class="detail-card">
        <h5>Linked context</h5>
        <h4>Connected entities</h4>
        ${Object.entries(related).map(([label, values]) => `
          <div class="subsection">
            <div class="subsection-heading">${this.escape(label)}</div>
            <div class="tags">${(values || []).length ? values.map((value) => `<span class="tag">${this.escape(value)}</span>`).join("") : `<span class="tag">None</span>`}</div>
          </div>
        `).join("")}
      </div>
      ${this.renderDetailMap(detail.map_points || [])}
      ${this.renderDetailGraph(detail.graph || { nodes: [], edges: [] })}
      <div class="detail-card">
        <h5>Open in dashboard</h5>
        <h4>Carry this context forward</h4>
        <p>Move into the decision workspace with a prepared graph question.</p>
        <div class="row-actions">
          <button type="button" id="explore-jump-dashboard">Open Dashboard</button>
        </div>
      </div>`;
    const button = document.getElementById("explore-jump-dashboard");
    if (button) {
      button.addEventListener("click", () => onJump(detail));
    }
  },

  renderSection(title, facts, summary) {
    return `
      <div class="detail-card">
        <h5>${this.escape(title)}</h5>
        ${summary ? `<p>${this.escape(summary)}</p>` : ""}
        <div class="key-facts">
          ${facts.map((item) => `
            <div class="fact">
              <span>${this.escape(item.label)}</span>
              <strong>${this.escape(item.value)}</strong>
            </div>
          `).join("")}
        </div>
      </div>`;
  },

  renderApplicationSection(applications) {
    return `
      <div class="detail-card">
        <h5>Applications</h5>
        <h4>Fit by downstream use case</h4>
        ${applications.length ? applications.map((item) => `
          <div class="row-card explore-detail-row">
            <strong>${this.escape(item.name)}</strong>
            ${item.use_case ? `<p>${this.escape(item.use_case)}</p>` : ""}
            <div class="score-grid">
              <div><span>Match</span><strong>${this.escape(item.match_score)}</strong></div>
              <div><span>Sustainability</span><strong>${this.escape(item.sustainability_score)}</strong></div>
              <div><span>Supply chain</span><strong>${this.escape(item.supply_chain_score)}</strong></div>
            </div>
            ${item.connected_products?.length ? `<div class="tags">${item.connected_products.map((value) => `<span class="tag">${this.escape(value)}</span>`).join("")}</div>` : ""}
          </div>
        `).join("") : `<p>No application scoring available.</p>`}
      </div>`;
  },

  renderListSection(title, rows, keys) {
    return `
      <div class="detail-card">
        <h5>${this.escape(title)}</h5>
        ${rows.length ? rows.map((row) => `
          <div class="row-card explore-detail-row">
            ${keys.map((key, index) => row[key] ? `${index === 0 ? `<strong>${this.escape(row[key])}</strong>` : `<p>${this.escape(row[key])}</p>`}` : "").join("")}
          </div>
        `).join("") : `<p>No ${this.escape(title.toLowerCase())} linked right now.</p>`}
      </div>`;
  },

  renderSignalSection(title, rows) {
    return `
      <div class="detail-card">
        <h5>${this.escape(title)}</h5>
        <div class="key-facts">
          ${rows.map((row) => `
            <div class="fact">
              <span>${this.escape(row.label)}</span>
              <strong>${this.escape(row.value)}</strong>
            </div>
          `).join("")}
        </div>
      </div>`;
  },

  renderDetailMap(points) {
    if (!points.length) return "";
    return `
      <div class="detail-card">
        <h5>Map</h5>
        <h4>Supplier and buyer geography</h4>
        <div class="tags">
          ${points.map((point) => `<span class="tag">${this.escape(point.type)}: ${this.escape(point.label)} | ${this.escape(point.region)}</span>`).join("")}
        </div>
      </div>`;
  },

  renderDetailGraph(graph) {
    if (!graph.nodes?.length) return "";
    return `
      <div class="detail-card">
        <h5>Graph</h5>
        <h4>Scoped entity connections</h4>
        <div class="explore-detail-graph">
          <div class="explore-detail-graph-nodes">
            ${graph.nodes.map((node) => `<div class="row-card"><strong>${this.escape(node.label)}</strong><small>${this.escape(node.type)}</small></div>`).join("")}
          </div>
          <div class="explore-detail-graph-edges">
            ${graph.edges.map((edge) => `<div class="row-card"><strong>${this.escape(edge.label)}</strong><small>${this.escape(edge.source)} -> ${this.escape(edge.target)}</small></div>`).join("")}
          </div>
        </div>
      </div>`;
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

const state = {
  materials: [],
  suppliers: [],
  regulations: [],
  filteredMaterials: [],
  selectedMaterialId: null,
  selectedMaterialDetail: null,
  selectedGraphNodeId: null,
  compareResults: [],
  workspaces: [],
  investigations: [],
  scenarioHistory: [],
  analyticsOverview: null,
  currentInvestigationId: null,
  graphZoom: 1,
  graphPan: { x: 0, y: 0 },
  graphFilter: "all",
  graphPreset: "full",
  graphIsolateSelection: false,
  currentGraph: null,
  theme: "light",
  currentUser: null,
  currentPage: "overview",
};

function applyTheme(theme) {
  state.theme = theme;
  document.body.setAttribute("data-theme", theme);
  const button = document.getElementById("theme-toggle");
  if (button) button.textContent = theme === "dark" ? "Light mode" : "Dark mode";
  window.localStorage.setItem("packgraph-theme", theme);
}

function setupThemeToggle() {
  const savedTheme = window.localStorage.getItem("packgraph-theme");
  const preferredDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(savedTheme || (preferredDark ? "dark" : "light"));
  document.getElementById("theme-toggle").addEventListener("click", () => applyTheme(state.theme === "dark" ? "light" : "dark"));
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  return payload.data;
}

function formatTags(items, className = "tag") {
  return `<div class="tags">${items.map((item) => `<span class="${className}">${item}</span>`).join("")}</div>`;
}

function addMessage(author, text, detail = "") {
  const log = document.getElementById("chat-log");
  const message = document.createElement("div");
  const authorSlug = String(author).toLowerCase().replace(/\s+/g, "-");
  message.className = `message message-${authorSlug}`;
  message.innerHTML = `<strong>${author}</strong><div>${text}</div>${detail ? `<pre>${detail}</pre>` : ""}`;
  log.prepend(message);
}

function renderStructuredAnswer(panel) {
  if (window.PackGraphAnswerPanel) {
    window.PackGraphAnswerPanel.render(panel);
  }
}

function titleCase(value) {
  return String(value)
    .split(/[-_ ]+/)
    .filter(Boolean)
    .map((item) => item.charAt(0).toUpperCase() + item.slice(1))
    .join(" ");
}

function formatFilterLabel(value) {
  return value === undefined || value === null || value === "" ? "Any" : titleCase(String(value));
}

function riskClass(score) {
  if (score >= 68) return "risk-high";
  if (score >= 50) return "risk-medium";
  return "risk-low";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatEntityLabel(type) {
  const labels = {
    material: "Material",
    supplier: "Supplier",
    regulation: "Regulation",
    document: "Document",
    report: "Report",
    test_report: "Report",
  };
  return labels[type] || titleCase(type);
}

function renderTableCard(containerId, columns, rows, emptyText = "No records available.") {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = `<div class="table-empty">${escapeHtml(emptyText)}</div>`;
    return;
  }
  container.innerHTML = `
    <table>
      <thead>
        <tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            ${columns.map((column) => `<td>${column.render(row)}</td>`).join("")}
          </tr>
        `).join("")}
      </tbody>
    </table>`;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function applyGraphZoom() {
  const viewport = document.getElementById("graph-viewport");
  const zoomLabel = document.getElementById("graph-zoom-level");
  if (viewport) {
    viewport.style.transform = `translate(${state.graphPan.x}px, ${state.graphPan.y}px) scale(${state.graphZoom})`;
  }
  if (zoomLabel) {
    zoomLabel.textContent = `${Math.round(state.graphZoom * 100)}%`;
  }
}

function relationshipPriority(type) {
  const order = {
    SUPPLIED_BY: 1,
    SUPPLIES: 1,
    TARGETS_APPLICATION: 2,
    HAS_DOCUMENT: 3,
    REVIEWED_UNDER: 4,
    RECYCLES_INTO: 5,
    SUBSTITUTES_WITH: 6,
  };
  return order[type] || 99;
}

function relationshipLane(type) {
  const lanes = {
    TARGETS_APPLICATION: "applications",
    HAS_DOCUMENT: "documents",
    RECYCLES_INTO: "recycling",
    SUPPLIED_BY: "suppliers",
    SUPPLIES: "suppliers",
    SUBSTITUTES_WITH: "substitutes",
    REVIEWED_UNDER: "regulations",
  };
  return lanes[type] || "related";
}

function centerNodeAnchorOffset(type) {
  const offsets = {
    TARGETS_APPLICATION: -28,
    HAS_DOCUMENT: -4,
    RECYCLES_INTO: 24,
    SUPPLIED_BY: -20,
    SUBSTITUTES_WITH: 16,
    REVIEWED_UNDER: 34,
  };
  return offsets[type] || 0;
}

function graphEdgeAnchors(source, target) {
  const direction = target.x >= source.x ? 1 : -1;
  const edgeInset = 1;

  return {
    source: {
      x: source.x + (source.halfWidth - edgeInset) * direction,
      y: source.y,
    },
    target: {
      x: target.x - (target.halfWidth - edgeInset) * direction,
      y: target.y,
    },
  };
}

function measureGraphNodes(positions) {
  const metrics = {};
  document.querySelectorAll(".graph-node").forEach((node) => {
    const nodeId = node.dataset.nodeId;
    const position = positions[nodeId];
    if (!position) return;
    metrics[nodeId] = {
      x: position.x,
      y: position.y,
      halfWidth: node.offsetWidth / 2,
      halfHeight: node.offsetHeight / 2,
    };
  });
  return metrics;
}

function centeredStackPositions(count, centerY, gap, minY, maxY) {
  if (!count) return [];
  const totalHeight = gap * (count - 1);
  let startY = centerY - totalHeight / 2;
  startY = clamp(startY, minY, Math.max(minY, maxY - totalHeight));
  return Array.from({ length: count }, (_, index) => startY + index * gap);
}

function distributedPositions(count, start, end) {
  if (!count) return [];
  if (count === 1) return [(start + end) / 2];
  const span = end - start;
  return Array.from({ length: count }, (_, index) => start + (span * index) / (count - 1));
}

function graphGroupConfig(group) {
  const configs = {
    applications: { axis: "left", nodeX: 162, branchX: 360, startY: 118, endY: 228, label: "Targets application", labelY: 82 },
    documents: { axis: "left", nodeX: 162, branchX: 344, startY: 316, endY: 404, label: "Has document", labelY: 286 },
    recycling: { axis: "left", nodeX: 162, branchX: 328, startY: 486, endY: 548, label: "Recycles into", labelY: 458 },
    suppliers: { axis: "right", nodeX: 838, branchX: 642, startY: 118, endY: 228, label: "Supplied by", labelY: 82 },
    substitutes: { axis: "right", nodeX: 838, branchX: 666, startY: 332, endY: 560, label: "Substitutes with", labelY: 304 },
    regulations: { axis: "bottom", nodeY: 560, branchY: 472, centerX: 500, gap: 180, label: "Reviewed under" },
    related: { axis: "right", nodeX: 838, branchX: 666, startY: 332, endY: 560, label: "Related", labelY: 304 },
  };
  return configs[group] || configs.related;
}

function routeVerticalGroupPaths(sourceAnchor, branchX, targetAnchors) {
  const topY = Math.min(sourceAnchor.y, ...targetAnchors.map((anchor) => anchor.y));
  const bottomY = Math.max(sourceAnchor.y, ...targetAnchors.map((anchor) => anchor.y));
  return [
    `M ${sourceAnchor.x} ${sourceAnchor.y} L ${branchX} ${sourceAnchor.y} L ${branchX} ${topY} L ${branchX} ${bottomY}`,
    ...targetAnchors.map((anchor) => `M ${branchX} ${anchor.y} L ${anchor.x} ${anchor.y}`),
  ];
}

function routeBottomGroupPaths(sourceAnchor, branchY, targetAnchors) {
  const leftX = Math.min(sourceAnchor.x, ...targetAnchors.map((anchor) => anchor.x));
  const rightX = Math.max(sourceAnchor.x, ...targetAnchors.map((anchor) => anchor.x));
  return [
    `M ${sourceAnchor.x} ${sourceAnchor.y} L ${sourceAnchor.x} ${branchY} L ${leftX} ${branchY} L ${rightX} ${branchY}`,
    ...targetAnchors.map((anchor) => `M ${anchor.x} ${branchY} L ${anchor.x} ${anchor.y}`),
  ];
}

function normalizeGraphEdges(graph, selectedNodeId) {
  const visibleNodeIds = new Set(graph.nodes.map((node) => node.id));
  const normalized = [];
  const seen = new Set();
  const presetTypes = {
    full: null,
    supply: new Set(["SUPPLIED_BY", "SUPPLIES", "SUBSTITUTES_WITH"]),
    evidence: new Set(["HAS_DOCUMENT"]),
    compliance: new Set(["REVIEWED_UNDER", "SUBSTITUTES_WITH"]),
  };
  const allowedByPreset = presetTypes[state.graphPreset] || null;

  graph.edges.forEach((edge) => {
    if (edge.source !== selectedNodeId && edge.target !== selectedNodeId) return;
    if (state.graphFilter !== "all" && edge.type !== state.graphFilter && !(state.graphFilter === "SUPPLIED_BY" && edge.type === "SUPPLIES")) return;
    if (allowedByPreset && !allowedByPreset.has(edge.type) && !(edge.type === "SUPPLIES" && allowedByPreset.has("SUPPLIED_BY"))) return;
    const neighborId = edge.source === selectedNodeId ? edge.target : edge.source;
    if (!visibleNodeIds.has(neighborId)) return;

    let type = edge.type;
    if (type === "SUPPLIES") {
      type = "SUPPLIED_BY";
    }

    const key = `${type}:${neighborId}`;
    if (seen.has(key)) return;
    seen.add(key);
    normalized.push({
      source: selectedNodeId,
      target: neighborId,
      type,
    });
  });

  return normalized.sort((a, b) => relationshipPriority(a.type) - relationshipPriority(b.type) || a.target.localeCompare(b.target));
}

function layoutGraphNodes(nodes, edges, selectedNodeId) {
  const width = 1000;
  const height = 640;
  const centerX = width / 2;
  const centerY = height / 2;
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) || nodes[0];
  const positions = {};
  const branches = [];

  if (selectedNode) {
    positions[selectedNode.id] = { x: centerX, y: centerY };
  }

  const connectedEdges = edges
    .filter((edge) => edge.source === selectedNode?.id || edge.target === selectedNode?.id)
    .sort((a, b) => relationshipPriority(a.type) - relationshipPriority(b.type) || a.type.localeCompare(b.type));

  const grouped = connectedEdges.reduce((acc, edge) => {
    const type = edge.type;
    const neighborId = edge.source === selectedNode?.id ? edge.target : edge.source;
    const node = nodes.find((item) => item.id === neighborId);
    if (!node) return acc;
    if (!acc[type]) acc[type] = [];
    acc[type].push(node);
    return acc;
  }, {});

  Object.entries(grouped).forEach(([type, groupNodes]) => {
    const group = relationshipLane(type);
    const config = graphGroupConfig(group);
    const sortedNodes = [...groupNodes].sort((a, b) => a.label.localeCompare(b.label));

    if (config.axis === "bottom") {
      const xs = centeredStackPositions(sortedNodes.length, config.centerX, config.gap, 172, width - 172);
      branches.push({
        type,
        group,
        axis: config.axis,
        label: config.label,
        branchY: config.branchY,
        textX: centerX,
        textY: config.branchY - 14,
        textAnchor: "middle",
      });
      sortedNodes.forEach((node, index) => {
        positions[node.id] = {
          x: xs[index],
          y: config.nodeY,
        };
      });
      return;
    }

    const ys = distributedPositions(sortedNodes.length, config.startY, config.endY);
    const textX = config.axis === "left" ? config.branchX - 20 : config.branchX + 20;
    branches.push({
      type,
      group,
      axis: config.axis,
      label: config.label,
      branchX: config.branchX,
      textX,
      textY: config.labelY ?? ys[0] - 24,
      textAnchor: config.axis === "left" ? "end" : "start",
    });
    sortedNodes.forEach((node, index) => {
      positions[node.id] = {
        x: config.nodeX,
        y: ys[index],
      };
    });
  });

  return { positions, branches };
}

function renderGraphCanvas(graph) {
  const graphRootId = state.graphIsolateSelection ? state.selectedGraphNodeId : state.selectedMaterialId;
  const normalizedEdges = normalizeGraphEdges(graph, graphRootId);
  const visibleIds = new Set([graphRootId, ...normalizedEdges.flatMap((edge) => [edge.source, edge.target])]);
  const visibleNodes = graph.nodes.filter((node) => visibleIds.has(node.id));
  const { positions, branches } = layoutGraphNodes(visibleNodes, normalizedEdges, graphRootId);
  const edgesSvg = document.getElementById("graph-edges");
  const nodesLayer = document.getElementById("graph-nodes-layer");

  nodesLayer.innerHTML = visibleNodes.map((node) => {
    const position = positions[node.id];
    if (!position) return "";
    return `
      <button
        type="button"
        class="graph-node graph-node-${escapeHtml(node.type)}${node.id === state.selectedGraphNodeId ? " active" : ""}${node.id === graphRootId ? " center" : ""}"
        data-node-id="${node.id}"
        style="left:${position.x}px; top:${position.y}px;"
      >
        <span>${escapeHtml(titleCase(node.type))}</span>
        <strong>${escapeHtml(node.label)}</strong>
      </button>`;
  }).join("");

  const nodeMetrics = measureGraphNodes(positions);
  const branchByType = Object.fromEntries(branches.map((branch) => [branch.type, branch]));
  const edgesByType = normalizedEdges.reduce((acc, edge) => {
    if (!acc[edge.type]) acc[edge.type] = [];
    acc[edge.type].push(edge);
    return acc;
  }, {});

  edgesSvg.innerHTML = [
    ...branches.map((branch) => `<text class="graph-branch-label" x="${branch.textX}" y="${branch.textY}" text-anchor="${branch.textAnchor}">${escapeHtml(branch.label)}</text>`),
    ...Object.entries(edgesByType).flatMap(([type, branchEdges]) => {
      const branch = branchByType[type];
      if (!branch || !branchEdges.length) return [];

      const source = nodeMetrics[branchEdges[0].source];
      if (!source) return [];

      const targetAnchors = branchEdges
        .map((edge) => {
          const target = nodeMetrics[edge.target];
          if (!target) return null;
          return graphEdgeAnchors(source, target).target;
        })
        .filter(Boolean)
        .sort((a, b) => a.y - b.y);

      if (!targetAnchors.length) return [];

      const firstTarget = nodeMetrics[branchEdges[0].target];
      if (!firstTarget) return [];
      const sourceMetric = {
        ...source,
        y: source.y + centerNodeAnchorOffset(type),
      };
      const sourceAnchor = graphEdgeAnchors(sourceMetric, firstTarget).source;
      const isActive = branchEdges.some((edge) => edge.source === state.selectedGraphNodeId || edge.target === state.selectedGraphNodeId);

      const paths = branch.axis === "bottom"
        ? routeBottomGroupPaths(sourceAnchor, branch.branchY, targetAnchors)
        : routeVerticalGroupPaths(sourceAnchor, branch.branchX, targetAnchors);

      return paths.map((path) => `<path class="graph-edge${isActive ? " active" : ""}" d="${path}"></path>`);
    }),
  ].join("");

  applyGraphZoom();
}

async function openMaterial(materialId, page = "overview") {
  if (!materialId) return;
  state.selectedMaterialId = materialId;
  const select = document.getElementById("material-select");
  if (select) select.value = materialId;
  setPage(page);
  await refreshMaterialContext();
}

async function openSupplierProfile(supplierId) {
  const supplier = await fetchJson(`/suppliers/${encodeURIComponent(supplierId)}`);
  renderSupplierDetail(supplier);
  setPage("intelligence");
}

async function openRegulationDetail(regulationId) {
  const regulation = await fetchJson(`/regulations/${encodeURIComponent(regulationId)}`);
  renderRegulationDetail(regulation);
  setPage("intelligence");
}

function addMaterialToShortlist(materialId) {
  const compare = document.getElementById("compare-materials");
  if (!compare) return;
  const option = Array.from(compare.options).find((item) => item.value === materialId);
  if (!option) return;
  option.selected = true;
  renderCompareSelectionSummary();
}

function bindInlineActions() {
  document.querySelectorAll("[data-select-material]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openMaterial(button.dataset.selectMaterial, "overview");
    });
  });
  document.querySelectorAll("[data-open-graph]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openMaterial(button.dataset.openGraph, "intelligence");
    });
  });
  document.querySelectorAll("[data-shortlist-material]").forEach((button) => {
    button.addEventListener("click", () => {
      addMaterialToShortlist(button.dataset.shortlistMaterial);
      setPage("workbench");
    });
  });
  document.querySelectorAll("[data-compare-material]").forEach((button) => {
    button.addEventListener("click", async () => {
      addMaterialToShortlist(button.dataset.compareMaterial);
      setPage("workbench");
      await runComparison();
    });
  });
  document.querySelectorAll("[data-run-scenario]").forEach((button) => {
    button.addEventListener("click", async () => {
      setPage("workbench");
      document.getElementById("scenario-type").value = button.dataset.runScenario;
      if (window.PackGraphWorkbenchPanels) {
        window.PackGraphWorkbenchPanels.applyScenarioVisibility(button.dataset.runScenario);
      }
      await runScenario();
    });
  });
  document.querySelectorAll("[data-open-supplier]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openSupplierProfile(button.dataset.openSupplier);
    });
  });
  document.querySelectorAll("[data-open-regulation]").forEach((button) => {
    button.addEventListener("click", async () => {
      await openRegulationDetail(button.dataset.openRegulation);
    });
  });
  document.querySelectorAll("[data-export-material]").forEach((button) => {
    button.addEventListener("click", () => {
      const materialId = button.dataset.exportMaterial;
      window.open(`/exports/executive-summary.pdf?material_id=${encodeURIComponent(materialId)}`, "_blank", "noopener");
    });
  });
}

function selectedMaterialsFromCompare() {
  return Array.from(document.getElementById("compare-materials").selectedOptions).map((option) => option.value);
}

function selectedMaterialRecordsFromCompare() {
  const ids = selectedMaterialsFromCompare();
  return ids.map((id) => state.materials.find((item) => item.material_id === id)).filter(Boolean);
}

function renderCompareSelectionSummary() {
  const container = document.getElementById("compare-selection-summary");
  if (!container) return;
  const selected = selectedMaterialRecordsFromCompare();
  container.innerHTML = selected.length
    ? selected.map((item) => `<span class="pill">${escapeHtml(item.name)}</span>`).join("")
    : `<span class="pill">No shortlist selected yet</span>`;
}

function populateMaterialControls(materials) {
  const select = document.getElementById("material-select");
  const compare = document.getElementById("compare-materials");
  select.innerHTML = materials.map((item) => `<option value="${item.material_id}">${item.name}</option>`).join("");
  compare.innerHTML = state.materials.map((item) => `<option value="${item.material_id}">${item.name}</option>`).join("");
  if (!materials.find((item) => item.material_id === state.selectedMaterialId)) {
    state.selectedMaterialId = materials[0]?.material_id || state.materials[0]?.material_id;
  }
  select.value = state.selectedMaterialId;
  const currentSelections = selectedMaterialsFromCompare();
  const fallbackSelections = currentSelections.length ? currentSelections : state.materials.slice(0, 3).map((item) => item.material_id);
  Array.from(compare.options).forEach((option) => {
    option.selected = fallbackSelections.includes(option.value);
  });
  renderCompareSelectionSummary();
}

function setPage(pageName) {
  state.currentPage = pageName;
  document.body.setAttribute("data-page", pageName);
  document.querySelectorAll(".page-link").forEach((button) => button.classList.toggle("active", button.dataset.page === pageName));
  document.querySelectorAll(".page-section").forEach((section) => section.classList.toggle("active", section.dataset.page === pageName));
  const pageCard = document.getElementById("page-context-card");
  if (pageCard) {
    const descriptions = {
      overview: "Core decision flow: filters, material detail, chat, compliance.",
      workbench: "Shortlist workflow: ranking, provenance, investigations, workspaces.",
      intelligence: "Support layer: graph, alerts, analytics, and benchmarks.",
    };
    pageCard.innerHTML = `<span>Current page</span><strong>${titleCase(pageName)}</strong><small>${descriptions[pageName]}</small>`;
  }
}

async function loadSession() {
  state.currentUser = await fetchJson("/auth/session");
}

async function loadMaterials() {
  const payload = await fetch("/materials");
  const body = await payload.json();
  state.materials = body.data;
  state.suppliers = await fetchJson("/suppliers");
  state.regulations = await fetchJson("/regulations");
  state.filteredMaterials = [...state.materials];
  state.selectedMaterialId = state.materials[0]?.material_id;
  state.selectedGraphNodeId = state.selectedMaterialId;
  populateMaterialControls(state.materials);
  populateFilterOptions();
  document.getElementById("material-select").addEventListener("change", async (event) => {
    state.selectedMaterialId = event.target.value;
    await refreshMaterialContext();
  });
  await refreshMaterialContext();
}

function populateFilterOptions() {
  const regions = [...new Set(state.materials.flatMap((item) => item.regions_available))].sort();
  const categories = [...new Set(state.materials.map((item) => item.category))].sort();
  const regulations = state.regulations || [];
  document.getElementById("filter-region").innerHTML = `<option value="">All regions</option>${regions.map((item) => `<option value="${item}">${item}</option>`).join("")}`;
  document.getElementById("filter-category").innerHTML = `<option value="">All categories</option>${categories.map((item) => `<option value="${item}">${titleCase(item)}</option>`).join("")}`;
  document.getElementById("filter-regulation").innerHTML = `<option value="">Any regulation</option>${regulations.map((item) => `<option value="${item.regulation_id}">${item.name}</option>`).join("")}`;
}

async function refreshMaterialContext() {
  await Promise.all([loadMaterialDetail(), loadProvenance(), loadGraph(), loadMaterialTimeline()]);
}

async function loadMaterialDetail() {
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  state.selectedMaterialDetail = material;
  document.getElementById("context-material").textContent = material.name;
  document.getElementById("overview-selected-material").textContent = material.name;
  document.getElementById("overview-selected-material-note").textContent = `${titleCase(material.category)} material across ${material.regions_available.length} regions with ${material.supplier_ids.length} qualified suppliers in the demo graph.`;
  document.getElementById("material-title").textContent = `${material.name} (${material.category})`;
  const supplierNames = material.suppliers.map((item) => item.name);
  const substitutes = material.substitute_material_ids.map((id) => state.materials.find((entry) => entry.material_id === id)?.name || id);
  document.getElementById("material-detail").innerHTML = `
    <div class="detail-primary overview-detail-primary">
      <div class="detail-card">
        <h5>Profile</h5>
        <h4>Current candidate</h4>
        <p>${material.composition}</p>
        ${formatTags(material.regions_available)}
        <div class="key-facts">
          <div class="fact"><span>Descriptor</span><strong>${titleCase(material.descriptor)}</strong></div>
          <div class="fact"><span>Food contact</span><strong>${material.food_contact_safe ? "Approved profile" : "Review required"}</strong></div>
          <div class="fact"><span>Applications</span><strong>${material.target_applications.length} active targets</strong></div>
          <div class="fact"><span>Suppliers</span><strong>${material.supplier_ids.length} qualified sources</strong></div>
        </div>
      </div>
      <div class="detail-card overview-metric-card">
        <h5>Key indicators</h5>
        <h4>Decision snapshot</h4>
        <div class="overview-metric-grid">
          <div class="metric"><div class="value">${material.sustainability_score}</div><div>Sustainability</div></div>
          <div class="metric"><div class="value">${material.recyclability_score}</div><div>Recyclability</div></div>
          <div class="metric"><div class="value">${material.compostability_score}</div><div>Compostability</div></div>
          <div class="metric"><div class="value">${material.cost_range.low}-${material.cost_range.high}</div><div>${material.cost_range.currency} / kg</div></div>
        </div>
      </div>
    </div>
    <div class="detail-secondary overview-detail-secondary">
      <div class="detail-card">
        <h5>Compliance view</h5>
        <h4>State and substitutes</h4>
        <p>Current state: <strong>${titleCase(material.compliance_state)}</strong></p>
        ${formatTags((material.compliance_flags.length ? material.compliance_flags : ["compliant profile"]).map(titleCase))}
        <div class="subsection">
          <div class="subsection-heading">Substitute materials</div>
          ${formatTags(substitutes)}
        </div>
      </div>
      <div class="detail-card">
        <h5>Qualified supply</h5>
        <h4>Available suppliers</h4>
        ${supplierNames.map((name) => `<div class="score-row"><span>${name}</span><strong>Available</strong></div>`).join("")}
      </div>
    </div>`;
  updateExportLinks(material);
  populateScenarioControls(material);
}

async function loadProvenance(searchQuery = "") {
  const material = await fetchJson(`/materials/${state.selectedMaterialId}`);
  document.getElementById("provenance-panel").innerHTML = `
    <div class="detail-card">
      <h4>Documents</h4>
      ${material.documents.map((doc) => `<div class="row-card"><strong>${doc.title}</strong><p>${titleCase(doc.document_type)}</p><small>Provenance score ${doc.provenance_score} / issued ${doc.issued_on}</small>${doc.extraction_summary ? `<p>${escapeHtml(doc.extraction_summary)}</p>` : ""}</div>`).join("")}
    </div>
    <div class="detail-card">
      <h4>Test reports</h4>
      ${material.test_reports.map((report) => `<div class="row-card"><strong>${report.title}</strong><p>${report.lab}</p><small>Migration ${report.migration_status} / test date ${report.test_date}</small>${report.extraction_summary ? `<p>${escapeHtml(report.extraction_summary)}</p>` : ""}</div>`).join("")}
    </div>`;
  if (searchQuery) {
    const results = await fetchJson(`/documents/search?query=${encodeURIComponent(searchQuery)}&material_id=${state.selectedMaterialId}`);
    renderTableCard(
      "document-search-results",
      [
        { label: "Evidence", render: (item) => `<strong>${escapeHtml(item.title || item.report_id || "Evidence")}</strong>` },
        { label: "Type", render: (item) => escapeHtml(titleCase(item.type)) },
        { label: "Detail", render: (item) => escapeHtml(item.document_type || item.lab || item.migration_status || "") },
        {
          label: "Actions",
          render: (item) => `
            <div class="action-row">
              <button type="button" class="mini-action" data-open-graph="${escapeHtml(item.material_id || state.selectedMaterialId)}">Open in graph</button>
              <button type="button" class="mini-action" data-export-material="${escapeHtml(item.material_id || state.selectedMaterialId)}">Export</button>
            </div>`,
        },
      ],
      results,
      "Try another search phrase or review the reference evidence for the selected material."
    );
    bindInlineActions();
    if (window.PackGraphWorkbenchPanels) {
      window.PackGraphWorkbenchPanels.renderEvidenceExtraction(results);
    }
  } else {
    document.getElementById("document-search-results").innerHTML = `<div class="table-empty">Search evidence to narrow the proof set for the selected material.</div>`;
    if (window.PackGraphWorkbenchPanels) {
      window.PackGraphWorkbenchPanels.renderEvidenceExtraction([...(material.documents || []), ...(material.test_reports || [])]);
    }
  }
}

async function loadCompliance() {
  const dashboard = await fetchJson("/compliance/dashboard");
  document.getElementById("compliance-summary").innerHTML = `
    <div class="metric"><div class="value">${dashboard.watch_count}</div><div>materials under review</div></div>
    <div class="metric"><div class="value">${dashboard.non_compliant_count}</div><div>materials out of bounds</div></div>`;
  document.getElementById("regulation-list").innerHTML = dashboard.upcoming_regulations.map((item) => `<span class="pill">${item.name}</span>`).join("");
  renderTableCard(
    "compliance-risk-list",
    [
      { label: "Material", render: (item) => `<strong>${escapeHtml(item.name)}</strong>` },
      { label: "Supplier risk", render: (item) => escapeHtml(String(item.supplier_risk_score)) },
      {
        label: "Actions",
        render: (item) => `
          <div class="action-row">
            <button type="button" class="mini-action" data-select-material="${escapeHtml(item.material_id)}">Open</button>
            <button type="button" class="mini-action" data-run-scenario="supplier_outage">Run scenario</button>
          </div>`,
      },
    ],
    dashboard.at_risk_materials.slice(0, 5),
    "No supplier exposure hotspots right now."
  );
  bindInlineActions();
  document.getElementById("hero-risk-count").textContent = dashboard.at_risk_materials.length;
  document.getElementById("hero-regulations").textContent = dashboard.upcoming_regulations.length;
}

async function loadAlerts() {
  const alerts = await fetchJson("/alerts");
  document.getElementById("context-alerts").textContent = alerts.length;
  renderTableCard(
    "alerts-list",
    [
      { label: "Alert", render: (item) => `<strong>${escapeHtml(item.title)}</strong><br /><small>${escapeHtml(item.detail)}</small>` },
      { label: "Severity", render: (item) => `<span class="${riskClass(item.severity === "high" ? 80 : item.severity === "medium" ? 58 : 32)}">${escapeHtml(titleCase(item.severity))}</span>` },
      { label: "Category", render: (item) => `<span class="table-badge">${escapeHtml(titleCase(item.category))}</span>` },
    ],
    alerts,
    "No active alerts."
  );
}

async function uploadDocumentEvidence() {
  const fileInput = document.getElementById("document-upload-file");
  const status = document.getElementById("document-upload-status");
  const file = fileInput.files[0];
  if (!file) {
    status.textContent = "Choose a file before uploading evidence.";
    return;
  }
  const formData = new FormData();
  formData.set("file", file);
  formData.set("document_type", document.getElementById("document-upload-type").value);
  formData.set("material_id", state.selectedMaterialId);
  const title = document.getElementById("document-upload-title").value.trim();
  if (title) formData.set("title", title);

  const response = await fetch("/documents/upload", {
    method: "POST",
    body: formData,
  });
  const payload = await response.json();
  if (!response.ok || payload.status !== "ok") {
    status.textContent = payload.detail || payload.error || "Upload failed.";
    status.className = "upload-status status-error";
    return;
  }
  status.textContent = `Uploaded ${payload.data.record.title}. Extraction linked to ${state.selectedMaterialId}.`;
  status.className = "upload-status status-success";
  document.getElementById("document-upload-title").value = "";
  fileInput.value = "";
  await Promise.all([loadProvenance(document.getElementById("document-search-input").value.trim()), loadAlerts(), loadGraph()]);
}

async function loadInvestigations() {
  const investigations = await fetchJson("/investigations");
  state.investigations = investigations;
  document.getElementById("context-investigations").textContent = investigations.length;
  document.getElementById("hero-investigations").textContent = investigations.length;
  if (window.PackGraphWorkbenchPanels) {
    window.PackGraphWorkbenchPanels.renderInvestigations(investigations, resumeInvestigation);
  }
}

async function loadWorkspaces() {
  const workspaces = await fetchJson("/workspaces");
  state.workspaces = workspaces;
  if (window.PackGraphWorkbenchPanels) {
    window.PackGraphWorkbenchPanels.renderWorkspaces(workspaces, resumeWorkspace);
  }
}

async function loadScenarioHistory() {
  const history = await fetchJson("/scenarios/history");
  state.scenarioHistory = history;
  renderTableCard(
    "scenario-history",
    [
      { label: "Scenario", render: (item) => `<strong>${escapeHtml(titleCase(item.scenario_type))}</strong>` },
      {
        label: "Before",
        render: (item) => escapeHtml(
          `${item.before.material_id || "portfolio"} | ${item.before.supplier_id || item.before.options?.regulation_id || "auto"}`
        ),
      },
      {
        label: "After",
        render: (item) => `<div><strong>${escapeHtml(item.after.summary || "Completed")}</strong><br /><small>${escapeHtml(JSON.stringify(item.after.metrics || {}))}</small></div>`,
      },
    ],
    history.slice(0, 8),
    "Run a scenario to build a history of before/after outcomes."
  );
}

async function loadGraph() {
  const graph = await fetchJson(`/graph/subgraph?material_id=${state.selectedMaterialId}`);
  state.currentGraph = graph;
  const graphNodeIds = new Set(graph.nodes.map((node) => node.id));
  if (!graphNodeIds.has(state.selectedGraphNodeId)) {
    state.selectedGraphNodeId = state.selectedMaterialId;
  }
  renderGraphCanvas(graph);
  const selectors = [document.getElementById("graph-source"), document.getElementById("graph-target")];
  selectors.forEach((select) => {
    select.innerHTML = graph.nodes.map((node) => `<option value="${node.id}">${node.label}</option>`).join("");
  });
  document.getElementById("graph-source").value = state.selectedGraphNodeId;
  document.getElementById("graph-target").value = graph.nodes.find((node) => node.id !== state.selectedGraphNodeId)?.id || state.selectedGraphNodeId;
  document.querySelectorAll(".graph-node").forEach((button) => {
    button.classList.toggle("active", button.dataset.nodeId === state.selectedGraphNodeId);
    button.addEventListener("click", async () => {
      await selectGraphNode(button.dataset.nodeId);
    });
  });
  const links = await fetchJson(`/graph/relationships?material_id=${state.selectedMaterialId}`);
  document.getElementById("relationship-list").innerHTML = links.slice(0, 14).map((item) => `<div class="row-card relationship-row"><span>${item.from}</span><strong>${titleCase(item.type)}</strong><span>${item.to}</span></div>`).join("");
  await loadGraphNodeInsight(state.selectedGraphNodeId);
}

async function loadGraphPath() {
  const sourceId = document.getElementById("graph-source").value;
  const targetId = document.getElementById("graph-target").value;
  const result = await fetchJson(`/graph/path?source_id=${sourceId}&target_id=${targetId}`);
  document.getElementById("graph-path-results").innerHTML = result.path.length
    ? result.path.map((node, index) => `<div class="row-card"><strong>${index + 1}. ${node.label}</strong><p>${titleCase(node.type)}</p></div>`).join("")
    : `<div class="row-card"><strong>No path found</strong><p>Try another source or target node.</p></div>`;
}

async function loadRecommendationsSummary() {
  const recommendations = await fetchJson("/query/recommendations?prioritize_sustainability=true");
  document.getElementById("hero-recommendations").textContent = recommendations.length;
}

async function runComparison() {
  const payload = {
    material_ids: selectedMaterialsFromCompare(),
    weights: {
      sustainability_score: Number(document.getElementById("weight-sustainability").value),
      recyclability_score: Number(document.getElementById("weight-recyclability").value),
      compostability_score: Number(document.getElementById("weight-compostability").value),
      oxygen_barrier: Number(document.getElementById("weight-barrier").value),
      moisture_barrier: Number(document.getElementById("weight-barrier").value),
      cost_efficiency: Number(document.getElementById("weight-cost").value),
    },
  };
  const results = await fetchJson("/materials/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.compareResults = results;
  document.getElementById("compare-results").innerHTML = results.length
    ? results.map((item, index) => `
      <div class="row-card compare-result-card">
        <div class="compare-result-rank">Rank ${index + 1}</div>
        <strong>${item.name}</strong>
        <p>Weighted score ${item.weighted_score}</p>
        <small>${index === 0 ? "Current leader based on active weights." : index === 1 ? "Closest alternative with a plausible tradeoff profile." : "Useful fallback if the leading options are blocked."}</small>
        <div class="tag-group">
          <span class="pill">Sustainability ${item.scores.sustainability}</span>
          <span class="pill">Recyclability ${item.scores.recyclability}</span>
          <span class="pill">Cost ${item.scores.cost_efficiency}</span>
        </div>
        <div class="action-row">
          <button type="button" class="mini-action" data-select-material="${escapeHtml(item.material_id)}">Open</button>
          <button type="button" class="mini-action" data-open-graph="${escapeHtml(item.material_id)}">Open in graph</button>
          <button type="button" class="mini-action" data-run-scenario="supplier_outage">Run scenario</button>
          <button type="button" class="mini-action" data-export-material="${escapeHtml(item.material_id)}">Export</button>
        </div>
      </div>`).join("")
    : `<div class="row-card"><strong>No ranked output</strong><p>Select at least one shortlisted material and run the ranking.</p></div>`;
  if (window.PackGraphWorkbenchPanels) {
    window.PackGraphWorkbenchPanels.renderComparisonMatrix(results);
  }
  bindInlineActions();
}

async function loadGraphNodeInsight(nodeId) {
  const insight = await fetchJson(`/graph/node-insight?node_id=${encodeURIComponent(nodeId)}`);
  renderGraphNodeInsight(insight);
  if (insight.node.type === "supplier") {
    const supplier = await fetchJson(`/suppliers/${encodeURIComponent(nodeId)}`);
    renderSupplierDetail(supplier);
  } else {
    renderSupplierDetail(null);
  }
  if (insight.node.type === "regulation") {
    const regulation = await fetchJson(`/regulations/${encodeURIComponent(nodeId)}`);
    renderRegulationDetail(regulation);
  } else {
    renderRegulationDetail(null);
  }
}

function renderGraphNodeInsight(insight) {
  document.getElementById("insight-title").textContent = `${insight.node.label} (${titleCase(insight.node.type)})`;
  document.getElementById("insight-summary").textContent = insight.summary;
  document.getElementById("analytics-summary").innerHTML = (insight.metrics || [])
    .map((item) => `<div class="metric"><div class="value">${escapeHtml(item.value)}</div><div>${escapeHtml(item.label)}</div></div>`)
    .join("");

  document.getElementById("analytics-details").innerHTML = (insight.facts || []).length
    ? insight.facts.map((item) => `<div class="row-card"><strong>${escapeHtml(item.label)}</strong><p>${escapeHtml(item.value)}</p></div>`).join("")
    : `<div class="row-card"><strong>No additional details</strong><p>This node does not expose extra structured fields in the demo dataset.</p></div>`;

  const relationshipCards = [];
  (insight.relationship_counts || []).slice(0, 4).forEach((item) => {
    relationshipCards.push(`<div class="row-card"><strong>${escapeHtml(item.label)}</strong><p>${escapeHtml(item.value)} connected edges</p></div>`);
  });
  (insight.timeline || []).slice(0, 4).forEach((item) => {
    relationshipCards.push(`<div class="row-card"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.detail)}</p><small>${escapeHtml(item.meta || "")}</small></div>`);
  });
  document.getElementById("analytics-relationships").innerHTML = relationshipCards.length
    ? relationshipCards.join("")
    : `<div class="row-card"><strong>No recent signal</strong><p>This node currently has no timeline or relationship mix details.</p></div>`;

  document.getElementById("analytics-related").innerHTML = (insight.related || []).length
    ? `
      <table>
        <thead><tr><th>Connected node</th><th>Type</th><th>Relationship</th></tr></thead>
        <tbody>
        ${insight.related.map((item) => `
          <tr>
            <td><button type="button" class="table-link-button" data-node-id="${escapeHtml(item.id)}">${escapeHtml(item.label)}</button></td>
            <td>${escapeHtml(titleCase(item.type))}</td>
            <td>${escapeHtml(titleCase(item.relationship))}</td>
          </tr>`).join("")}
        </tbody>
      </table>`
    : `<table><tbody><tr><td>No connected nodes available for this selection.</td></tr></tbody></table>`;

  document.querySelectorAll("#analytics-related [data-node-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      await selectGraphNode(button.dataset.nodeId);
    });
  });
}

async function selectGraphNode(nodeId) {
  state.selectedGraphNodeId = nodeId;
  const sourceSelect = document.getElementById("graph-source");
  if (sourceSelect) {
    sourceSelect.value = nodeId;
  }
  document.querySelectorAll(".graph-node").forEach((button) => {
    button.classList.toggle("active", button.dataset.nodeId === nodeId);
  });
  await loadGraphNodeInsight(nodeId);
}

async function loadAnalytics() {
  if (state.selectedGraphNodeId) {
    await loadGraphNodeInsight(state.selectedGraphNodeId);
  }
}

async function runGlobalSearch() {
  const input = document.getElementById("global-search-input");
  const status = document.getElementById("global-search-status");
  const query = input.value.trim();
  if (!query) {
    status.textContent = "Type something to search.";
    status.className = "upload-status status-error";
    renderTableCard("global-search-results", [], [], "Search across materials, suppliers, regulations, documents, and reports.");
    return;
  }
  const results = await fetchJson(`/search/global?query=${encodeURIComponent(query)}`);
  status.textContent = results.length ? `Found ${results.length} matching records.` : "No matches found.";
  status.className = `upload-status ${results.length ? "status-success" : ""}`;
  renderTableCard(
    "global-search-results",
    [
      { label: "Type", render: (item) => `<span class="table-badge">${escapeHtml(formatEntityLabel(item.entity_type))}</span>` },
      { label: "Result", render: (item) => `<strong>${escapeHtml(item.title)}</strong><br /><small>${escapeHtml(item.subtitle)}</small>` },
      { label: "Context", render: (item) => escapeHtml(item.meta || "") },
      {
        label: "Actions",
        render: (item) => {
          if (item.entity_type === "material") {
            return `
              <div class="action-row">
                <button type="button" class="mini-action" data-select-material="${escapeHtml(item.entity_id)}">Open</button>
                <button type="button" class="mini-action" data-compare-material="${escapeHtml(item.entity_id)}">Compare</button>
                <button type="button" class="mini-action" data-shortlist-material="${escapeHtml(item.entity_id)}">Shortlist</button>
                <button type="button" class="mini-action" data-open-graph="${escapeHtml(item.entity_id)}">Graph</button>
              </div>`;
          }
          if (item.entity_type === "supplier") {
            return `<div class="action-row"><button type="button" class="mini-action" data-open-supplier="${escapeHtml(item.entity_id)}">Open supplier</button></div>`;
          }
          if (item.entity_type === "regulation") {
            return `<div class="action-row"><button type="button" class="mini-action" data-open-regulation="${escapeHtml(item.entity_id)}">Open regulation</button></div>`;
          }
          const fallbackMaterial = item.entity_type === "report" || item.entity_type === "document" ? state.selectedMaterialId : "";
          return `<div class="action-row"><button type="button" class="mini-action" data-open-graph="${escapeHtml(fallbackMaterial)}">Open context</button></div>`;
        },
      },
    ],
    results,
    "No matches found."
  );
  bindInlineActions();
}

async function loadBenchmarks() {
  if (!document.getElementById("benchmark-status")) {
    return;
  }
  const data = await fetchJson("/benchmarks");
  const neo4jStatus = data.neo4j?.status || data.status || "not-run";
  const memgraphStatus = data.memgraph?.status || "not-run";
  document.getElementById("benchmark-status").innerHTML = `
    <div class="metric"><div class="value">${titleCase(neo4jStatus)}</div><div>Neo4j benchmark state</div></div>
    <div class="metric"><div class="value">${titleCase(memgraphStatus)}</div><div>Memgraph benchmark state</div></div>`;
  document.getElementById("benchmark-query-set").innerHTML = (data.query_set || []).map((item) => `<div class="row-card"><strong>${item.query}</strong><p>${item.note}</p></div>`).join("");
  document.getElementById("benchmark-plan-notes").innerHTML = (data.query_plan_notes || data.notes || []).map((item) => `<div class="row-card"><p>${item.note || item}</p></div>`).join("");
}

async function applyFilters() {
  const search = document.getElementById("filter-search").value.trim();
  const family = document.getElementById("filter-family").value.trim();
  const region = document.getElementById("filter-region").value;
  const category = document.getElementById("filter-category").value;
  const regulation = document.getElementById("filter-regulation").value;
  const claim = document.getElementById("filter-claim").value;
  const compliance = document.getElementById("filter-compliance").value;
  const performanceMetric = document.getElementById("filter-performance-metric").value;
  const performanceScore = document.getElementById("filter-performance-score").value;
  const supplierCapability = document.getElementById("filter-supplier-capability").value.trim();
  const sustainability = document.getElementById("filter-sustainability").value;
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (family) params.set("material_family", family);
  if (region) params.set("region", region);
  if (category) params.set("category", category);
  if (regulation) params.set("regulation_id", regulation);
  if (claim) params.set("claim_type", claim);
  if (compliance) params.set("compliance_state", compliance);
  if (performanceMetric) params.set("performance_metric", performanceMetric);
  if (performanceScore) params.set("min_performance_score", performanceScore);
  if (supplierCapability) params.set("supplier_capability", supplierCapability);
  if (sustainability) params.set("min_sustainability", sustainability);
  const results = await fetchJson(`/materials/filter?${params.toString()}`);
  state.filteredMaterials = results;
  populateMaterialControls(results.length ? results : state.materials);
  document.getElementById("filter-results-summary").textContent = results.length ? `Showing ${results.length} filtered materials` : "No materials matched. Reverting to full portfolio.";
  if (!results.length) state.filteredMaterials = [];
  await refreshMaterialContext();
}

function updateExportLinks(material) {
  const supplierIds = (material.suppliers || []).map((item) => item.supplier_id).join(",");
  document.getElementById("export-executive-summary-pdf").href = `/exports/executive-summary.pdf?material_id=${encodeURIComponent(material.material_id)}`;
  document.getElementById("export-executive-summary-csv").href = `/exports/executive-summary.csv?material_id=${encodeURIComponent(material.material_id)}`;
  document.getElementById("export-compliance-pack-csv").href = `/exports/compliance-pack.csv?material_id=${encodeURIComponent(material.material_id)}`;
  document.getElementById("export-compliance-pack-pdf").href = `/exports/compliance-pack.pdf?material_id=${encodeURIComponent(material.material_id)}`;
  document.getElementById("export-supplier-snapshot-pdf").href = `/exports/supplier-comparison.pdf?supplier_ids=${encodeURIComponent(supplierIds)}`;
  document.getElementById("export-supplier-snapshot-csv").href = `/exports/supplier-comparison.csv?supplier_ids=${encodeURIComponent(supplierIds)}`;
}

function populateScenarioControls(material) {
  const supplierSelect = document.getElementById("scenario-supplier");
  const regulationSelect = document.getElementById("scenario-regulation");
  if (!supplierSelect || !regulationSelect) return;

  const suppliers = material?.suppliers || [];
  supplierSelect.innerHTML = `<option value="">Auto from selected material</option>${suppliers.map((item) => `<option value="${item.supplier_id}">${item.name}</option>`).join("")}`;
  regulationSelect.innerHTML = `<option value="">Next pending regulation</option>${(state.regulations || []).map((item) => `<option value="${item.regulation_id}">${item.name}</option>`).join("")}`;
  if (window.PackGraphWorkbenchPanels) {
    window.PackGraphWorkbenchPanels.applyScenarioVisibility(document.getElementById("scenario-type")?.value || "supplier_outage");
  }
}

function formatScenarioMetricValue(value) {
  if (value === null || value === undefined || value === "") return "n/a";
  if (typeof value === "object") return escapeHtml(JSON.stringify(value));
  return escapeHtml(String(value));
}

function renderScenarioResult(result) {
  document.getElementById("scenario-summary").textContent = result.summary || "Scenario completed.";
  const metrics = result.metrics || {};
  document.getElementById("scenario-metrics").innerHTML = Object.keys(metrics).length
    ? Object.entries(metrics).map(([key, value]) => `<div class="metric"><div class="value">${formatScenarioMetricValue(value)}</div><div>${escapeHtml(titleCase(key))}</div></div>`).join("")
    : `<div class="metric"><div class="value">No metrics</div><div>Projected summary</div></div>`;

  document.getElementById("scenario-actions").innerHTML = (result.actions || []).length
    ? result.actions.map((item) => `<div class="row-card"><strong>${escapeHtml(item)}</strong></div>`).join("")
    : `<div class="row-card"><strong>No follow-up actions</strong><p>This scenario returned no recommended operational steps.</p></div>`;

  document.getElementById("scenario-impacts").innerHTML = (result.impacts || []).length
    ? result.impacts.map((item) => {
      const rows = Object.entries(item)
        .filter(([key]) => key !== "recommended_substitutes")
        .map(([key, value]) => `<div class="score-row"><span>${escapeHtml(titleCase(key))}</span><strong>${formatScenarioMetricValue(value)}</strong></div>`)
        .join("");
      const substitutes = Array.isArray(item.recommended_substitutes) && item.recommended_substitutes.length
        ? `<div class="tag-group">${item.recommended_substitutes.map((entry) => `<span class="pill">${escapeHtml(typeof entry === "string" ? entry : entry.name)}</span>`).join("")}</div>`
        : "";
      return `<div class="row-card">${rows}${substitutes}</div>`;
    }).join("")
    : `<div class="row-card"><strong>No impacted records</strong><p>This scenario did not change any material status in the current dataset.</p></div>`;
}

function renderSupplierDetail(supplier) {
  const container = document.getElementById("supplier-detail-panel");
  if (!container) return;
  if (!supplier) {
    container.innerHTML = `<div class="detail-card"><p>Select or search a supplier to open the drilldown.</p></div>`;
    return;
  }
  container.innerHTML = `
    <div class="detail-card">
      <h5>${escapeHtml(supplier.name)}</h5>
      <h4>${escapeHtml(supplier.country)} supplier profile</h4>
      <div class="key-facts">
        <div class="fact"><span>Lead time</span><strong>${escapeHtml(supplier.lead_time_days)} days</strong></div>
        <div class="fact"><span>Risk</span><strong>${escapeHtml(supplier.disruption_risk_score)}</strong></div>
        <div class="fact"><span>ESG</span><strong>${escapeHtml(supplier.esg_score)}</strong></div>
        <div class="fact"><span>Materials</span><strong>${escapeHtml(supplier.supplied_materials.length)}</strong></div>
      </div>
      <div class="trend-chip-grid">
        ${(supplier.certifications_detail || []).map((item) => `<span class="trend-chip">${escapeHtml(item.name)}</span>`).join("")}
      </div>
    </div>
    <div class="detail-card">
      <h5>Trends</h5>
      <h4>Risk and lead time</h4>
      <div class="timeline-chart-footer">
        <span>${(supplier.risk_trend || []).map((item) => `${item.quarter}: risk ${item.risk_score}`).join(" | ") || "No risk trend available."}</span>
      </div>
      <div class="timeline-chart-footer">
        <span>${(supplier.lead_time_trend || []).map((item) => `${item.quarter}: ${item.lead_time_days}d`).join(" | ") || "No lead-time trend available."}</span>
      </div>
      <div class="subsection-heading">Supplied materials</div>
      <div class="card-list compact-list">
        ${(supplier.supplied_materials || []).slice(0, 6).map((item) => `<div class="row-card"><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.category)} | ${escapeHtml(item.compliance_state)}</p></div>`).join("")}
      </div>
    </div>`;
}

function renderRegulationDetail(regulation) {
  const container = document.getElementById("regulation-detail-panel");
  if (!container) return;
  if (!regulation) {
    container.innerHTML = `<div class="detail-card"><p>Select or search a regulation to open the drilldown.</p></div>`;
    return;
  }
  container.innerHTML = `
    <div class="detail-card">
      <h5>${escapeHtml(regulation.name)}</h5>
      <h4>${regulation.active ? "Active" : "Upcoming"} regulation</h4>
      <div class="key-facts">
        <div class="fact"><span>Effective date</span><strong>${escapeHtml(regulation.effective_date)}</strong></div>
        <div class="fact"><span>Focus</span><strong>${escapeHtml(titleCase(regulation.focus))}</strong></div>
        <div class="fact"><span>Affected materials</span><strong>${escapeHtml(regulation.affected_materials.length)}</strong></div>
      </div>
    </div>
    <div class="detail-card">
      <h5>Action context</h5>
      <h4>Evidence gaps and likely actions</h4>
      <div class="card-list compact-list">
        ${(regulation.evidence_gaps || []).length
          ? regulation.evidence_gaps.map((item) => `<div class="row-card"><strong>Evidence gap</strong><p>${escapeHtml(item)}</p></div>`).join("")
          : `<div class="row-card"><strong>No immediate gaps</strong><p>Linked material dossiers look reasonably complete in the current dataset.</p></div>`}
      </div>
      <div class="card-list compact-list">
        ${(regulation.likely_actions || []).map((item) => `<div class="row-card"><strong>Likely action</strong><p>${escapeHtml(item)}</p></div>`).join("")}
      </div>
    </div>`;
}

async function runScenario() {
  const payload = {
    scenario: document.getElementById("scenario-type").value,
    material_id: state.selectedMaterialId,
    supplier_id: document.getElementById("scenario-supplier").value || null,
    options: {
      scenario_type: document.getElementById("scenario-type").value,
      scope: document.getElementById("scenario-scope").value,
      regulation_id: document.getElementById("scenario-regulation").value || null,
      metric: document.getElementById("scenario-metric").value,
      target_value: Number(document.getElementById("scenario-target-value").value || 0),
      max_cost: Number(document.getElementById("scenario-max-cost").value || 0),
      percent_increase: Number(document.getElementById("scenario-percent-increase").value || 0),
    },
  };
  const result = await fetchJson("/query/scenario", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  renderScenarioResult(result);
  await loadScenarioHistory();
}

async function loadTrendCharts() {
  state.analyticsOverview = await fetchJson("/analytics/overview");
  if (window.PackGraphTrendCharts) {
    window.PackGraphTrendCharts.renderOverview(state.analyticsOverview);
  }
}

async function loadMaterialTimeline() {
  const timeline = await fetchJson(`/materials/${state.selectedMaterialId}/timeline`);
  if (window.PackGraphTrendCharts) {
    window.PackGraphTrendCharts.renderMaterialTimeline(timeline);
  }
}

async function saveInvestigation() {
  const title = document.getElementById("investigation-title").value.trim();
  if (!title) {
    document.getElementById("investigation-status").textContent = "Add a title before saving the investigation.";
    document.getElementById("investigation-status").className = "upload-status status-error";
    return;
  }
  const payload = {
    title,
    focus_material_id: state.selectedMaterialId,
    notes: document.getElementById("investigation-notes").value.trim(),
    shortlisted_material_ids: selectedMaterialsFromCompare(),
    comparison_material_ids: state.compareResults.map((item) => item.material_id),
    decision_rationale: document.getElementById("investigation-rationale").value.trim(),
    status: "open",
  };
  const method = state.currentInvestigationId ? "PATCH" : "POST";
  const url = state.currentInvestigationId ? `/investigations/${state.currentInvestigationId}` : "/investigations";
  const result = await fetchJson(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.currentInvestigationId = result.investigation_id;
  document.getElementById("investigation-status").textContent = `Saved ${result.title} with ${result.shortlisted_material_ids.length} shortlisted materials.`;
  document.getElementById("investigation-status").className = "upload-status status-success";
  await loadInvestigations();
}

async function resumeInvestigation(investigationId) {
  const investigation = await fetchJson(`/investigations/${investigationId}`);
  state.currentInvestigationId = investigation.investigation_id;
  document.getElementById("investigation-title").value = investigation.title || "";
  document.getElementById("investigation-notes").value = investigation.notes || "";
  document.getElementById("investigation-rationale").value = investigation.decision_rationale || "";
  if (investigation.focus_material_id) {
    state.selectedMaterialId = investigation.focus_material_id;
    document.getElementById("material-select").value = state.selectedMaterialId;
  }
  const compare = document.getElementById("compare-materials");
  Array.from(compare.options).forEach((option) => {
    option.selected = (investigation.shortlisted_material_ids || []).includes(option.value);
  });
  renderCompareSelectionSummary();
  await refreshMaterialContext();
  await runComparison();
  document.getElementById("investigation-status").textContent = `Resumed ${investigation.title}.`;
  document.getElementById("investigation-status").className = "upload-status status-success";
}

async function resumeWorkspace(workspaceId) {
  const workspace = state.workspaces.find((item) => item.workspace_id === workspaceId);
  if (!workspace) return;
  state.currentPage = workspace.active_tab || "overview";
  setPage(state.currentPage);
  if ((workspace.selected_material_ids || []).length) {
    state.selectedMaterialId = workspace.selected_material_ids[0];
  }
  const filters = workspace.filters || {};
  const mapping = {
    "filter-search": filters.search || "",
    "filter-family": filters.material_family || "",
    "filter-region": filters.region || "",
    "filter-category": filters.category || "",
    "filter-regulation": filters.regulation_id || "",
    "filter-claim": filters.claim_type || "",
    "filter-compliance": filters.compliance_state || "",
    "filter-performance-metric": filters.performance_metric || "",
    "filter-performance-score": filters.min_performance_score || "",
    "filter-supplier-capability": filters.supplier_capability || "",
    "filter-sustainability": filters.min_sustainability || "",
  };
  Object.entries(mapping).forEach(([id, value]) => {
    const element = document.getElementById(id);
    if (element) element.value = value;
  });
  await applyFilters();
  const compare = document.getElementById("compare-materials");
  Array.from(compare.options).forEach((option) => {
    option.selected = (workspace.selected_material_ids || []).includes(option.value);
  });
  renderCompareSelectionSummary();
  await runComparison();
}

function setupPageNavigation() {
  document.querySelectorAll(".page-link").forEach((button) => {
    button.addEventListener("click", () => setPage(button.dataset.page));
  });
}

function setupNavigation() {
  document.getElementById("jump-chat").addEventListener("click", () => {
    setPage("overview");
    document.getElementById("chat-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.getElementById("jump-workbench").addEventListener("click", () => {
    setPage("workbench");
    document.querySelector('[data-page="workbench"]').scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.querySelectorAll("[data-jump-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.jumpPage;
      setPage(target);
      document.querySelector(`[data-page="${target}"]`).scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function setupGraphZoomControls() {
  const zoomIn = document.getElementById("graph-zoom-in");
  const zoomOut = document.getElementById("graph-zoom-out");
  const canvas = document.getElementById("graph-subgraph");
  if (zoomIn) {
    zoomIn.addEventListener("click", () => {
      state.graphZoom = clamp(Number((state.graphZoom + 0.1).toFixed(2)), 0.7, 1.8);
      applyGraphZoom();
    });
  }
  if (zoomOut) {
    zoomOut.addEventListener("click", () => {
      state.graphZoom = clamp(Number((state.graphZoom - 0.1).toFixed(2)), 0.7, 1.8);
      applyGraphZoom();
    });
  }
  if (canvas) {
    canvas.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        const delta = event.deltaY < 0 ? 0.08 : -0.08;
        state.graphZoom = clamp(Number((state.graphZoom + delta).toFixed(2)), 0.7, 1.8);
        applyGraphZoom();
      },
      { passive: false }
    );
  }
  applyGraphZoom();
}

function setupGraphPanControls() {
  const canvas = document.getElementById("graph-subgraph");
  if (!canvas) return;

  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  const stopDragging = () => {
    dragging = false;
    canvas.classList.remove("dragging");
  };

  canvas.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    if (event.target.closest(".graph-node, .graph-zoom-controls button")) return;
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    canvas.classList.add("dragging");
  });

  window.addEventListener("mousemove", (event) => {
    if (!dragging) return;
    const deltaX = event.clientX - lastX;
    const deltaY = event.clientY - lastY;
    lastX = event.clientX;
    lastY = event.clientY;
    state.graphPan.x = clamp(state.graphPan.x + deltaX, -240, 240);
    state.graphPan.y = clamp(state.graphPan.y + deltaY, -180, 180);
    applyGraphZoom();
  });

  window.addEventListener("mouseup", stopDragging);
  canvas.addEventListener("mouseleave", () => {
    if (dragging) {
      canvas.classList.add("dragging");
    }
  });
}

function setupGraphFilters() {
  const relationshipFilter = document.getElementById("graph-relationship-filter");
  const preset = document.getElementById("graph-preset");
  const isolate = document.getElementById("graph-isolate-selection");
  const reset = document.getElementById("graph-reset-view");
  if (relationshipFilter) {
    relationshipFilter.addEventListener("change", () => {
      state.graphFilter = relationshipFilter.value;
      if (state.currentGraph) renderGraphCanvas(state.currentGraph);
    });
  }
  if (preset) {
    preset.addEventListener("change", () => {
      state.graphPreset = preset.value;
      if (state.currentGraph) renderGraphCanvas(state.currentGraph);
    });
  }
  if (isolate) {
    isolate.addEventListener("click", () => {
      state.graphIsolateSelection = !state.graphIsolateSelection;
      isolate.textContent = state.graphIsolateSelection ? "Show full graph" : "Isolate branch";
      if (state.currentGraph) renderGraphCanvas(state.currentGraph);
    });
  }
  if (reset) {
    reset.addEventListener("click", () => {
      state.graphPan = { x: 0, y: 0 };
      state.graphZoom = 1;
      state.graphFilter = "all";
      state.graphPreset = "full";
      state.graphIsolateSelection = false;
      if (relationshipFilter) relationshipFilter.value = "all";
      if (preset) preset.value = "full";
      if (isolate) isolate.textContent = "Isolate branch";
      if (state.currentGraph) renderGraphCanvas(state.currentGraph);
      applyGraphZoom();
    });
  }
}

function setupForms() {
  document.getElementById("ask-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = document.getElementById("question-input").value.trim();
    if (!question) return;
    const response = await fetchJson("/query/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, options: { material_id: state.selectedMaterialId, prioritize_sustainability: true } }),
    });
    addMessage("Question", question);
    addMessage("PackGraph", response.message, JSON.stringify(response.plan.audit, null, 2));
    renderStructuredAnswer(response.panel);
  });

  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", async () => {
      document.getElementById("question-input").value = button.dataset.prompt;
      document.getElementById("ask-form").requestSubmit();
    });
  });

  document.getElementById("filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await applyFilters();
  });

  document.getElementById("compare-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runComparison();
  });

  document.getElementById("compare-materials").addEventListener("change", () => {
    renderCompareSelectionSummary();
  });

  document.getElementById("document-search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = document.getElementById("document-search-input").value.trim();
    await loadProvenance(query);
  });

  document.getElementById("document-upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await uploadDocumentEvidence();
  });

  document.getElementById("scenario-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runScenario();
  });

  document.getElementById("scenario-type").addEventListener("change", (event) => {
    if (window.PackGraphWorkbenchPanels) {
      window.PackGraphWorkbenchPanels.applyScenarioVisibility(event.target.value);
    }
  });

  document.getElementById("graph-path-button").addEventListener("click", async () => {
    await loadGraphPath();
  });

  document.getElementById("investigation-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveInvestigation();
  });

  document.getElementById("investigation-clear").addEventListener("click", () => {
    state.currentInvestigationId = null;
    document.getElementById("investigation-title").value = "";
    document.getElementById("investigation-notes").value = "";
    document.getElementById("investigation-rationale").value = "";
    document.getElementById("investigation-status").textContent = "Cleared the current investigation draft.";
  });

  document.getElementById("workspace-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("workspace-name").value.trim();
    if (!name) return;
    await fetchJson("/workspaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        filters: {
          search: document.getElementById("filter-search").value.trim(),
          material_family: document.getElementById("filter-family").value.trim(),
          region: document.getElementById("filter-region").value,
          category: document.getElementById("filter-category").value,
          regulation_id: document.getElementById("filter-regulation").value,
          claim_type: document.getElementById("filter-claim").value,
          compliance_state: document.getElementById("filter-compliance").value,
          performance_metric: document.getElementById("filter-performance-metric").value,
          min_performance_score: document.getElementById("filter-performance-score").value,
          supplier_capability: document.getElementById("filter-supplier-capability").value.trim(),
          min_sustainability: document.getElementById("filter-sustainability").value,
        },
        selected_material_ids: selectedMaterialsFromCompare().length ? selectedMaterialsFromCompare() : [state.selectedMaterialId],
        active_tab: state.currentPage,
      }),
    });
    document.getElementById("workspace-name").value = "";
    await loadWorkspaces();
  });

  document.getElementById("global-search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await runGlobalSearch();
  });

}

async function init() {
  setupThemeToggle();
  setupPageNavigation();
  setupNavigation();
  setupGraphZoomControls();
  setupGraphPanControls();
  setupGraphFilters();
  setupForms();
  await Promise.all([
    loadSession(),
    loadMaterials(),
    loadCompliance(),
    loadAlerts(),
    loadInvestigations(),
    loadWorkspaces(),
    loadScenarioHistory(),
    loadRecommendationsSummary(),
    loadAnalytics(),
    loadBenchmarks(),
    loadTrendCharts(),
  ]);
  await runComparison();
  renderCompareSelectionSummary();
  await runScenario();
  await loadGraphPath();
  await loadMaterialTimeline();
  renderStructuredAnswer({
    title: "Decision output",
    summary: "Run a natural-language question to see structured recommendations, reasons, risk flags, and next steps.",
    recommendations: [],
    reasons: [],
    risk_flags: [],
    next_steps: [],
  });
  renderSupplierDetail(null);
  renderRegulationDetail(null);
  addMessage("PackGraph", "Start in Overview, move to Workbench for deeper evaluation, and use Intelligence for graph, analytics, alerts, and benchmark context.");
}

init();

const trustItems = ["Materials", "Suppliers", "Regulations", "Documents", "Reports"];

const capabilityRows = [
  {
    title: "Search packaging evidence",
    detail: "Move across materials, suppliers, regulations, documents, and reports from one query surface.",
  },
  {
    title: "Compare serious candidates",
    detail: "Shortlist alternatives, run weighted comparison, and keep the tradeoffs visible.",
  },
  {
    title: "Export decision-ready outputs",
    detail: "Carry rationale, evidence context, and scenario outcomes into downloadable review artifacts.",
  },
];

const audienceRows = [
  {
    title: "Packaging teams",
    detail: "Understand which materials are viable for a packaging use case before the project turns into a full investigation.",
  },
  {
    title: "Compliance leads",
    detail: "Trace linked regulations, evidence gaps, and likely follow-up actions without losing the material context.",
  },
  {
    title: "Procurement and sourcing",
    detail: "Inspect supplier exposure, lead-time movement, and supply concentration before locking in the shortlist.",
  },
  {
    title: "R&D and materials teams",
    detail: "Compare alternatives, test reformulation pressure, and carry the decision rationale into downstream review.",
  },
];

const workflowSteps = [
  {
    step: "01",
    title: "Search and narrow evidence",
    detail: "Start from the question, not from a file folder. Search the graph and reduce the candidate set fast.",
  },
  {
    step: "02",
    title: "Traverse suppliers, materials, and regulations",
    detail: "Inspect connected entities to understand traceability, evidence gaps, and compliance pressure.",
  },
  {
    step: "03",
    title: "Compare candidates and run scenarios",
    detail: "Move shortlisted options into deeper evaluation and test outage, cost, or regulation changes.",
  },
  {
    step: "04",
    title: "Produce a decision-ready output",
    detail: "Save rationale, export reports, and keep the decision trail explainable for the next reviewer.",
  },
];

const productAreas = [
  {
    name: "Overview",
    label: "Decision starting point",
    detail: "Filter the portfolio, ask the graph, and quickly identify which candidate deserves deeper work.",
    preview: ["Material filters", "Structured answer panel", "Compliance pressure snapshot"],
  },
  {
    name: "Workbench",
    label: "Evaluation workspace",
    detail: "Compare shortlisted materials, validate evidence, save investigations, and run decision scenarios.",
    preview: ["Weighted ranking", "Evidence review", "Scenario history"],
  },
  {
    name: "Intelligence",
    label: "Graph and operating context",
    detail: "Inspect node relationships, supplier drilldowns, regulation detail, active alerts, and trend signals.",
    preview: ["Graph controls", "Supplier profile", "Regulation impacts"],
  },
];

const differentiators = [
  {
    label: "Graph-native structure",
    narrative: "Relationships are first-class, so materials, suppliers, regulations, and evidence stay connected by design.",
  },
  {
    label: "Evidence-connected reasoning",
    narrative: "Recommendations are supported by documents, reports, and missing-data signals instead of opaque output.",
  },
  {
    label: "Operational visibility",
    narrative: "Risk, compliance drift, supplier pressure, and quarterly movement remain visible while evaluating choices.",
  },
  {
    label: "Scenario readiness",
    narrative: "Teams can pressure-test decisions before they commit, rather than reacting after disruptions happen.",
  },
];

const setupSteps = [
  "Clone the repo and install Python dependencies into a local virtual environment.",
  "Run the FastAPI app in local mode, or connect Neo4j Community Edition if you want live graph-backed traversal.",
  "Open the landing page, jump into the product, and inspect the three focused workspaces.",
];

function renderTrustStrip() {
  const container = document.getElementById("landing-trust-strip");
  if (!container) return;
  container.innerHTML = trustItems.map((item) => `<span>${item}</span>`).join("");
}

function renderCapabilityRows() {
  const container = document.getElementById("landing-capability-rows");
  if (!container) return;
  container.innerHTML = capabilityRows
    .map(
      (item) => `
        <article class="landing-capability-row">
          <strong>${item.title}</strong>
          <p>${item.detail}</p>
        </article>`
    )
    .join("");
}

function renderAudienceRows() {
  const container = document.getElementById("landing-audience-grid");
  if (!container) return;
  container.innerHTML = audienceRows
    .map(
      (item) => `
        <article class="landing-audience-row">
          <strong>${item.title}</strong>
          <p>${item.detail}</p>
        </article>`
    )
    .join("");
}

function renderWorkflow() {
  const container = document.getElementById("landing-workflow-grid");
  if (!container) return;
  container.innerHTML = workflowSteps
    .map(
      (item) => `
        <article class="landing-workflow-card">
          <span class="landing-step-number">${item.step}</span>
          <h3>${item.title}</h3>
          <p>${item.detail}</p>
        </article>`
    )
    .join("");
}

function renderAreas() {
  const container = document.getElementById("landing-areas-grid");
  if (!container) return;
  container.innerHTML = productAreas
    .map(
      (item) => `
        <article class="landing-area-surface">
          <div>
            <span class="landing-kicker">${item.label}</span>
            <h3>${item.name}</h3>
            <p>${item.detail}</p>
          </div>
          <div class="landing-area-preview">
            ${item.preview.map((entry) => `<div class="landing-area-preview-row"><span></span><strong>${entry}</strong></div>`).join("")}
          </div>
        </article>`
    )
    .join("");
}

function renderDifferentiators() {
  const container = document.getElementById("landing-differentiator-table");
  if (!container) return;
  container.innerHTML = differentiators
    .map(
      (item) => `
        <div class="landing-differentiator-row">
          <strong>${item.label}</strong>
          <p>${item.narrative}</p>
        </div>`
    )
    .join("");
}

function renderSetupSteps() {
  const container = document.getElementById("landing-setup-steps");
  if (!container) return;
  container.innerHTML = setupSteps
    .map(
      (item, index) => `
        <div class="landing-setup-step-row">
          <span>${index + 1}</span>
          <p>${item}</p>
        </div>`
    )
    .join("");
}

function setupReveal() {
  const sections = document.querySelectorAll(".section-reveal");
  if (!("IntersectionObserver" in window)) {
    sections.forEach((section) => section.classList.add("is-visible"));
    return;
  }
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.18 }
  );
  sections.forEach((section) => observer.observe(section));
}

renderTrustStrip();
renderAudienceRows();
renderCapabilityRows();
renderWorkflow();
renderAreas();
renderDifferentiators();
renderSetupSteps();
setupReveal();

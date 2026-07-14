window.PackGraphTrendCharts = {
  renderOverview(overview) {
    const container = document.getElementById("trend-charts");
    if (!container) return;
    const cost = overview?.cost_trends || [];
    const risk = overview?.supplier_risk_trend || [];
    const drift = overview?.compliance_drift || [];
    container.innerHTML = [
      this.renderChartCard("Average cost", cost.map((item) => ({ label: item.quarter, value: item.average_price_usd_per_kg })), "USD/kg"),
      this.renderChartCard("Average supplier risk", risk.map((item) => ({ label: item.quarter, value: item.average_risk_score })), "risk"),
      this.renderChartCard("Non-compliant count", drift.map((item) => ({ label: item.quarter, value: item.non_compliant_count })), "materials"),
    ].join("");
  },

  renderMaterialTimeline(timeline) {
    const container = document.getElementById("material-timeline");
    if (!container) return;
    const normalized = timeline || [];
    container.innerHTML = normalized.length
      ? normalized.slice(-6).map((item) => `
        <div class="row-card">
          <strong>${this.escape(item.quarter)}</strong>
          <p>${this.escape(item.price_usd_per_kg)} USD/kg | lead time ${this.escape(item.lead_time_days)} days</p>
          <small>Risk ${this.escape(item.risk_score)} | compliance ${this.escape(item.compliance_state)} | score ${this.escape(item.compliance_score)}</small>
        </div>`).join("")
      : `<div class="row-card"><p>No material timeline available.</p></div>`;
  },

  renderChartCard(title, points, suffix) {
    if (!points.length) {
      return `<div class="row-card"><strong>${this.escape(title)}</strong><p>No data available.</p></div>`;
    }
    const values = points.map((item) => Number(item.value));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const width = 320;
    const height = 96;
    const polyline = points.map((item, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * (width - 24) + 12;
      const y = max === min
        ? height / 2
        : height - 12 - ((Number(item.value) - min) / (max - min)) * (height - 24);
      return `${x},${y}`;
    }).join(" ");
    return `
      <div class="row-card timeline-chart">
        <strong>${this.escape(title)}</strong>
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
          <polyline points="12,12 12,84 308,84"></polyline>
          <path d="M ${polyline.replaceAll(" ", " L ")}"></path>
        </svg>
        <div class="timeline-chart-footer">
          <span>${this.escape(points[0].label)}</span>
          <span>${this.escape(points[points.length - 1].value)} ${this.escape(suffix)}</span>
          <span>${this.escape(points[points.length - 1].label)}</span>
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

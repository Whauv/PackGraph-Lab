window.PackGraphUI = {
  escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  },

  emptyState(title, text) {
    return `
      <div class="table-empty">
        <span class="table-empty-illustration" aria-hidden="true"></span>
        <strong>${this.escape(title)}</strong>
        <p>${this.escape(text)}</p>
      </div>`;
  },

  badge(text, className = "tag") {
    return `<span class="${className}">${this.escape(text)}</span>`;
  },

  tonePill(text, tone = "neutral") {
    return `<span class="status-pill status-pill-${tone}">${this.escape(text)}</span>`;
  },
};

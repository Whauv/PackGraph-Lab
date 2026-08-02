window.PackGraphAuthShell = {
  renderUser(user) {
    const container = document.getElementById("user-card");
    if (!container) return;
    if (!user) {
      container.innerHTML = `
        <span>No active session</span>
        <strong>Sign in to save workspaces, searches, and contributions</strong>
        <small>Use the demo credentials or create a quick local account.</small>`;
      return;
    }
    container.innerHTML = `
      <span>${window.PackGraphUI.escape(user.role_title)}</span>
      <strong>${window.PackGraphUI.escape(user.name)}</strong>
      <small>${window.PackGraphUI.escape(user.email)}</small>
      <div class="tags">${(user.permissions || []).slice(0, 4).map((permission) => window.PackGraphUI.badge(permission, "table-badge")).join("")}</div>`;
  },

  renderNotifications(items) {
    const container = document.getElementById("notification-list");
    if (!container) return;
    if (!items.length) {
      const summary = document.getElementById("notification-summary");
      if (summary) summary.innerHTML = "";
      container.innerHTML = window.PackGraphUI.emptyState("No new notifications", "Alerts, reviews, saved workspaces, and discussion updates will surface here.");
      return;
    }
    const summary = document.getElementById("notification-summary");
    if (summary) {
      const counts = items.reduce((acc, item) => {
        acc[item.type] = (acc[item.type] || 0) + 1;
        return acc;
      }, {});
      summary.innerHTML = `
        <div class="metric"><div class="value">${window.PackGraphUI.escape(items.length)}</div><div>visible</div></div>
        <div class="metric"><div class="value">${window.PackGraphUI.escape((counts.alert || 0) + (counts.review_request || 0))}</div><div>urgent</div></div>`;
    }
    container.innerHTML = items.map((item) => `
      <div class="row-card notification-card">
        <div class="explore-result-top">
          ${window.PackGraphUI.tonePill(item.type, item.tone || "neutral")}
          <strong>${window.PackGraphUI.escape(item.title)}</strong>
        </div>
        <p>${window.PackGraphUI.escape(item.detail)}</p>
      </div>`).join("");
  },
};

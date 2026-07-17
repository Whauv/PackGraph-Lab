window.PackGraphContributePage = {
  renderRoles(roles, selectedRoleId, onSelect) {
    const container = document.getElementById("contribute-role-cards");
    if (!container) return;
    container.innerHTML = roles.map((role) => `
      <button type="button" class="row-card contribute-role-card${role.role_id === selectedRoleId ? " active" : ""}" data-role-card="${this.escape(role.role_id)}">
        <span class="section-label">${this.escape(role.persona)}</span>
        <strong>${this.escape(role.title)}</strong>
        <p>${this.escape(role.description)}</p>
        <small>${this.escape(role.badge)} | ${this.escape(role.verification_level)}</small>
      </button>
    `).join("");
    container.querySelectorAll("[data-role-card]").forEach((button) => {
      button.addEventListener("click", () => onSelect(button.dataset.roleCard));
    });
  },

  renderRoleDetail(role) {
    const container = document.getElementById("contribute-role-detail");
    if (!container) return;
    if (!role) {
      container.innerHTML = `<div class="detail-card"><p>Select a role to inspect permissions and verification behavior.</p></div>`;
      return;
    }
    container.innerHTML = `
      <div class="detail-card">
        <h5>${this.escape(role.persona)}</h5>
        <h4>${this.escape(role.title)}</h4>
        <p>${this.escape(role.description)}</p>
        <div class="tags">
          <span class="tag">${this.escape(role.badge)}</span>
          <span class="tag">${this.escape(role.verification_level)}</span>
        </div>
      </div>
      <div class="detail-card">
        <h5>Role permissions</h5>
        <h4>What this contributor can do</h4>
        <div class="card-list compact-list">
          ${(role.permissions || []).map((permission) => `<div class="row-card"><strong>${this.escape(permission)}</strong></div>`).join("")}
        </div>
      </div>`;
  },

  renderSubmissions(payload) {
    const recent = document.getElementById("contribution-recent-list");
    const status = document.getElementById("contribution-status-board");
    if (status) {
      status.innerHTML = (payload.status_summary || []).map((item) => `
        <div class="metric">
          <div class="value">${this.escape(item.value)}</div>
          <div>${this.escape(item.label)}</div>
        </div>
      `).join("");
    }
    if (!recent) return;
    const submissions = payload.submissions || [];
    recent.innerHTML = submissions.length
      ? submissions.map((item) => `
        <div class="row-card">
          <strong>${this.escape(item.title)}</strong>
          <p>${this.escape(item.summary || "No summary captured.")}</p>
          <small>${this.escape(item.status)} | ${this.escape(item.badge)} | ${this.escape(item.submitted_on)}</small>
        </div>`).join("")
      : `<div class="row-card"><p>No submissions yet.</p></div>`;
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

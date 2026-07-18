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
    const queue = document.getElementById("contribution-review-queue");
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
          <small>${this.escape(item.status)} | confidence ${this.escape(item.evidence_confidence || "n/a")} | ${this.escape(item.badge)} | ${this.escape(item.submitted_on)}</small>
        </div>`).join("")
      : `<div class="row-card"><p>No submissions yet.</p></div>`;
    if (queue) {
      const reviewQueue = payload.review_queue || [];
      queue.innerHTML = reviewQueue.length
        ? reviewQueue.map((item) => `
          <div class="row-card review-queue-card">
            <div class="explore-result-top">
              <strong>${this.escape(item.title)}</strong>
              <span class="table-badge">${this.escape(item.status)}</span>
            </div>
            <p>${this.escape(item.summary || "No summary captured.")}</p>
            <div class="diff-preview">
              <div><span>Before</span><strong>${this.escape(item.diff_preview?.before || "No prior draft")}</strong></div>
              <div><span>After</span><strong>${this.escape(item.diff_preview?.after || "No proposed update")}</strong></div>
            </div>
            <small>Evidence confidence ${this.escape(item.evidence_confidence || "n/a")} | ${this.escape(item.submitted_by)}</small>
            <div class="row-actions">
              <button type="button" class="mini-action" data-review-id="${this.escape(item.contribution_id)}" data-review-status="accepted">Approve</button>
              <button type="button" class="mini-action secondary" data-review-id="${this.escape(item.contribution_id)}" data-review-status="under_review">Keep reviewing</button>
              <button type="button" class="mini-action secondary" data-review-id="${this.escape(item.contribution_id)}" data-review-status="rejected">Reject</button>
            </div>
          </div>`).join("")
        : `<div class="row-card"><p>No items currently need review.</p></div>`;
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

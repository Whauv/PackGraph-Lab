window.PackGraphEntityActions = {
  escape(value) {
    return window.PackGraphUI?.escape ? window.PackGraphUI.escape(value) : String(value ?? "");
  },

  render(container, context = {}, handlers = {}) {
    if (!container) return;
    const entityName = context.entity_name || context.name || "current entity";
    const entityType = context.entity_type || "entity";
    container.innerHTML = `
      <div class="entity-action-strip">
        <div class="entity-action-strip-copy">
          <span class="section-label">Quick actions</span>
          <strong>${this.escape(entityName)}</strong>
          <small>${this.escape(entityType)} context follows you across the product.</small>
        </div>
        <div class="entity-action-buttons">
          <button type="button" class="mini-action" data-entity-action="shortlist">Shortlist</button>
          <button type="button" class="mini-action" data-entity-action="compare">Compare</button>
          <button type="button" class="mini-action" data-entity-action="graph">Graph</button>
          <button type="button" class="mini-action" data-entity-action="evidence">Evidence</button>
          <button type="button" class="mini-action" data-entity-action="scenario">Scenario</button>
          <button type="button" class="mini-action" data-entity-action="review">Review</button>
          <button type="button" class="mini-action" data-entity-action="export">Export</button>
        </div>
      </div>`;
    container.querySelectorAll("[data-entity-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.dataset.entityAction;
        if (handlers[action]) handlers[action](context);
      });
    });
  },
};

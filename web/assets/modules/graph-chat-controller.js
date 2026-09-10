(function () {
  async function loadWorkflowStatus(fetchJson) {
    try {
      const payload = await fetchJson("/runtime/workflow-status");
      window.PackGraphChat?.setWorkflowStatus(payload);
    } catch {
      window.PackGraphChat?.setWorkflowStatus(null);
    }
  }

  async function init(deps) {
    const { fetchJson, state, handleChatResult, loadReviewQueue, loadNotifications } = deps;
    window.PackGraphChat?.init({
      previewRequest: async ({ question, context, mode }) => fetchJson("/query/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          mode: mode || "quick_ask",
          options: { material_id: state.selectedMaterialId, prioritize_sustainability: true },
          context,
        }),
      }),
      request: async ({ question, context, mode }) => fetchJson("/query/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          mode: mode || "quick_ask",
          options: { material_id: state.selectedMaterialId, prioritize_sustainability: true },
          context,
        }),
      }),
      enrichRequest: async ({ question, context, mode }) => fetchJson("/query/enrich", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          mode: mode || "research_review",
          options: { material_id: state.selectedMaterialId, prioritize_sustainability: true },
          context,
        }),
      }),
      onResult: async (question, response) => {
        handleChatResult(question, response);
        await Promise.all([loadReviewQueue(), loadNotifications()]);
      },
    });
    await loadWorkflowStatus(fetchJson);
  }

  window.PackGraphGraphChatController = { init, loadWorkflowStatus };
})();

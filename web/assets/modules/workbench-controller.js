(function () {
  function setupForms(deps) {
    document.getElementById("compare-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await deps.runComparison();
    });

    document.getElementById("compare-materials")?.addEventListener("change", () => {
      deps.renderCompareSelectionSummary();
      deps.syncActiveCase({
        shortlist_material_ids: deps.selectedMaterialsFromCompare(),
        status: "compare",
        workflow_step: "Compare",
      });
    });

    document.getElementById("document-search-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const query = document.getElementById("document-search-input").value.trim();
      await deps.loadProvenance(query);
    });

    document.getElementById("document-upload-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await deps.uploadDocumentEvidence();
    });

    document.getElementById("source-intake-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await window.PackGraphSourceIntake?.upload();
    });

    document.getElementById("scenario-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await deps.runScenario();
    });

    document.getElementById("scenario-type")?.addEventListener("change", (event) => {
      window.PackGraphWorkbenchPanels?.applyScenarioVisibility(event.target.value);
    });

    document.getElementById("graph-path-button")?.addEventListener("click", async () => {
      await deps.loadGraphPath();
    });

    document.getElementById("investigation-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await deps.saveInvestigation();
    });

    document.getElementById("investigation-clear")?.addEventListener("click", () => {
      deps.state.currentInvestigationId = null;
      document.getElementById("investigation-title").value = "";
      document.getElementById("investigation-project-status").value = "active";
      document.getElementById("investigation-owner").value = "";
      document.getElementById("investigation-due-date").value = "";
      document.getElementById("investigation-notes").value = "";
      document.getElementById("investigation-rationale").value = "";
      deps.clearDraft(deps.draftStorageKeys.investigation);
      deps.setStatus("investigation-status", "Cleared the current investigation draft.", "info");
    });

    document.getElementById("case-sync")?.addEventListener("click", async () => {
      await deps.syncProjectMemory({
        saved_entities: [deps.state.activeCase?.focus_material_id],
        compared_entities: deps.state.activeCase?.shortlist_material_ids || [],
        prior_questions: [deps.state.activeCase?.latest_question],
        investigation_notes: [deps.state.activeCase?.note],
        user_assumptions: [deps.state.activeCase?.workflow_step],
      });
      deps.setStatus("case-status", "Synced the active case to project memory.", "success");
    });

    document.getElementById("case-reset")?.addEventListener("click", () => {
      deps.state.activeCase = deps.defaultActiveCase();
      deps.persistActiveCase();
      deps.renderCaseWorkspace();
      deps.renderWorkflowMap();
      deps.renderCrossPageContext();
      deps.setStatus("case-status", "Reset the active case workspace.", "info");
    });
  }

  window.PackGraphWorkbenchController = { setupForms };
})();

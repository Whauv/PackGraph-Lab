window.PackGraphState = {
  storageKeys: {
    sessionToken: "packgraph-session-token",
    theme: "packgraph-theme",
    activeCase: "packgraph-active-case",
    graphPins: "packgraph-graph-pins",
    graphCollapsed: "packgraph-graph-collapsed",
    personalWorkspace: "packgraph-personal-workspace",
  },

  createDefaultState() {
    return {
      materials: [],
      products: [],
      suppliers: [],
      applications: [],
      regulations: [],
      exploreTab: "materials",
      exploreView: "cards",
      currentSection: "dashboard",
      exploreResults: [],
      selectedExploreDetail: null,
      contributionRoles: [],
      selectedContributionRoleId: "fellow",
      contributionData: { submissions: [], status_summary: [] },
      communityChannels: [],
      selectedCommunityChannelId: "polymers",
      communityPosts: [],
      selectedCommunityPostId: null,
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
      sessionToken: window.localStorage.getItem(this.storageKeys.sessionToken) || "",
      currentPage: "overview",
      notifications: [],
      savedSearches: [],
      latestQuestion: "",
      latestGlobalSearch: "",
      latestSupplierId: null,
      supplierRegionSummary: [],
      privateDataStatus: { private_data_active: false, dataset_count: 0, record_count: 0 },
      projectMemory: null,
      reviewQueue: [],
      reviewSummary: { total: 0, pending: 0 },
      selectedReviewCandidateId: null,
      activeCase: null,
      commandCenterResults: null,
      notificationFilter: "all",
      graphCollapsedTypes: [],
      graphPinnedNodeIds: [],
      scenarioComparisons: [],
      roleDashboardProfile: null,
      graphRenderSignature: "",
      personalWorkspace: {
        bookmarks: [],
        recent_entities: [],
        quick_note: "",
        reminders: [],
      },
      drawerState: {
        isOpen: false,
        activeContext: null,
      },
    };
  },

  defaultActiveCase() {
    return {
      case_id: `CASE-${Date.now()}`,
      name: "Active packaging case",
      status: "discover",
      focus_material_id: null,
      focus_supplier_id: null,
      focus_entity_type: "material",
      focus_entity_id: null,
      focus_entity_name: "",
      shortlist_material_ids: [],
      latest_question: "",
      latest_search: "",
      scenario_type: "",
      evidence_strength: "unknown",
      review_state: "not_requested",
      confidence: "pending",
      next_action_label: "Start in Overview",
      next_action_target: "overview",
      next_action_reason: "Search or ask a focused question to begin.",
      last_result_count: 0,
      missing_evidence_count: 0,
      note: "",
      workflow_step: "Discover",
    };
  },

  loadJson(key, fallback) {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(key) || "null");
      return parsed ?? fallback;
    } catch {
      return fallback;
    }
  },

  saveJson(key, value) {
    window.localStorage.setItem(key, JSON.stringify(value));
  },
};

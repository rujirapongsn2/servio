export const UI_COPY = {
  tools: {
    navLabel: "Agent Capabilities",
    pageTitle: "Agent Capabilities",
    pageSubtitle: "Choose what your agents can use to answer questions and complete tasks.",
    actions: {
      addIntegration: "Add Integration",
      addDocumentLibrary: "Add Document Library",
    },
    sections: {
      readyToUse: "Ready-to-Use Capabilities",
      documentSearch: "Document Search",
      externalIntegrations: "External Integrations",
    },
    badges: {
      included: "Included",
      documentSearch: "Document Search",
    },
    meta: {
      ownedBy: "Owned by",
      createdBy: "Created by",
      usedByAgents: "Used by",
      agents: "agents",
    },
    empty: {
      documentLibraries: "No document libraries yet. Add one so agents can answer from your files.",
      externalIntegrations: "No integrations yet. Add one to connect your agents to external systems.",
    },
    builtInNames: {
      DateTimeTool: "Current Date & Time",
      WebSearchTool: "Web Search",
    } as Record<string, string>,
    builtInDescriptions: {
      DateTimeTool: "Provides the current date and time automatically.",
      WebSearchTool: "Finds up-to-date information from the web.",
    } as Record<string, string>,
  },
  dashboard: {
    cards: {
      totalAgents: { title: "Total Agents", description: "Active AI agents" },
      totalCapabilities: { title: "Total Capabilities", description: "Available capabilities" },
      includedCapabilities: { title: "Included Capabilities", description: "Ready-to-use capabilities" },
      externalIntegrations: { title: "External Integrations", description: "Connected external systems" },
    },
  },
} as const;


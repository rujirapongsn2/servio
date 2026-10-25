"use client";
import { useAdminLocale } from "@/lib/admin-locale";
import { useCallback, useEffect, useRef, useState, type ComponentProps } from "react";
import { BookOpen, Boxes, Pencil, Play, Plus, RefreshCw, Search, Trash2, Wrench } from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";
import WorkflowPanelDialog from "@/components/WorkflowPanelDialog";
import WorkflowToolModal from "@/components/WorkflowToolModal";
import EditToolForm from "@/components/EditToolForm";
import CreateOKFBundleModal from "@/components/CreateOKFBundleModal";
import OKFBundleDetailDrawer from "@/components/OKFBundleDetailDrawer";
import TestOKFBundleModal from "@/components/TestOKFBundleModal";
import CreateFileStoreModal from "@/components/CreateFileStoreModal";
import FileStoreDetailModal from "@/components/FileStoreDetailModal";
import TestFileStoreModal from "@/components/TestFileStoreModal";
export type WorkflowResourceMutation = {
  kind: "updated";
  toolId: number;
} | {
  kind: "deleted";
  toolId: number;
};
interface LibraryTool {
  id: number;
  name: string;
  type: string;
  config: string | null;
  owner_team_agent_id: number | null;
  owner_team_name?: string;
  visibility?: string;
  agent_usage_count?: number;
}
type FileStore = ComponentProps<typeof FileStoreDetailModal>["store"];
type ResourceView = {
  kind: "list";
} | {
  kind: "create-tool";
} | {
  kind: "create-knowledge";
} | {
  kind: "create-legacy";
} | {
  kind: "edit" | "knowledge-detail" | "knowledge-test";
  tool: LibraryTool;
} | {
  kind: "legacy-detail" | "legacy-test";
  tool: LibraryTool;
  store: FileStore;
};
export function parseResourceConfig(config: string | null): Record<string, unknown> {
  const parsed: unknown = config ? JSON.parse(config) : {};
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
    throw new Error("Invalid resource configuration");
  return parsed as Record<string, unknown>;
}
export function canEditWorkflowResource(tool: Pick<LibraryTool, "owner_team_agent_id" | "type">, teamId: number, canEdit: boolean) {
  return canEdit && tool.type !== "builtin" && (tool.owner_team_agent_id === teamId || (tool.owner_team_agent_id == null && ["custom_api", "mcp_streamable_http"].includes(tool.type)));
}
export default function WorkflowCapabilitiesPanel({ teamId, canEdit, onClose, onMutation }: {
  teamId: number;
  canEdit: boolean;
  onClose: () => void;
  onMutation: (result: WorkflowResourceMutation) => Promise<void>;
}) {
  const { copy } = useAdminLocale();
  const [tools, setTools] = useState<LibraryTool[]>([]);
  const [view, setView] = useState<ResourceView>({ kind: "list" });
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<WorkflowResourceMutation | null>(null);
  const active = useRef(true);
  const operation = useRef(false);
  const legacy = process.env.NEXT_PUBLIC_ENABLE_GEMINI_DOCUMENT_SEARCH === "true";
  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem("adminToken")}` });
  const fetchTools = useCallback(async (signal?: AbortSignal) => {
    const response = await fetch(`${getApiBaseUrl()}/api/admin/tools?team_agent_id=${teamId}`, { signal, headers: { Authorization: `Bearer ${localStorage.getItem("adminToken")}` } });
    const data: unknown = await response.json().catch(() => null);
    if (!response.ok)
      throw new Error("Failed to load capabilities");
    if (!Array.isArray(data) || !data.every(value => value && typeof value === "object" && Number.isSafeInteger(value.id) && value.id > 0 && typeof value.name === "string" && typeof value.type === "string" && (value.config == null || typeof value.config === "string")))
      throw new Error("Invalid capabilities response");
    const loaded: LibraryTool[] = data.map((tool: LibraryTool) => {
      if (tool.type === "okf_knowledge_graph" || tool.type === "gemini_file_search") {
        try {
          const config = parseResourceConfig(tool.config);
          if (typeof config.display_name === "string" && config.display_name.trim()) return { ...tool, name: config.display_name };
        } catch {}
      }
      return tool;
    });
    if (!signal?.aborted && active.current)
      setTools(loaded);
    return loaded;
  }, [teamId]);
  useEffect(() => {
    active.current = true;
    const controller = new AbortController();
    setLoading(true);
    setView({ kind: "list" });
    setPending(null);
    fetchTools(controller.signal).catch(failure => {
      if (!controller.signal.aborted)
        setError(failure instanceof Error ? failure.message : "Failed to load capabilities");
    }).finally(() => {
      if (!controller.signal.aborted)
        setLoading(false);
    });
    return () => {
      active.current = false;
      controller.abort();
    };
  }, [fetchTools]);
  const refresh = async (result: WorkflowResourceMutation, closeView = true) => {
    setPending(result);
    try {
      await fetchTools();
      await onMutation(result);
      if (!active.current)
        return;
      setPending(null);
      setError("");
      if (closeView)
        setView({ kind: "list" });
    }
    catch (failure) {
      if (active.current)
        setError(`Change saved. Refresh failed. ${failure instanceof Error ? failure.message : "Try again"}`);
      throw failure;
    }
  };
  const mutate = async (result: WorkflowResourceMutation) => {
    if (operation.current || pending)
      return;
    operation.current = true;
    setBusy(true);
    setView({ kind: "list" });
    try {
      await refresh(result);
    }
    catch {
    }
    finally {
      operation.current = false;
      if (active.current)
        setBusy(false);
    }
  };
  const remove = async (tool: LibraryTool) => {
    if (!canEditWorkflowResource(tool, teamId, canEdit) || operation.current || pending)
      return;
    if (!window.confirm(copy.confirmDeleteCapability(tool.name)))
      return;
    operation.current = true;
    setBusy(true);
    setError("");
    try {
      const config = parseResourceConfig(tool.config);
      let path = `/tools/${tool.id}`;
      if (tool.type === "okf_knowledge_graph") {
        if (!Number.isSafeInteger(config.okf_bundle_id) || Number(config.okf_bundle_id) < 1)
          throw new Error("Invalid knowledge bundle ID");
        path = `/okf-bundles/${config.okf_bundle_id}`;
      }
      if (tool.type === "gemini_file_search") {
        const store = await findStore(tool);
        path = `/file-stores/${store.id}`;
      }
      const response = await fetch(`${getApiBaseUrl()}/api/admin${path}?team_agent_id=${teamId}`, { method: "DELETE", headers: headers() });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(typeof data?.detail === "string" ? data.detail : "Failed to delete capability");
      }
      await refresh({ kind: "deleted", toolId: tool.id });
    }
    catch (failure) {
      if (active.current)
        setError(failure instanceof Error ? failure.message : "Failed to delete capability");
    }
    finally {
      operation.current = false;
      if (active.current)
        setBusy(false);
    }
  };
  const findStore = async (tool: LibraryTool): Promise<FileStore> => {
    const config = parseResourceConfig(tool.config);
    if (typeof config.gemini_store_id !== "string")
      throw new Error("Invalid document library configuration");
    const response = await fetch(`${getApiBaseUrl()}/api/admin/file-stores?team_agent_id=${teamId}`, { headers: headers() });
    const stores = await response.json();
    if (!response.ok || !Array.isArray(stores))
      throw new Error("Failed to load document library");
    const store = stores.find(item => item.gemini_store_id === config.gemini_store_id);
    if (!store || !Number.isSafeInteger(store.id) || typeof store.display_name !== "string")
      throw new Error("Document library unavailable");
    return store;
  };
  const open = async (tool: LibraryTool, test = false) => {
    setError("");
    try {
      const config = parseResourceConfig(tool.config);
      if (tool.type === "okf_knowledge_graph") {
        if (!Number.isSafeInteger(config.okf_bundle_id) || Number(config.okf_bundle_id) < 1)
          throw new Error("Invalid knowledge bundle ID");
        setView({ kind: test ? "knowledge-test" : "knowledge-detail", tool });
      }
      else if (tool.type === "gemini_file_search") {
        const store = await findStore(tool);
        if (active.current)
          setView({ kind: test ? "legacy-test" : "legacy-detail", tool, store });
      }
      else if (canEditWorkflowResource(tool, teamId, canEdit))
        setView({ kind: "edit", tool });
    }
    catch (failure) {
      setError(failure instanceof Error ? failure.message : "Failed to open capability");
    }
  };
  const closeChild = () => {
    if (!busy)
      setView({ kind: "list" });
  };
  const visible = tools.filter(tool => `${tool.name} ${tool.type} ${tool.owner_team_name ?? ""}`.toLowerCase().includes(query.trim().toLowerCase()));
  const actionClass = "rounded p-2 hover:bg-gray-100 disabled:opacity-40 dark:hover:bg-gray-800";
  return <WorkflowPanelDialog title={copy.capabilities} onClose={onClose} onChildClose={closeChild} busy={busy || !!pending}>
  <div className="space-y-4">{error && <div role="alert" className="text-sm text-red-600">{copy.capabilityIssue}<details><summary>{copy.errorDetails}</summary>{error}</details></div>}{pending && <div className="flex items-center justify-between gap-2 rounded border border-amber-300 p-3 text-sm">
    <span>{copy.changeSavedRefresh}</span>
    <button type="button" disabled={busy} onClick={() => {
        setBusy(true);
        void refresh(pending).catch(() => {
        }).finally(() => setBusy(false));
      }} className="rounded border px-3 py-1.5">{copy.retryRefresh}</button>
    </div>}{view.kind === "edit" ? <fieldset disabled={!!pending}>
    <div className="mb-3 flex items-center justify-between">
    <h3 className="font-semibold">{copy.editIntegration}</h3>
    <button type="button" disabled={busy || !!pending} onClick={closeChild} className="rounded border px-3 py-1.5 text-sm">{copy.back}</button>
    </div>
    <EditToolForm key={view.tool.id} toolId={view.tool.id} teamId={teamId} onCancel={closeChild} onBusyChange={setBusy} onSaved={() => refresh({ kind: "updated", toolId: view.tool.id })}/>
    </fieldset> : <>
    <div className="flex flex-wrap items-center gap-2">
    <label className="relative min-w-40 flex-1">
    <Search className="absolute left-3 top-2.5 text-gray-400" size={18}/>
    <input aria-label={copy.searchCapabilities} value={query} onChange={event => setQuery(event.target.value)} placeholder={copy.searchCapabilities} className="w-full rounded-lg border py-2 pl-9 pr-3 text-sm dark:border-gray-700 dark:bg-gray-800"/>
    </label>
    <button type="button" title={copy.refreshCapabilities} aria-label={copy.refreshCapabilities} disabled={loading || busy || !!pending} onClick={() => {
        setLoading(true);
        fetchTools().catch(failure => setError(String(failure))).finally(() => setLoading(false));
      }} className={actionClass}>
    <RefreshCw size={18}/>
    </button>{canEdit && <>
      <button type="button" disabled={busy || !!pending} data-admin-write="true" onClick={() => setView({ kind: "create-tool" })} className="inline-flex items-center gap-1 rounded border px-3 py-2 text-sm">
      <Plus size={16}/>{copy.integration}</button>
      <button type="button" disabled={busy || !!pending} data-admin-write="true" onClick={() => setView({ kind: "create-knowledge" })} className="inline-flex items-center gap-1 rounded border px-3 py-2 text-sm">
      <Plus size={16}/>{copy.knowledge}</button>{legacy && <button type="button" disabled={busy || !!pending} data-admin-write="true" onClick={() => setView({ kind: "create-legacy" })} className="rounded border px-3 py-2 text-sm">{copy.documentLibrary}</button>}</>}</div>{loading ? <p role="status" className="py-8 text-center text-sm text-gray-500">{copy.loadingCapabilities}</p> : <ul className="divide-y rounded-lg border dark:divide-gray-700 dark:border-gray-700">{visible.map(tool => {
          const own = canEditWorkflowResource(tool, teamId, canEdit);
          const knowledge = ["okf_knowledge_graph", "gemini_file_search"].includes(tool.type);
          const integration = ["custom_api", "mcp_streamable_http"].includes(tool.type);
          const Icon = knowledge ? BookOpen : tool.type === "builtin" ? Boxes : Wrench;
          return <li key={tool.id} className="flex items-center gap-3 p-3">
          <Icon size={20} className="shrink-0 text-blue-600"/>
          <div className="min-w-0 flex-1">
          <p className="break-words text-sm font-medium">{tool.name}</p>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
          <span>{tool.type === "builtin" ? copy.included : tool.type === "custom_api" ? "API" : tool.type === "mcp_streamable_http" ? "MCP" : copy.knowledge}</span>
                <span>{tool.owner_team_agent_id === teamId ? copy.thisTeam : tool.owner_team_name || (tool.type === "builtin" ? copy.system : copy.unassigned)}</span>
          <span>{tool.visibility === "global" ? copy.global : tool.type === "builtin" ? "" : copy.private}</span>
          <span>{copy.agentsCount(tool.agent_usage_count ?? 0)}</span>
          </div>
          </div>
          <div className="flex shrink-0 gap-1">{knowledge && <>
            <button type="button" disabled={busy || !!pending} onClick={() => void open(tool)} title={copy.openNamed(tool.name)} aria-label={copy.openNamed(tool.name)} className={actionClass}>
            <BookOpen size={17}/>
            </button>
            <button type="button" disabled={busy || !!pending} onClick={() => void open(tool, true)} title={copy.testNamed(tool.name)} aria-label={copy.testNamed(tool.name)} className={actionClass}>
            <Play size={17}/>
            </button>
            </>}{own && integration && <button type="button" disabled={busy || !!pending} data-admin-write="true" onClick={() => void open(tool)} title={copy.editNamed(tool.name)} aria-label={copy.editNamed(tool.name)} className={actionClass}>
            <Pencil size={17}/>
            </button>}{own && (integration || knowledge) && <button type="button" disabled={busy || !!pending} data-admin-write="true" onClick={() => void remove(tool)} title={copy.deleteNamed(tool.name)} aria-label={copy.deleteNamed(tool.name)} className={`${actionClass} text-red-600`}>
            <Trash2 size={17}/>
            </button>}</div>
          </li>;
        })}{visible.length === 0 && <li className="p-8 text-center text-sm text-gray-500">{copy.noCapabilities}</li>}</ul>}</>}
  {view.kind === "create-tool" && <WorkflowToolModal teamId={teamId} onClose={closeChild} onCreated={result => {
        void mutate({ kind: "updated", toolId: result.tool_id });
      }}/>}
  {view.kind === "create-knowledge" && <CreateOKFBundleModal teamAgentId={teamId} assignAgentId={null} jobStorageKey={`workflow-library-import:${teamId}`} onClose={closeChild} onSuccess={result => {
        void mutate({ kind: "updated", toolId: result.tool_id });
      }}/>}
  {view.kind === "knowledge-detail" && <OKFBundleDetailDrawer tool={view.tool} teamAgentId={teamId} canEdit={canEditWorkflowResource(view.tool, teamId, canEdit) && !pending} onClose={closeChild} onReindexed={() => {
        void refresh({ kind: "updated", toolId: view.tool.id }, false).catch(() => {
        });
      }}/>}
  {view.kind === "knowledge-test" && <TestOKFBundleModal tool={view.tool} teamAgentId={teamId} onClose={closeChild}/>}
  {legacy && view.kind === "create-legacy" && <CreateFileStoreModal teamAgentId={teamId} assignAgentId={null} onClose={closeChild} onSuccess={() => {
        const previousIds = new Set(tools.map(tool => tool.id));
        setBusy(true);
        fetchTools().then(loaded => {
          const added = loaded.find(tool => !previousIds.has(tool.id));
          if (added)
            return refresh({ kind: "updated", toolId: added.id });
          setView({ kind: "list" });
        }).catch(failure => setError(String(failure))).finally(() => setBusy(false));
      }}/>}
  {view.kind === "legacy-detail" && <FileStoreDetailModal store={view.store} canEdit={canEditWorkflowResource(view.tool, teamId, canEdit)} onClose={() => {
        closeChild();
        void refresh({ kind: "updated", toolId: view.tool.id }).catch(() => {
        });
      }}/>}
  {view.kind === "legacy-test" && <TestFileStoreModal store={view.store} onClose={closeChild}/>}
 </div>
  </WorkflowPanelDialog>;
}

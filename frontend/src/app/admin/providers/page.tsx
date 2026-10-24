"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { ArrowLeft, Copy, Plus, Trash2, Edit2, Link as LinkIcon, Check, X, Loader2, Sparkles } from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";
import { ProviderModels } from "@/components/ProviderModels";

interface LLMProvider {
    id: number;
    name: string;
    base_url: string;
    api_key: string;
    is_default: boolean;
    created_at: string;
    updated_at: string;
}

export default function LLMProvidersPage() {
    return (
        <Suspense fallback={<ProvidersLoading />}>
            <LLMProvidersContent />
        </Suspense>
    );
}

function ProvidersLoading() {
    return (
        <div className="flex justify-center p-8">
            <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
        </div>
    );
}

function LLMProvidersContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const apiBaseUrl = getApiBaseUrl();
    const returnToAgentEdit = searchParams.get("return_to") === "agent_edit";
    const returnAgentId = searchParams.get("return_agent_id") || "new";
    const returnTeamId = searchParams.get("return_team_id");
    const returnTeamName = searchParams.get("return_team_name");
    const returnWorkspace = searchParams.get("return_workspace");
    const teamAgentId = searchParams.get("team_agent_id");
    const draftId = searchParams.get("draft_id");
    const shouldCreateProvider = searchParams.get("create") === "1";
    const [providers, setProviders] = useState<LLMProvider[]>([]);
    const [modelsProvider, setModelsProvider] = useState<LLMProvider | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

    // Edit/Create State
    const [isEditing, setIsEditing] = useState(false);
    const [currentProvider, setCurrentProvider] = useState<Partial<LLMProvider>>({});
    const [lastSavedProviderId, setLastSavedProviderId] = useState<number | null>(null);
    const [createPromptOpened, setCreatePromptOpened] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
    const [isTesting, setIsTesting] = useState(false);

    useEffect(() => {
        fetchProviders();
    }, []);

    useEffect(() => {
        if (!isLoading && shouldCreateProvider && !isEditing && !lastSavedProviderId && !createPromptOpened) {
            setCreatePromptOpened(true);
            handleCreate();
        }
    }, [isLoading, shouldCreateProvider, isEditing, lastSavedProviderId, createPromptOpened]);

    const buildAgentReturnHref = (providerId?: number | null) => {
        const params = new URLSearchParams();
        if (teamAgentId) params.set("team_agent_id", teamAgentId);
        if (returnTeamId) params.set("return_team_id", returnTeamId);
        if (returnTeamName) params.set("return_team_name", returnTeamName);
        if (returnWorkspace === "workflow") params.set("return_workspace", "workflow");
        if (draftId) params.set("draft_id", draftId);
        if (providerId) params.set("select_provider_id", String(providerId));
        const query = params.toString();
        return `/admin/agents/${returnAgentId}${query ? `?${query}` : ""}`;
    };

    const fetchProviders = async () => {
        setIsLoading(true);
        try {
            const token = localStorage.getItem("adminToken");
            const res = await fetch(`${apiBaseUrl}/api/admin/llm-providers`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                setProviders(data);
            } else {
                throw new Error("Failed to fetch providers");
            }
        } catch (error) {
            console.error(error);
            setMessage({ text: "Failed to load providers", type: "error" });
        } finally {
            setIsLoading(false);
        }
    };

    const handleEdit = (provider: LLMProvider) => {
        setCurrentProvider({ ...provider }); // Clone to avoid direct mutation
        setIsEditing(true);
        setTestResult(null);
        setMessage(null);
    };

    const handleCreate = () => {
        setCurrentProvider({
            name: "",
            base_url: "https://api.openai.com/v1",
            api_key: "",
            is_default: false
        });
        setIsEditing(true);
        setTestResult(null);
        setMessage(null);
    };

    const handleDelete = async (id: number) => {
        if (!confirm("Are you sure you want to delete this provider?")) return;

        try {
            const token = localStorage.getItem("adminToken");
            const res = await fetch(`${apiBaseUrl}/api/admin/llm-providers/${id}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });

            if (res.ok) {
                fetchProviders();
                setMessage({ text: "Provider deleted", type: "success" });
            } else {
                throw new Error("Failed to delete");
            }
        } catch (error) {
            setMessage({ text: "Failed to delete provider", type: "error" });
        }
    };

    const handleSave = async () => {
        if (!currentProvider.name || !currentProvider.base_url || !currentProvider.api_key) {
            setMessage({ text: "Please fill in all required fields", type: "error" });
            return;
        }

        setIsSaving(true);
        try {
            const token = localStorage.getItem("adminToken");
            const method = currentProvider.id ? "PUT" : "POST";
            const url = currentProvider.id
                ? `${apiBaseUrl}/api/admin/llm-providers/${currentProvider.id}`
                : `${apiBaseUrl}/api/admin/llm-providers`;

            const res = await fetch(url, {
                method,
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`
                },
                body: JSON.stringify(currentProvider),
            });

            if (res.ok) {
                const data = await res.json().catch(() => ({}));
                const createdIdMatch = typeof data.message === "string" ? data.message.match(/ID\s+(\d+)/) : null;
                const savedProviderId = currentProvider.id || (createdIdMatch ? parseInt(createdIdMatch[1]) : null);
                setIsEditing(false);
                fetchProviders();
                setLastSavedProviderId(savedProviderId);
                setMessage({
                    text: returnToAgentEdit && savedProviderId
                        ? "Provider saved. You can return to the agent and use it now."
                        : "Provider saved successfully",
                    type: "success",
                });
            } else {
                const data = await res.json();
                throw new Error(data.detail || "Failed to save");
            }
        } catch (error: any) {
            setMessage({ text: error.message || "Failed to save provider", type: "error" });
        } finally {
            setIsSaving(false);
        }
    };

    const testConnection = async () => {
        // We need an ID to test (fetch models). If it's a new provider, we can't test until saved?
        // Actually we can have a backend endpoint that accepts creds to test, but I implemented fetching models by ID.
        // So for now, we only test saved providers.
        if (!currentProvider.id) {
            setTestResult({ success: false, message: "Please save the provider first to test connection." });
            return;
        }

        setIsTesting(true);
        setTestResult(null);
        try {
            const token = localStorage.getItem("adminToken");
            const res = await fetch(`${apiBaseUrl}/api/admin/llm-providers/${currentProvider.id}/models`, {
                headers: { Authorization: `Bearer ${token}` },
            });

            if (res.ok) {
                const models = await res.json();
                setTestResult({ success: true, message: `Success! Found ${models.length} models.` });
            } else {
                const data = await res.json();
                throw new Error(data.detail || "Connection failed");
            }
        } catch (error: any) {
            setTestResult({ success: false, message: error.message || "Connection failed" });
        } finally {
            setIsTesting(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex justify-center p-8">
                <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
            </div>
        );
    }

    return (
        <div className="max-w-5xl mx-auto space-y-6">
            {returnToAgentEdit && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900 dark:border-blue-900/50 dark:bg-blue-900/20 dark:text-blue-100">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                            <div className="font-semibold">Adding a provider for this agent</div>
                            <div className="mt-1 text-blue-800 dark:text-blue-200">
                                Save or test the provider here, then return to Edit Agent without losing the setup flow.
                            </div>
                        </div>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => router.push(buildAgentReturnHref(lastSavedProviderId))}
                        >
                            <ArrowLeft className="w-4 h-4 mr-2" />
                            Back to Edit Agent
                        </Button>
                    </div>
                </div>
            )}

            <div className="flex flex-wrap justify-between items-center gap-3">
                <div>
                    <h1 className="text-[26px] font-bold tracking-[-0.02em] text-gray-900 dark:text-white">LLM Providers</h1>
                    <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                        Configure OpenAI-compatible LLM providers for your agents.
                    </p>
                </div>
                <Button onClick={handleCreate}>
                    <Plus className="w-4 h-4 mr-2" />
                    Add Provider
                </Button>
            </div>

            {message && (
                <div className={`p-4 rounded-md ${message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                    {message.text}
                </div>
            )}

            {/* List */}
            <div className="bg-white dark:bg-gray-800 shadow rounded-xl border border-gray-200 dark:border-gray-700 overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                    <thead className="bg-gray-50 dark:bg-gray-900">
                        <tr>
                            <th className="px-6 py-3 text-left text-[12.5px] font-medium text-gray-500 dark:text-gray-400">Name</th>
                            <th className="px-6 py-3 text-left text-[12.5px] font-medium text-gray-500 dark:text-gray-400">Base URL</th>
                            <th className="px-6 py-3 text-center text-[12.5px] font-medium text-gray-500 dark:text-gray-400">Default</th>
                            <th className="px-6 py-3 text-right text-[12.5px] font-medium text-gray-500 dark:text-gray-400">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                        {providers.length === 0 ? (
                            <tr>
                                <td colSpan={4} className="px-6 py-4 text-center text-sm text-gray-500 dark:text-gray-400">
                                    No providers configured. Add one to get started.
                                </td>
                            </tr>
                        ) : (
                            providers.map((provider) => (
                                <tr key={provider.id}>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                                        {provider.name}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400 font-mono">
                                        {provider.base_url}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400 text-center">
                                        {provider.is_default && <Check className="w-4 h-4 text-green-500 mx-auto" />}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        <button type="button" className="text-blue-600 hover:text-blue-900 dark:hover:text-blue-400 mr-4" onClick={() => setModelsProvider(provider)} aria-label={`Manage models for ${provider.name}`}>Models</button>
                                        <button type="button" aria-label={`Edit provider ${provider.name}`} title="Edit provider" className="text-blue-600 hover:text-blue-900 dark:hover:text-blue-400 mr-4" onClick={() => handleEdit(provider)}>
                                            <Edit2 className="w-4 h-4" />
                                        </button>
                                        <button type="button" aria-label={`Delete provider ${provider.name}`} title="Delete provider" className="text-red-600 hover:text-red-900 dark:hover:text-red-400" onClick={() => handleDelete(provider.id)}>
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {modelsProvider && <ProviderModels provider={modelsProvider} providers={providers} onClose={() => setModelsProvider(null)} />}

            {/* Edit Modal */}
            {isEditing && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
                    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-lg w-full max-h-[calc(100dvh-2rem)] overflow-y-auto p-6 animate-in fade-in zoom-in-95 duration-200">
                        <div className="flex justify-between items-center mb-6">
                            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                                {currentProvider.id ? "Edit Provider" : "New Provider"}
                            </h2>
                            <button type="button" aria-label="Close provider settings" onClick={() => setIsEditing(false)} className="text-gray-400 hover:text-gray-500">
                                <X className="w-6 h-6" />
                            </button>
                        </div>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
                                <input
                                    type="text"
                                    value={currentProvider.name || ""}
                                    onChange={(e) => setCurrentProvider({ ...currentProvider, name: e.target.value })}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md dark:bg-gray-900 dark:text-white"
                                    placeholder="e.g. OpenAI, DeepSeek, Local"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Base URL</label>
                                <input
                                    type="text"
                                    value={currentProvider.base_url || ""}
                                    onChange={(e) => setCurrentProvider({ ...currentProvider, base_url: e.target.value })}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md dark:bg-gray-900 dark:text-white font-mono"
                                    placeholder="https://api.openai.com/v1"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">API Key</label>
                                <input
                                    type="password"
                                    value={currentProvider.api_key || ""}
                                    onChange={(e) => setCurrentProvider({ ...currentProvider, api_key: e.target.value })}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md dark:bg-gray-900 dark:text-white font-mono"
                                    placeholder="sk-..."
                                />
                            </div>
                            <div className="flex items-center">
                                <input
                                    type="checkbox"
                                    id="is_default"
                                    checked={currentProvider.is_default || false}
                                    onChange={(e) => setCurrentProvider({ ...currentProvider, is_default: e.target.checked })}
                                    className="h-4 w-4 text-blue-600 border-gray-300 rounded"
                                />
                                <label htmlFor="is_default" className="ml-2 block text-sm text-gray-700 dark:text-gray-300">
                                    Set as Default Provider
                                </label>
                            </div>

                            {testResult && (
                                <div className={`p-3 rounded-md text-sm ${testResult.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                                    {testResult.message}
                                </div>
                            )}

                            <div className="flex flex-wrap justify-between gap-3 pt-4">
                                <Button variant="outline" onClick={testConnection} disabled={isTesting || !currentProvider.id}>
                                    {isTesting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <LinkIcon className="w-4 h-4 mr-2" />}
                                    Test Connection
                                </Button>
                                <div className="space-x-2">
                                    <Button variant="outline" onClick={() => setIsEditing(false)}>Cancel</Button>
                                    <Button onClick={handleSave} disabled={isSaving}>
                                        {isSaving && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
                                        Save
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

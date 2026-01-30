"use client";

import { useState, useEffect } from "react";
import { Button } from "./ui/Button";
import {
  getAllApiKeys,
  createApiKey,
  updateApiKey,
  deleteApiKey,
  type ApiKey,
} from "@/lib/apiKeys";

interface ApiKeyManagerProps {
  onApiKeySelect?: (apiKey: string) => void;
  onSlugSelect?: (slug: string) => void;
}

export function ApiKeyManager({ onApiKeySelect, onSlugSelect }: ApiKeyManagerProps) {
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyExpireDays, setNewKeyExpireDays] = useState<number | "">("");
  const [newKeyDomains, setNewKeyDomains] = useState("localhost");
  const [newKeyVoiceResponse, setNewKeyVoiceResponse] = useState(true);
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [error, setError] = useState<string>("");
  const [token, setToken] = useState<string | null>(null);

  // Edit state
  const [editingKeyId, setEditingKeyId] = useState<number | null>(null);
  const [editDomains, setEditDomains] = useState("");
  const [editVoiceResponse, setEditVoiceResponse] = useState(true);

  // Check for token on mount and when storage changes
  useEffect(() => {
    const checkToken = () => {
      if (typeof window !== "undefined") {
        const storedToken = localStorage.getItem("adminToken");
        setToken(storedToken);
      }
    };

    checkToken();

    // Listen for storage changes (e.g., after login)
    window.addEventListener("storage", checkToken);

    // Custom event for same-window token changes
    window.addEventListener("tokenChanged", checkToken);

    return () => {
      window.removeEventListener("storage", checkToken);
      window.removeEventListener("tokenChanged", checkToken);
    };
  }, []);

  useEffect(() => {
    loadApiKeys();
  }, [token]); // Re-load when token changes

  const loadApiKeys = async (): Promise<ApiKey[] | undefined> => {
    setError("");
    if (!token) {
      setError("Not authenticated");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const keys = await getAllApiKeys(token);
      setApiKeys(keys);
      // ... logic continues ...

      // Auto-select the first active key
      const firstActive = keys.find((k) => k.is_active);
      if (firstActive && !selectedKey) {
        setSelectedKey(firstActive.key);
        onApiKeySelect?.(firstActive.key);
        onSlugSelect?.(firstActive.slug || "");
      }
      return keys;
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to load API keys";

      // Suppress error if it's likely just an empty list or specific fetch error
      // specifically "Failed to fetch API keys" which is thrown when response is not OK (e.g. 404 for empty list)
      if (
        errorMessage === "Failed to fetch API keys" ||
        errorMessage.includes("Failed to fetch") ||
        !errorMessage.includes("Not authenticated")
      ) {
        console.warn(
          "Suppressing API key load error, assuming empty list:",
          errorMessage
        );
        setApiKeys([]);
        setError(""); // Force clear error
      } else {
        setError(errorMessage);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !newKeyName.trim()) return;

    try {
      setCreating(true);
      setError("");

      // Parse domains from comma-separated string
      const allowedDomains = newKeyDomains
        .split(",")
        .map((d) => d.trim())
        .filter((d) => d.length > 0);

      const result = await createApiKey(token, {
        name: newKeyName.trim(),
        expires_days: newKeyExpireDays || undefined,
        allowed_domains: allowedDomains.length > 0 ? allowedDomains : undefined,
        voice_response_enabled: newKeyVoiceResponse,
      });

      // Extract API key from message
      const keyMatch = result.message.match(/Key: (sk_\w+)/);
      if (keyMatch) {
        const newKey = keyMatch[1];
        // Copy to clipboard
        navigator.clipboard.writeText(newKey);

        // Show alert with the key
        alert(
          `API Key created successfully!\n\n${newKey}\n\nThe key has been copied to your clipboard. Save it now - it won't be shown again!`
        );

        // We need to reload keys to get the slug for this new key
        const updatedKeys = await loadApiKeys();

        // Find the new key to select it properly with slug
        const createdKeyData = updatedKeys?.find(k => k.key === newKey);
        if (createdKeyData) {
          setSelectedKey(createdKeyData.key);
          onApiKeySelect?.(createdKeyData.key);
          onSlugSelect?.(createdKeyData.slug || "");
        }
      } else {
        // Fallback if we can't parse the key (shouldn't happen)
        await loadApiKeys();
      }

      // Reset form
      setNewKeyName("");
      setNewKeyExpireDays("");
      setNewKeyDomains("");
      setNewKeyVoiceResponse(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create API key");
    } finally {
      setCreating(false);
    }
  };

  const handleToggleActive = async (keyId: number, isActive: boolean) => {
    if (!token) return;

    try {
      await updateApiKey(token, keyId, { is_active: !isActive });
      await loadApiKeys();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update API key"
      );
    }
  };

  const handleDelete = async (keyId: number) => {
    if (!token) return;
    if (
      !confirm(
        "Are you sure you want to delete this API key? This action cannot be undone."
      )
    ) {
      return;
    }

    try {
      await deleteApiKey(token, keyId);
      await loadApiKeys();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete API key"
      );
    }
  };

  const handleCopyKey = (key: string, id: number) => {
    navigator.clipboard.writeText(key);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleSelectKey = (key: string, slug: string = "") => {
    setSelectedKey(key);
    onApiKeySelect?.(key);
    onSlugSelect?.(slug);
  };

  // Edit Handlers
  const handleEditStart = (apiKey: ApiKey) => {
    setEditingKeyId(apiKey.id);
    setEditDomains(
      apiKey.allowed_domains ? apiKey.allowed_domains.join(", ") : ""
    );
    setEditVoiceResponse(apiKey.voice_response_enabled ?? true);
  };

  const handleEditCancel = () => {
    setEditingKeyId(null);
    setEditDomains("");
    setEditVoiceResponse(true);
  };

  const handleEditSave = async (keyId: number) => {
    if (!token) return;

    try {
      // Parse domains
      const allowedDomains = editDomains
        .split(",")
        .map((d) => d.trim())
        .filter((d) => d.length > 0);

      await updateApiKey(token, keyId, {
        allowed_domains: allowedDomains.length > 0 ? allowedDomains : undefined,
        voice_response_enabled: editVoiceResponse,
      });

      setEditingKeyId(null);
      setEditDomains("");
      setEditVoiceResponse(true);
      await loadApiKeys();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update API key"
      );
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-gray-500 dark:text-gray-400">
          Loading API keys...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          API Keys
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Create and manage API keys for widget authentication.
        </p>
      </div>

      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-lg text-sm">
          {error}
        </div>
      )}

      {/* Create New Key Form */}
      <form
        onSubmit={handleCreate}
        className="bg-gray-50 dark:bg-gray-900/50 p-4 rounded-lg border border-gray-200 dark:border-gray-700"
      >
        <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
          Create New API Key
        </h4>
        <div className="space-y-3">
          <div>
            <label
              htmlFor="keyName"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Key Name
            </label>
            <input
              id="keyName"
              type="text"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="e.g., Production Widget, Staging Widget"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
              required
            />
          </div>
          <div>
            <label
              htmlFor="expireDays"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Expires in (days) - Optional
            </label>
            <input
              id="expireDays"
              type="number"
              min="1"
              value={newKeyExpireDays}
              onChange={(e) =>
                setNewKeyExpireDays(e.target.value ? parseInt(e.target.value) : "")
              }
              placeholder="Leave empty for no expiration"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
            />
          </div>
          <div>
            <label
              htmlFor="allowedDomains"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Allowed Domains (Optional)
            </label>
            <input
              id="allowedDomains"
              type="text"
              value={newKeyDomains}
              onChange={(e) => setNewKeyDomains(e.target.value)}
              placeholder="example.com, localhost, 127.0.0.1"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Comma-separated list of allowed domains. Leave empty to allow all
              origins.
            </p>
          </div>
          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={newKeyVoiceResponse}
                onChange={(e) => setNewKeyVoiceResponse(e.target.checked)}
                className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600"
              />
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Enable Voice Responses (TTS)
              </span>
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 ml-6">
              When disabled, the AI will respond with text only. Users can still use voice input.
            </p>
          </div>
          <Button
            type="submit"
            disabled={creating || !newKeyName.trim()}
            variant="primary"
            size="sm"
            className="w-full"
          >
            {creating ? "Creating..." : "Create API Key"}
          </Button>
        </div>
      </form>

      {/* API Keys List */}
      <div className="space-y-3">
        <h4 className="text-sm font-medium text-gray-900 dark:text-white">
          Your API Keys ({apiKeys.length})
        </h4>

        {apiKeys.length === 0 ? (
          <div className="text-center p-8 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700">
            <p className="text-gray-500 dark:text-gray-400 text-sm">
              No API keys yet. Create one to get started.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {apiKeys.map((apiKey) => (
              <div
                key={apiKey.id}
                className={`p-4 rounded-lg border transition-all ${selectedKey === apiKey.key
                  ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                  : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800"
                  }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <h5 className="font-medium text-gray-900 dark:text-white text-sm">
                        {apiKey.name}
                      </h5>
                      {apiKey.is_active ? (
                        <span className="px-2 py-0.5 text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded">
                          Active
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded">
                          Inactive
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 mb-2">
                      <code className="text-xs bg-gray-100 dark:bg-gray-900 px-2 py-1 rounded font-mono text-gray-700 dark:text-gray-300 break-all">
                        {apiKey.key}
                      </code>
                      <button
                        onClick={() => handleCopyKey(apiKey.key, apiKey.id)}
                        className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 text-xs whitespace-nowrap"
                      >
                        {copiedId === apiKey.id ? "Copied!" : "Copy"}
                      </button>
                    </div>

                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                      <span>Usage: {apiKey.usage_count} times</span>
                      {apiKey.last_used_at && (
                        <span>
                          Last used:{" "}
                          {new Date(apiKey.last_used_at).toLocaleDateString()}
                        </span>
                      )}
                      {apiKey.expires_at && (
                        <span
                          className={
                            new Date(apiKey.expires_at) < new Date()
                              ? "text-red-600 dark:text-red-400"
                              : ""
                          }
                        >
                          Expires:{" "}
                          {new Date(apiKey.expires_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>

                    {/* Allowed Domains & Voice Response Section */}
                    {editingKeyId === apiKey.id ? (
                      <div className="mt-2 space-y-3">
                        <div>
                          <label className="text-xs font-medium text-gray-700 dark:text-gray-300 block mb-1">
                            Edit Allowed Domains (Comma-separated)
                          </label>
                          <input
                            type="text"
                            value={editDomains}
                            onChange={(e) => setEditDomains(e.target.value)}
                            className="w-full px-2 py-1 text-xs border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-1 focus:ring-blue-500"
                          />
                        </div>
                        <div>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={editVoiceResponse}
                              onChange={(e) => setEditVoiceResponse(e.target.checked)}
                              className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600"
                            />
                            <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                              Enable Voice Responses (TTS)
                            </span>
                          </label>
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleEditSave(apiKey.id)}
                            className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                          >
                            Save
                          </button>
                          <button
                            onClick={handleEditCancel}
                            className="text-xs px-2 py-1 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      apiKey.allowed_domains &&
                      apiKey.allowed_domains.length > 0 && (
                        <div className="mt-2">
                          <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                            Allowed Domains:
                          </span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {apiKey.allowed_domains.map((domain, idx) => (
                              <span
                                key={idx}
                                className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded"
                              >
                                {domain}
                              </span>
                            ))}
                          </div>
                        </div>
                      )
                    )}
                  </div>

                  <div className="flex flex-col gap-2">
                    <Button
                      onClick={() => {
                        setSelectedKey(apiKey.key);
                        onApiKeySelect?.(apiKey.key);
                        onSlugSelect?.(apiKey.slug || "");
                      }}
                      size="sm"
                      variant={
                        selectedKey === apiKey.key ? "primary" : "outline"
                      }
                      disabled={!apiKey.is_active}
                    >
                      {selectedKey === apiKey.key ? "Selected" : "Select"}
                    </Button>

                    <div className="flex gap-2">
                      <button
                        onClick={() =>
                          handleToggleActive(apiKey.id, apiKey.is_active)
                        }
                        className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300"
                      >
                        {apiKey.is_active ? "Disable" : "Enable"}
                      </button>

                      {/* Only show edit button if not currently editing this key */}
                      {editingKeyId !== apiKey.id && (
                        <button
                          onClick={() => handleEditStart(apiKey)}
                          className="text-xs px-2 py-1 rounded border border-blue-300 dark:border-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 text-blue-600 dark:text-blue-400"
                        >
                          Edit
                        </button>
                      )}

                      <button
                        onClick={() => handleDelete(apiKey.id)}
                        className="text-xs px-2 py-1 rounded border border-red-300 dark:border-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600 dark:text-red-400"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

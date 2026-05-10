"use client";

import { useState, useEffect } from "react";
import { X, Loader2, AlertCircle } from "lucide-react";
import MultiFileUploader from "./MultiFileUploader";
import { getApiBaseUrl } from "@/lib/api";

interface CreateFileStoreModalProps {
  teamAgentId?: number | null;
  assignAgentId?: number | null;
  onClose: () => void;
  onSuccess: () => void;
}

interface ExistingFileStore {
  id: number;
  display_name: string;
}

export default function CreateFileStoreModal({
  teamAgentId,
  assignAgentId,
  onClose,
  onSuccess,
}: CreateFileStoreModalProps) {
  const apiBaseUrl = getApiBaseUrl();
  const [displayName, setDisplayName] = useState("");
  const [createTool, setCreateTool] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [existingStores, setExistingStores] = useState<ExistingFileStore[]>([]);
  const [nameError, setNameError] = useState<string | null>(null);

  // Fetch existing file stores on mount
  useEffect(() => {
    const fetchExistingStores = async () => {
      try {
        const token = localStorage.getItem("adminToken");
        const teamQuery = teamAgentId ? `?team_agent_id=${teamAgentId}` : "";
        const response = await fetch(`${apiBaseUrl}/api/admin/file-stores${teamQuery}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const data = await response.json();
          setExistingStores(data);
        }
      } catch (error) {
        console.error("Failed to fetch existing stores:", error);
      }
    };
    fetchExistingStores();
  }, [apiBaseUrl]);

  // Validate name when it changes
  useEffect(() => {
    if (displayName.trim()) {
      const isDuplicate = existingStores.some(
        (store) => store.display_name.toLowerCase() === displayName.trim().toLowerCase()
      );
      if (isDuplicate) {
        setNameError("A File Store with this name already exists");
      } else {
        setNameError(null);
      }
    } else {
      setNameError(null);
    }
  }, [displayName, existingStores]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!displayName.trim()) {
      alert("Please enter a display name");
      return;
    }

    if (nameError) {
      alert(nameError);
      return;
    }

    if (files.length === 0) {
      alert("Please upload at least one file");
      return;
    }

    try {
      setCreating(true);

      // Step 1: Create file store
      const token = localStorage.getItem("adminToken");
      const teamQuery = teamAgentId ? `?team_agent_id=${teamAgentId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/file-stores${teamQuery}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          display_name: displayName,
          create_tool: createTool,
          assign_agent_id: assignAgentId || undefined,
        }),
      });

      if (!response.ok) throw new Error("Failed to create file store");

      const result = await response.json();

      // Extract store ID from message
      const match = result.message.match(/ID (\d+)/);
      const createdStoreId = match ? parseInt(match[1]) : null;

      if (!createdStoreId) {
        throw new Error("Could not get store ID from response");
      }

      setCreating(false);
      setUploading(true);

      // Step 2: Upload files
      let uploaded = 0;
      for (const file of files) {
        const formData = new FormData();
        formData.append("file", file);

        const uploadResponse = await fetch(
          `${apiBaseUrl}/api/admin/file-stores/${createdStoreId}/upload`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          }
        );

        if (!uploadResponse.ok) {
          throw new Error(`Failed to upload ${file.name}`);
        }

        uploaded++;
        setUploadProgress(Math.round((uploaded / files.length) * 100));
      }

      setUploading(false);
      onSuccess();
    } catch (error) {
      console.error("Failed to create file store:", error);
      alert(`Failed to create file store: ${error}`);
      setCreating(false);
      setUploading(false);
    }
  };

  const isProcessing = creating || uploading;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Create File Store Agent
          </h2>
          <button
            onClick={onClose}
            disabled={isProcessing}
            className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Display Name */}
          <div>
            <label
              htmlFor="displayName"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
            >
              Display Name
            </label>
            <input
              type="text"
              id="displayName"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              disabled={isProcessing}
              className={`w-full px-3 py-2 border rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 ${
                nameError
                  ? "border-red-500 dark:border-red-500"
                  : "border-gray-300 dark:border-gray-600"
              }`}
              placeholder="e.g., Product Documentation"
              required
            />
            {nameError ? (
              <div className="mt-1 flex items-center gap-1 text-sm text-red-600 dark:text-red-400">
                <AlertCircle className="w-4 h-4" />
                <span>{nameError}</span>
              </div>
            ) : (
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                A descriptive name for your file store
              </p>
            )}
          </div>

          {/* Create Tool Checkbox */}
          <div className="flex items-start">
            <div className="flex items-center h-5">
              <input
                type="checkbox"
                id="createTool"
                checked={createTool}
                onChange={(e) => setCreateTool(e.target.checked)}
                disabled={isProcessing}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 disabled:opacity-50"
              />
            </div>
            <div className="ml-3">
              <label
                htmlFor="createTool"
                className="text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Create Tool Automatically
              </label>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Automatically create a search tool that agents can use to query this file store
              </p>
            </div>
          </div>

          {/* File Uploader */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Upload Files
            </label>
            <MultiFileUploader
              files={files}
              onFilesChange={setFiles}
              disabled={isProcessing}
            />
          </div>

          {/* Progress */}
          {isProcessing && (
            <div className="rounded-md bg-blue-50 dark:bg-blue-900/20 p-4">
              <div className="flex items-center gap-3">
                <Loader2 className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-blue-800 dark:text-blue-300">
                    {creating && "Creating file store..."}
                    {uploading && `Uploading files... ${uploadProgress}%`}
                  </p>
                  {uploading && (
                    <div className="mt-2 w-full bg-blue-200 dark:bg-blue-800 rounded-full h-2">
                      <div
                        className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Buttons */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              type="button"
              onClick={onClose}
              disabled={isProcessing}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isProcessing || !displayName.trim() || files.length === 0 || !!nameError}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {isProcessing && <Loader2 className="w-4 h-4 animate-spin" />}
              {creating ? "Creating..." : uploading ? "Uploading..." : "Create File Store"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

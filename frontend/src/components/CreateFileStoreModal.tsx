"use client";

import { useState } from "react";
import { X, Loader2 } from "lucide-react";
import MultiFileUploader from "./MultiFileUploader";

interface CreateFileStoreModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

export default function CreateFileStoreModal({
  onClose,
  onSuccess,
}: CreateFileStoreModalProps) {
  const [displayName, setDisplayName] = useState("");
  const [createTool, setCreateTool] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!displayName.trim()) {
      alert("Please enter a display name");
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
      const response = await fetch("http://localhost:8000/api/admin/file-stores", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          display_name: displayName,
          create_tool: createTool,
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
          `http://localhost:8000/api/admin/file-stores/${createdStoreId}/upload`,
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
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white disabled:opacity-50"
              placeholder="e.g., Product Documentation"
              required
            />
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              A descriptive name for your file store
            </p>
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
              disabled={isProcessing || !displayName.trim() || files.length === 0}
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

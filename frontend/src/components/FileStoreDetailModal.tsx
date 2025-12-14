"use client";

import { useState, useEffect, useCallback } from "react";
import { X, FileText, Trash2, Upload, Loader2 } from "lucide-react";
import MultiFileUploader from "./MultiFileUploader";
import { getApiBaseUrl } from "@/lib/api";

interface FileStore {
  id: number;
  name: string;
  gemini_store_id: string;
  display_name: string;
  file_count: number;
  created_at: string;
}

interface FileStoreFile {
  id: number;
  filename: string;
  original_filename: string;
  file_size: number;
  uploaded_at: string;
}

interface FileStoreDetailModalProps {
  store: FileStore;
  onClose: () => void;
}

export default function FileStoreDetailModal({
  store,
  onClose,
}: FileStoreDetailModalProps) {
  const apiBaseUrl = getApiBaseUrl();
  const [files, setFiles] = useState<FileStoreFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [newFiles, setNewFiles] = useState<File[]>([]);
  const [deleting, setDeleting] = useState<number | null>(null);

  const fetchFiles = useCallback(async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/file-stores/${store.id}/files`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (!response.ok) throw new Error("Failed to fetch files");

      const data = await response.json();
      setFiles(data);
    } catch (error) {
      console.error("Failed to fetch files:", error);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, store.id]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  const handleUploadFiles = async () => {
    if (newFiles.length === 0) {
      alert("Please select at least one file to upload");
      return;
    }

    try {
      setUploading(true);
      const token = localStorage.getItem("adminToken");

      let uploaded = 0;
      for (const file of newFiles) {
        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch(
          `${apiBaseUrl}/api/admin/file-stores/${store.id}/upload`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
          }
        );

        if (!response.ok) {
          throw new Error(`Failed to upload ${file.name}`);
        }

        uploaded++;
        setUploadProgress(Math.round((uploaded / newFiles.length) * 100));
      }

      setNewFiles([]);
      setUploadProgress(0);
      fetchFiles();
    } catch (error) {
      console.error("Failed to upload files:", error);
      alert(`Failed to upload files: ${error}`);
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteFile = async (fileId: number, filename: string) => {
    if (!confirm(`Are you sure you want to delete "${filename}"?`)) {
      return;
    }

    try {
      setDeleting(fileId);
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/file-stores/${store.id}/files/${fileId}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (!response.ok) throw new Error("Failed to delete file");

      fetchFiles();
    } catch (error) {
      console.error("Failed to delete file:", error);
      alert("Failed to delete file");
    } finally {
      setDeleting(null);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Manage Files - {store.display_name}
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {files.length} file{files.length !== 1 ? "s" : ""} in this store
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={uploading}
            className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Store Information */}
          <div className="rounded-md bg-blue-50 dark:bg-blue-900/20 p-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-600 dark:text-gray-400">Store Name:</span>
                <span className="ml-2 font-medium text-gray-900 dark:text-white">
                  {store.name}
                </span>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400">Created:</span>
                <span className="ml-2 font-medium text-gray-900 dark:text-white">
                  {new Date(store.created_at).toLocaleDateString()}
                </span>
              </div>
              <div className="col-span-2">
                <span className="text-gray-600 dark:text-gray-400">Gemini Store ID:</span>
                <span className="ml-2 font-mono text-xs text-gray-900 dark:text-white">
                  {store.gemini_store_id}
                </span>
              </div>
            </div>
          </div>

          {/* File List */}
          <div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
              Current Files
            </h3>

            {loading ? (
              <div className="text-center py-8 text-gray-600 dark:text-gray-400">
                Loading files...
              </div>
            ) : files.length === 0 ? (
              <div className="text-center py-8 text-gray-600 dark:text-gray-400">
                No files in this store yet. Upload some files below.
              </div>
            ) : (
              <div className="space-y-2">
                {files.map((file) => (
                  <div
                    key={file.id}
                    className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-900 rounded-md border border-gray-200 dark:border-gray-700"
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <FileText className="w-5 h-5 text-gray-400 flex-shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                          {file.original_filename}
                        </p>
                        <div className="flex items-center gap-3 mt-1">
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            {formatFileSize(file.file_size)}
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            Uploaded: {formatDate(file.uploaded_at)}
                          </p>
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteFile(file.id, file.original_filename)}
                      disabled={deleting === file.id || uploading}
                      className="ml-4 p-2 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/20 rounded-md disabled:opacity-50 transition-colors"
                      title="Delete file"
                    >
                      {deleting === file.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Upload More Files */}
          <div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
              Upload More Files
            </h3>

            <MultiFileUploader
              files={newFiles}
              onFilesChange={setNewFiles}
              disabled={uploading}
            />

            {uploading && (
              <div className="mt-4 rounded-md bg-blue-50 dark:bg-blue-900/20 p-4">
                <div className="flex items-center gap-3">
                  <Loader2 className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-blue-800 dark:text-blue-300">
                      Uploading files... {uploadProgress}%
                    </p>
                    <div className="mt-2 w-full bg-blue-200 dark:bg-blue-800 rounded-full h-2">
                      <div
                        className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {newFiles.length > 0 && !uploading && (
              <div className="mt-4 flex justify-end">
                <button
                  onClick={handleUploadFiles}
                  className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md"
                >
                  <Upload className="w-4 h-4" />
                  Upload {newFiles.length} file{newFiles.length !== 1 ? "s" : ""}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onClose}
            disabled={uploading}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md disabled:opacity-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

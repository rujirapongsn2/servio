"use client";

import { useRef } from "react";
import { Upload, X, FileText, AlertCircle } from "lucide-react";

// Currently only PDF is supported by Gemini File Store
const ALLOWED_EXTENSIONS = [".pdf"];
const ALLOWED_MIME_TYPES = ["application/pdf"];
const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;

interface MultiFileUploaderProps {
  files: File[];
  onFilesChange: (files: File[]) => void;
  disabled?: boolean;
}

export default function MultiFileUploader({
  files,
  onFilesChange,
  disabled = false,
}: MultiFileUploaderProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isValidFile = (file: File): boolean => {
    const extension = "." + file.name.split(".").pop()?.toLowerCase();
    const isAllowedType =
      ALLOWED_EXTENSIONS.includes(extension) || ALLOWED_MIME_TYPES.includes(file.type);
    return isAllowedType && file.size <= MAX_FILE_SIZE_BYTES;
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files);
      const validFiles = newFiles.filter(isValidFile);
      const invalidFiles = newFiles.filter((f) => !isValidFile(f));

      if (invalidFiles.length > 0) {
        alert(
          `The following files were skipped:\n${invalidFiles.map((f) => f.name).join("\n")}\n\nOnly PDF files up to 50MB per file are supported.`
        );
      }

      if (validFiles.length > 0) {
        onFilesChange([...files, ...validFiles]);
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (disabled) return;

    if (e.dataTransfer.files) {
      const newFiles = Array.from(e.dataTransfer.files);
      const validFiles = newFiles.filter(isValidFile);
      const invalidFiles = newFiles.filter((f) => !isValidFile(f));

      if (invalidFiles.length > 0) {
        alert(
          `The following files were skipped:\n${invalidFiles.map((f) => f.name).join("\n")}\n\nOnly PDF files up to 50MB per file are supported.`
        );
      }

      if (validFiles.length > 0) {
        onFilesChange([...files, ...validFiles]);
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const removeFile = (index: number) => {
    onFilesChange(files.filter((_, i) => i !== index));
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => !disabled && fileInputRef.current?.click()}
        className={`
          border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
          ${
            disabled
              ? "border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 cursor-not-allowed opacity-50"
              : "border-gray-300 dark:border-gray-600 hover:border-blue-400 dark:hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/10"
          }
        `}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileSelect}
          disabled={disabled}
          className="hidden"
          accept=".pdf"
        />
        <Upload className="w-12 h-12 text-gray-400 mx-auto mb-4" />
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
          <span className="font-medium text-blue-600 dark:text-blue-400">
            Click to upload
          </span>{" "}
          or drag and drop
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-500">
          PDF files only (max 50MB per file)
        </p>
      </div>

      {/* File List */}
      {files.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Selected Files ({files.length})
          </p>
          <div className="space-y-2">
            {files.map((file, index) => (
              <div
                key={index}
                className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-900 rounded-md border border-gray-200 dark:border-gray-700"
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <FileText className="w-5 h-5 text-gray-400 flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {file.name}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {formatFileSize(file.size)}
                    </p>
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFile(index);
                  }}
                  disabled={disabled}
                  className="p-1 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded disabled:opacity-50"
                  title="Remove file"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

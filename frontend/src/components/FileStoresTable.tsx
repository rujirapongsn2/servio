"use client";

import { useEffect, useState } from "react";
import { Database, Plus, FileText, Play, Trash2, Upload } from "lucide-react";
import CreateFileStoreModal from "./CreateFileStoreModal";
import FileStoreDetailModal from "./FileStoreDetailModal";
import TestFileStoreModal from "./TestFileStoreModal";

interface FileStore {
  id: number;
  name: string;
  gemini_store_id: string;
  display_name: string;
  file_count: number;
  created_at: string;
}

export default function FileStoresTable() {
  const [stores, setStores] = useState<FileStore[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedStore, setSelectedStore] = useState<FileStore | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showTestModal, setShowTestModal] = useState(false);

  useEffect(() => {
    fetchStores();
  }, []);

  const fetchStores = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch("http://localhost:8000/api/admin/file-stores", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) throw new Error("Failed to fetch file stores");

      const data = await response.json();
      setStores(data);
    } catch (error) {
      console.error("Failed to fetch file stores:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: number, displayName: string) => {
    if (!confirm(`Are you sure you want to delete "${displayName}"? This will also delete all uploaded files.`)) {
      return;
    }

    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `http://localhost:8000/api/admin/file-stores/${id}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (!response.ok) throw new Error("Failed to delete file store");

      fetchStores();
    } catch (error) {
      console.error("Failed to delete file store:", error);
      alert("Failed to delete file store");
    }
  };

  const handleShowFiles = (store: FileStore) => {
    setSelectedStore(store);
    setShowDetailModal(true);
  };

  const handleTest = (store: FileStore) => {
    setSelectedStore(store);
    setShowTestModal(true);
  };

  if (loading) {
    return (
      <div className="text-gray-600 dark:text-gray-400">Loading file stores...</div>
    );
  }

  return (
    <>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            File Store Agents use Gemini File Search to answer questions about your documents
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700"
          >
            <Plus className="w-4 h-4" />
            New File Store
          </button>
        </div>

        {stores.length === 0 ? (
          <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
            <Database className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              No file stores found. Create your first file store to get started.
            </p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700"
            >
              Create File Store
            </button>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 shadow overflow-hidden sm:rounded-lg border border-gray-200 dark:border-gray-700">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-900">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Name
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Files
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Store ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Created
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {stores.map((store) => (
                  <tr key={store.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        <div className="flex-shrink-0 w-10 h-10 bg-purple-100 dark:bg-purple-900/20 rounded-lg flex items-center justify-center">
                          <Database className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                        </div>
                        <div>
                          <div className="text-sm font-medium text-gray-900 dark:text-white">
                            {store.display_name}
                          </div>
                          <div className="text-sm text-gray-500 dark:text-gray-400">
                            {store.name}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-gray-400" />
                        <span className="text-sm text-gray-900 dark:text-white">
                          {store.file_count} file{store.file_count !== 1 ? "s" : ""}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="text-xs font-mono text-gray-500 dark:text-gray-400">
                        {store.gemini_store_id.split("/")[1]?.substring(0, 12)}...
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {new Date(store.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleTest(store)}
                          className="p-2 text-green-600 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/20 rounded-md transition-colors"
                          title="Test Store"
                        >
                          <Play className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleShowFiles(store)}
                          className="p-2 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/20 rounded-md transition-colors"
                          title="Manage Files"
                        >
                          <Upload className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(store.id, store.display_name)}
                          className="p-2 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/20 rounded-md transition-colors"
                          title="Delete Store"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modals */}
      {showCreateModal && (
        <CreateFileStoreModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            setShowCreateModal(false);
            fetchStores();
          }}
        />
      )}

      {showDetailModal && selectedStore && (
        <FileStoreDetailModal
          store={selectedStore}
          onClose={() => {
            setShowDetailModal(false);
            setSelectedStore(null);
            fetchStores();
          }}
        />
      )}

      {showTestModal && selectedStore && (
        <TestFileStoreModal
          store={selectedStore}
          onClose={() => {
            setShowTestModal(false);
            setSelectedStore(null);
          }}
        />
      )}
    </>
  );
}

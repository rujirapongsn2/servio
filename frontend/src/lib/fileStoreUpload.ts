"use client";

export interface FileUploadJobStartResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface FileUploadJobStatus {
  job_id: string;
  file_store_id: number;
  filename: string;
  status: "queued" | "processing" | "completed" | "failed";
  progress: number;
  stage: string;
  error?: string | null;
  uploaded_at?: string | null;
  completed_at?: string | null;
}

interface UploadFileToStoreParams {
  apiBaseUrl: string;
  token: string;
  storeId: number;
  file: File;
  onUploadProgress?: (progress: number) => void;
}

interface PollUploadJobParams {
  apiBaseUrl: string;
  token: string;
  jobId: string;
  onStatus?: (status: FileUploadJobStatus) => void;
}

export function uploadFileToStore({
  apiBaseUrl,
  token,
  storeId,
  file,
  onUploadProgress,
}: UploadFileToStoreParams): Promise<FileUploadJobStartResponse> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiBaseUrl}/api/admin/file-stores/${storeId}/upload`);
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.responseType = "json";

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || !onUploadProgress) return;
      onUploadProgress(Math.round((event.loaded / event.total) * 100));
    };

    xhr.onload = () => {
      const response = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300 && response) {
        resolve(response as FileUploadJobStartResponse);
        return;
      }

      const detail =
        response && typeof response === "object" && "detail" in response
          ? String(response.detail)
          : `Upload failed with status ${xhr.status}`;
      reject(new Error(detail));
    };

    xhr.onerror = () => reject(new Error("Network error while uploading file"));
    xhr.send(formData);
  });
}

export async function pollFileUploadJob({
  apiBaseUrl,
  token,
  jobId,
  onStatus,
}: PollUploadJobParams): Promise<FileUploadJobStatus> {
  while (true) {
    const response = await fetch(`${apiBaseUrl}/api/admin/file-stores/upload-jobs/${jobId}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error("Failed to check upload status");
    }

    const status = (await response.json()) as FileUploadJobStatus;
    onStatus?.(status);

    if (status.status === "completed") {
      return status;
    }

    if (status.status === "failed") {
      throw new Error(status.error || "File processing failed");
    }

    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}

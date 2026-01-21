import { buildApiUrl } from "./api";

export interface ApiKey {
  id: number;
  name: string;
  key: string;
  is_active: boolean;
  usage_count: number;
  last_used_at: string | null;
  expires_at: string | null;
  created_by: string | null;
  allowed_domains: string[] | null;
  voice_response_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateApiKeyRequest {
  name: string;
  expires_days?: number;
  allowed_domains?: string[];
  voice_response_enabled?: boolean;
}

export interface UpdateApiKeyRequest {
  name?: string;
  is_active?: boolean;
  expires_at?: string;
  allowed_domains?: string[];
  voice_response_enabled?: boolean;
}

export async function getAllApiKeys(token: string): Promise<ApiKey[]> {
  const response = await fetch(buildApiUrl("/api/admin/api-keys"), {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("Failed to fetch API keys");
  }

  return response.json();
}

export async function createApiKey(
  token: string,
  data: CreateApiKeyRequest
): Promise<{ message: string }> {
  const response = await fetch(buildApiUrl("/api/admin/api-keys"), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to create API key");
  }

  return response.json();
}

export async function updateApiKey(
  token: string,
  keyId: number,
  data: UpdateApiKeyRequest
): Promise<{ message: string }> {
  const response = await fetch(buildApiUrl(`/api/admin/api-keys/${keyId}`), {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to update API key");
  }

  return response.json();
}

export async function deleteApiKey(
  token: string,
  keyId: number
): Promise<{ message: string }> {
  const response = await fetch(buildApiUrl(`/api/admin/api-keys/${keyId}`), {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to delete API key");
  }

  return response.json();
}

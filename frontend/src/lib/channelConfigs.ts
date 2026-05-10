import { buildApiUrl } from "./api";

export type MessagingChannelType = "line" | "facebook";

export interface ChannelConfig {
  id: number;
  type: MessagingChannelType;
  name: string;
  config: Record<string, string>;
  is_active: boolean;
  team_agent_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface UpdateChannelConfigRequest {
  name: string;
  config: Record<string, string>;
  is_active: boolean;
}

export async function getChannelConfigs(token: string, teamAgentId?: number | null): Promise<ChannelConfig[]> {
  const params = teamAgentId ? `?team_agent_id=${teamAgentId}` : "";
  const response = await fetch(buildApiUrl(`/api/admin/channel-configs${params}`), {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("Failed to fetch channel configs");
  }

  return response.json();
}

export async function updateChannelConfig(
  token: string,
  channelType: MessagingChannelType,
  data: UpdateChannelConfigRequest,
  teamAgentId?: number | null
): Promise<ChannelConfig> {
  const params = teamAgentId ? `?team_agent_id=${teamAgentId}` : "";
  const response = await fetch(buildApiUrl(`/api/admin/channel-configs/${channelType}${params}`), {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to update channel config");
  }

  return response.json();
}

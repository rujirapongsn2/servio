import { workflowRequest } from "./team-workflow";

type CommonChannel = {
  id: number; name: string; team_id: number | null; team_name: string;
  team_active: boolean; can_edit: boolean; is_active: boolean;
  status: "active" | "paused" | "expired" | "incomplete"; updated_at: string | null;
};
export type OverviewChannel = CommonChannel & (
  { kind: "web"; channel_type: "web_widget" | "api"; slug: string | null;
    allowed_domains: string[]; voice_response_enabled: boolean; expires_at: string | null; usage_count: number }
  | { kind: "messaging"; channel_type: "line" | "facebook"; identifier: string;
      configured_fields: string[]; required_fields: string[] }
);
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
function record(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) throw new Error("Invalid channel data");
  return value;
}
function str(value: unknown): string { if (typeof value !== "string") throw new Error("Invalid channel text"); return value; }
function bool(value: unknown): boolean { if (typeof value !== "boolean") throw new Error("Invalid channel state"); return value; }
function num(value: unknown): number { if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new Error("Invalid channel ID"); return value; }
function strings(value: unknown): string[] { if (!Array.isArray(value)) throw new Error("Invalid channel list"); return value.map(str); }
function nullable(value: unknown): string | null { return value === null ? null : str(value); }
export function parseChannelOverview(value: unknown): OverviewChannel[] {
  if (!Array.isArray(value)) throw new Error("Invalid channel overview");
  return value.map((item): OverviewChannel => {
    const v = record(item);
    const status = v.status;
    if (status !== "active" && status !== "paused" && status !== "expired" && status !== "incomplete") throw new Error("Invalid status");
    const common: CommonChannel = { id: num(v.id), name: str(v.name), team_id: v.team_id === null ? null : num(v.team_id),
      team_name: str(v.team_name), team_active: bool(v.team_active), can_edit: bool(v.can_edit),
      is_active: bool(v.is_active), status, updated_at: nullable(v.updated_at) };
    if (v.kind === "web" && (v.channel_type === "web_widget" || v.channel_type === "api")) {
      const slug = nullable(v.slug);
      if (slug && !/^[A-Za-z0-9_-]+$/.test(slug)) throw new Error("Invalid chat link");
      return { ...common, kind: "web", channel_type: v.channel_type, slug, allowed_domains: strings(v.allowed_domains),
        voice_response_enabled: bool(v.voice_response_enabled), expires_at: nullable(v.expires_at), usage_count: num(v.usage_count) };
    }
    if (v.kind === "messaging" && (v.channel_type === "line" || v.channel_type === "facebook")) {
      return { ...common, kind: "messaging", channel_type: v.channel_type, identifier: str(v.identifier),
        configured_fields: strings(v.configured_fields), required_fields: strings(v.required_fields) };
    }
    throw new Error("Unknown channel type");
  });
}
export type ChannelDraft = {
  name: string; is_active: boolean; config: Record<string, string>;
  allowed_domains: string; voice_response_enabled: boolean; expires_at: string | null;
  updated_at: string; api_key: string;
};
export function detailPath(row: OverviewChannel): string {
  return row.kind === "web" ? `/api-keys/${row.id}`
    : `/channel-configs/${row.channel_type}${row.team_id === null ? "" : `?team_agent_id=${row.team_id}`}`;
}
export function parseChannelDraft(value: unknown, row: OverviewChannel): ChannelDraft {
  const v = record(value);
  if (num(v.id) !== row.id || v.team_agent_id !== row.team_id) throw new Error("Channel scope changed. Reload the page.");
  const common = { name: str(v.name), is_active: bool(v.is_active), updated_at: str(v.updated_at) };
  if (row.kind === "web") return { ...common, config: {}, allowed_domains: v.allowed_domains === null ? "" : strings(v.allowed_domains).join(", "),
    voice_response_enabled: bool(v.voice_response_enabled), expires_at: nullable(v.expires_at), api_key: str(v.key) };
  if (v.type !== row.channel_type) throw new Error("Channel type changed");
  const config = Object.fromEntries(Object.entries(record(v.config)).map(([k, value]) => [k, str(value)]));
  return { ...common, config, allowed_domains: "", voice_response_enabled: false, expires_at: null, api_key: "" };
}
export async function loadChannelDraft(row: OverviewChannel, signal?: AbortSignal): Promise<ChannelDraft> {
  return parseChannelDraft(await workflowRequest(detailPath(row), { signal }), row);
}
export async function saveChannelDraft(row: OverviewChannel, draft: ChannelDraft, renewal: string): Promise<void> {
  const current = await loadChannelDraft(row);
  if (current.updated_at !== draft.updated_at) throw new Error("This channel changed. Close and reopen it before saving.");
  const body = row.kind === "web" ? { name: draft.name.trim(), is_active: draft.is_active,
    allowed_domains: draft.allowed_domains.split(",").map(v => v.trim()).filter(Boolean),
    voice_response_enabled: draft.voice_response_enabled,
    ...(renewal ? { expires_at: new Date(renewal).toISOString() } : {}) }
    : { name: draft.name.trim(), is_active: draft.is_active, config: draft.config };
  await workflowRequest(detailPath(row), { method: "PUT", body: JSON.stringify(body) });
}
export function channelIdentity(row: OverviewChannel): string { return `${row.kind}-${row.id}`; }
export function channelDate(value: string | null, locale: string): string {
  if (!value) return "—";
  const date = new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : value + "Z");
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

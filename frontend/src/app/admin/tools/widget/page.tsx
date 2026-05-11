"use client";

import { useEffect, useState, type ReactNode } from "react";
import {
  CheckCircle2,
  Code2,
  ExternalLink,
  Globe2,
  KeyRound,
  Link2,
  MessageCircle,
  Radio,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import MicIcon from "@/components/icons/MicIcon";
import WriteIcon from "@/components/icons/WriteIcon";
import { ApiKeyManager } from "@/components/ApiKeyManager";
import ChannelConfigForm from "@/components/ChannelConfigForm";
import { useTeam } from "@/lib/team-context";
import { getChannelConfigs, type ChannelConfig } from "@/lib/channelConfigs";
import { getAllApiKeys, type ApiKey } from "@/lib/apiKeys";

type ChannelType = "web-widget" | "line" | "facebook";

type ChannelDefinition = {
  id: ChannelType;
  name: string;
  label: string;
  icon: ReactNode;
};

const STEPS = ["Choose Team", "Choose Channel Type", "Connect Channel", "Test and Go Live"];

const CHANNELS: ChannelDefinition[] = [
  {
    id: "web-widget",
    name: "Website Chat",
    label: "Website",
    icon: <Globe2 className="h-5 w-5" />,
  },
  {
    id: "line",
    name: "LINE Official Account",
    label: "LINE",
    icon: <MessageCircle className="h-5 w-5" />,
  },
  {
    id: "facebook",
    name: "Facebook Messenger",
    label: "Facebook",
    icon: <Radio className="h-5 w-5" />,
  },
];

function getChannelStatus(type: ChannelType, configs: ChannelConfig[], apiKeys: ApiKey[]) {
  if (type === "web-widget") {
    if (apiKeys.some((key) => key.is_active)) return { label: "Ready", tone: "green" as const };
    if (apiKeys.length > 0) return { label: "Draft", tone: "amber" as const };
    return { label: "Not set", tone: "gray" as const };
  }

  const config = configs.find((item) => item.type === type);
  if (!config) return { label: "Not set", tone: "gray" as const };
  return config.is_active
    ? { label: "Live", tone: "green" as const }
    : { label: "Draft", tone: "amber" as const };
}

function statusClasses(tone: "green" | "amber" | "gray") {
  if (tone === "green") return "border-green-200 bg-green-50 text-green-700";
  if (tone === "amber") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-gray-200 bg-gray-50 text-gray-600";
}

export default function ChannelsPage() {
  const { teams, selectedTeam, selectedTeamId, setSelectedTeamId, loading: teamLoading } = useTeam();
  const [selectedChannel, setSelectedChannel] = useState<ChannelType>("web-widget");
  const [position, setPosition] = useState("bottom-right");
  const [widgetType, setWidgetType] = useState("voice");
  const [allowToggle, setAllowToggle] = useState(true);
  const [copied, setCopied] = useState(false);
  const [selectedApiKey, setSelectedApiKey] = useState("");
  const [selectedSlug, setSelectedSlug] = useState("");
  const [linkCopied, setLinkCopied] = useState(false);
  const [channelConfigs, setChannelConfigs] = useState<ChannelConfig[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);

  const token = typeof window !== "undefined" ? localStorage.getItem("adminToken") || "" : "";
  const serverUrl = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";

  useEffect(() => {
    if (!token || !selectedTeamId) {
      setChannelConfigs([]);
      setApiKeys([]);
      return;
    }

    let cancelled = false;
    Promise.all([
      getChannelConfigs(token, selectedTeamId).catch(() => []),
      getAllApiKeys(token, selectedTeamId).catch(() => []),
    ]).then(([configs, keys]) => {
      if (cancelled) return;
      setChannelConfigs(configs);
      setApiKeys(keys);
    });

    return () => {
      cancelled = true;
    };
  }, [token, selectedTeamId]);

  const selectedChannelMeta = CHANNELS.find((channel) => channel.id === selectedChannel) ?? CHANNELS[0];

  const embedCode = selectedApiKey
    ? `<script src="${serverUrl}/embed.js" data-position="${position}" data-type="${widgetType}" data-allow-toggle="${allowToggle}" data-server-url="${serverUrl}" data-api-key="${selectedApiKey}"></script>`
    : `<script src="${serverUrl}/embed.js" data-position="${position}" data-type="${widgetType}" data-allow-toggle="${allowToggle}" data-server-url="${serverUrl}" data-api-key="YOUR_API_KEY_HERE"></script>`;

  const shareUrl = selectedSlug
    ? `${serverUrl}/c/${selectedSlug}?type=${widgetType}${allowToggle ? "" : "&allowToggle=false"}`
    : "";

  const handleCopyCode = () => {
    navigator.clipboard.writeText(embedCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopyLink = () => {
    if (!shareUrl) return;
    navigator.clipboard.writeText(shareUrl);
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 2000);
  };

  if (teamLoading) {
    return <div className="text-sm text-gray-500">Loading teams...</div>;
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-col gap-3 border-b border-[#E2E8F0] pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-[#0D1B2A]">Channels</h1>
          <p className="mt-1 text-sm text-[#66768D]">
            {selectedTeam ? `Team: ${selectedTeam.name}` : "Select a team to configure channels"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {CHANNELS.map((channel) => {
            const status = getChannelStatus(channel.id, channelConfigs, apiKeys);
            return (
              <span
                key={channel.id}
                className={`rounded-md border px-2.5 py-1 text-xs font-medium ${statusClasses(status.tone)}`}
              >
                {channel.label}: {status.label}
              </span>
            );
          })}
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-4">
        {STEPS.map((step, index) => (
          <div key={step} className="flex items-center gap-2 rounded-md border border-[#E2E8F0] bg-white px-3 py-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#2786C2] text-xs font-semibold text-white">
              {index + 1}
            </span>
            <span className="text-sm font-medium text-[#0D1B2A]">{step}</span>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <aside className="space-y-6">
          <section>
            <h2 className="mb-2 text-sm font-semibold text-[#0D1B2A]">1. Team</h2>
            <div className="space-y-2">
              {teams.map((team) => {
                const selected = selectedTeamId === team.id;
                return (
                  <button
                    key={team.id}
                    type="button"
                    onClick={() => setSelectedTeamId(team.id)}
                    className={`flex w-full items-center justify-between rounded-md border px-3 py-3 text-left transition ${
                      selected
                        ? "border-[#2786C2] bg-[#F8FBFF]"
                        : "border-[#E2E8F0] bg-white hover:border-[#CBD5E1]"
                    }`}
                  >
                    <span>
                      <span className="block text-sm font-semibold text-[#0D1B2A]">{team.name}</span>
                      {team.description && (
                        <span className="mt-0.5 block line-clamp-1 text-xs text-[#778DA9]">{team.description}</span>
                      )}
                    </span>
                    {selected && <CheckCircle2 className="h-4 w-4 text-[#2786C2]" />}
                  </button>
                );
              })}
            </div>
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold text-[#0D1B2A]">2. Channel Type</h2>
            <div className="space-y-2">
              {CHANNELS.map((channel) => {
                const selected = selectedChannel === channel.id;
                const status = getChannelStatus(channel.id, channelConfigs, apiKeys);
                return (
                  <button
                    key={channel.id}
                    type="button"
                    disabled={!selectedTeamId}
                    onClick={() => setSelectedChannel(channel.id)}
                    className={`flex w-full items-center justify-between rounded-md border px-3 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
                      selected
                        ? "border-[#2786C2] bg-[#F8FBFF]"
                        : "border-[#E2E8F0] bg-white hover:border-[#CBD5E1]"
                    }`}
                  >
                    <span className="flex items-center gap-3">
                      <span className="flex h-9 w-9 items-center justify-center rounded-md bg-[#EFF6FF] text-[#2786C2]">
                        {channel.icon}
                      </span>
                      <span>
                        <span className="block text-sm font-semibold text-[#0D1B2A]">{channel.name}</span>
                        <span className="block text-xs text-[#778DA9]">{status.label}</span>
                      </span>
                    </span>
                    {selected && <CheckCircle2 className="h-4 w-4 text-[#2786C2]" />}
                  </button>
                );
              })}
            </div>
          </section>
        </aside>

        <main className="space-y-6">
          {!selectedTeamId ? (
            <div className="rounded-md border border-dashed border-[#CBD5E1] bg-white p-8 text-center text-sm text-[#66768D]">
              Select a Team Agent to continue.
            </div>
          ) : (
            <>
            <section className="rounded-md border border-[#E2E8F0] bg-white">
              <div className="border-b border-[#E2E8F0] px-5 py-4">
                <h2 className="text-sm font-semibold text-[#0D1B2A]">3. Connect Channel</h2>
                <p className="mt-1 text-xs text-[#778DA9]">{selectedChannelMeta.name}</p>
              </div>

              {selectedChannel === "web-widget" ? (
                <div className="space-y-5 p-5">
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <label className="mb-2 block text-sm font-medium text-[#2D3F55]">Mode</label>
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => setWidgetType("voice")}
                          className={`flex items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-medium ${
                            widgetType === "voice"
                              ? "border-[#2786C2] bg-[#F8FBFF] text-[#0D1B2A]"
                              : "border-[#E2E8F0] text-[#526277]"
                          }`}
                        >
                          <MicIcon className="h-4 w-4" />
                          Voice
                        </button>
                        <button
                          type="button"
                          onClick={() => setWidgetType("chat")}
                          className={`flex items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-medium ${
                            widgetType === "chat"
                              ? "border-[#2786C2] bg-[#F8FBFF] text-[#0D1B2A]"
                              : "border-[#E2E8F0] text-[#526277]"
                          }`}
                        >
                          <WriteIcon width={16} height={16} />
                          Chat
                        </button>
                      </div>
                    </div>

                    <div>
                      <label className="mb-2 block text-sm font-medium text-[#2D3F55]">Position</label>
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => setPosition("bottom-right")}
                          className={`rounded-md border px-3 py-2 text-sm font-medium ${
                            position === "bottom-right"
                              ? "border-[#2786C2] bg-[#F8FBFF] text-[#0D1B2A]"
                              : "border-[#E2E8F0] text-[#526277]"
                          }`}
                        >
                          Bottom Right
                        </button>
                        <button
                          type="button"
                          onClick={() => setPosition("bottom-left")}
                          className={`rounded-md border px-3 py-2 text-sm font-medium ${
                            position === "bottom-left"
                              ? "border-[#2786C2] bg-[#F8FBFF] text-[#0D1B2A]"
                              : "border-[#E2E8F0] text-[#526277]"
                          }`}
                        >
                          Bottom Left
                        </button>
                      </div>
                    </div>
                  </div>

                  <label className="flex items-center justify-between rounded-md border border-[#E2E8F0] px-3 py-2">
                    <span className="text-sm font-medium text-[#2D3F55]">Allow voice/text toggle</span>
                    <input
                      type="checkbox"
                      checked={allowToggle}
                      onChange={(event) => setAllowToggle(event.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 text-[#2786C2] focus:ring-[#2786C2]"
                    />
                  </label>

                  <div className="border-t border-[#E2E8F0] pt-5">
                    <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#0D1B2A]">
                      <KeyRound className="h-4 w-4 text-[#2786C2]" />
                      API Key
                    </div>
                    <ApiKeyManager onApiKeySelect={setSelectedApiKey} onSlugSelect={setSelectedSlug} />
                  </div>
                </div>
              ) : (
                <div className="p-5">
                  <ChannelConfigForm channelType={selectedChannel as "line" | "facebook"} />
                </div>
              )}
            </section>

            {selectedChannel === "web-widget" && (
              <section className="rounded-md border border-[#E2E8F0] bg-white">
                <div className="border-b border-[#E2E8F0] px-5 py-4">
                  <h2 className="text-sm font-semibold text-[#0D1B2A]">4. Test and Go Live</h2>
                </div>

                <div className="grid gap-4 p-5 lg:grid-cols-2">
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-[#0D1B2A]">
                      <Code2 className="h-4 w-4 text-[#2786C2]" />
                      Install Code
                    </div>
                    <textarea
                      readOnly
                      value={embedCode}
                      className="h-40 w-full resize-y rounded-md border border-[#E2E8F0] bg-[#0F172A] p-3 font-mono text-xs leading-5 text-slate-100 outline-none"
                    />
                    <Button onClick={handleCopyCode} size="sm" variant={copied ? "primary" : "outline"} disabled={!selectedApiKey}>
                      {copied ? "Copied" : "Copy Code"}
                    </Button>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#0D1B2A]">
                        <Link2 className="h-4 w-4 text-[#2786C2]" />
                        Direct Link
                      </div>
                      <input
                        type="text"
                        readOnly
                        value={shareUrl}
                        placeholder="Select an active API key"
                        className="w-full rounded-md border border-[#E2E8F0] bg-[#F8FAFC] px-3 py-2 text-sm text-[#526277] outline-none"
                      />
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <Button onClick={handleCopyLink} size="sm" variant={linkCopied ? "primary" : "outline"} disabled={!shareUrl}>
                        {linkCopied ? "Copied" : "Copy Link"}
                      </Button>
                      <a
                        href={shareUrl || "#"}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={!shareUrl ? "pointer-events-none opacity-50" : ""}
                      >
                        <Button size="sm" variant="outline" disabled={!shareUrl}>
                          Open Link
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      </a>
                      <a
                        href={`/test_widget.html?type=${widgetType}&position=${position}&allowToggle=${allowToggle}&apiKey=${selectedApiKey}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={!selectedApiKey ? "pointer-events-none opacity-50" : ""}
                      >
                        <Button size="sm" disabled={!selectedApiKey}>
                          Test Widget
                        </Button>
                      </a>
                    </div>
                  </div>
                </div>
              </section>
            )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/Button";
import {
    type MessagingChannelType,
    type ChannelConfig,
    type UpdateChannelConfigRequest,
    getChannelConfigs,
    updateChannelConfig,
} from "@/lib/channelConfigs";
import { useTeam } from "@/lib/team-context";

interface FieldDef {
    key: string;
    label: string;
    type: "text" | "password";
    placeholder: string;
}

const LINE_FIELDS: FieldDef[] = [
    { key: "channel_id", label: "Channel ID", type: "text", placeholder: "LINE Channel ID" },
    { key: "channel_secret", label: "Channel Secret", type: "password", placeholder: "LINE Channel Secret" },
    { key: "channel_access_token", label: "Channel Access Token", type: "password", placeholder: "LINE Access Token (long-lived)" },
];

const FACEBOOK_FIELDS: FieldDef[] = [
    { key: "page_id", label: "Page ID", type: "text", placeholder: "Facebook Page ID" },
    { key: "app_id", label: "App ID", type: "text", placeholder: "Facebook App ID" },
    { key: "app_secret", label: "App Secret", type: "password", placeholder: "Facebook App Secret" },
    { key: "page_access_token", label: "Page Access Token", type: "password", placeholder: "Facebook Page Access Token" },
    { key: "verify_token", label: "Verify Token", type: "text", placeholder: "Custom webhook verify token" },
];

const FIELD_LABELS: Record<string, Record<string, string>> = {
    line: Object.fromEntries(LINE_FIELDS.map((f) => [f.key, f.label])),
    facebook: Object.fromEntries(FACEBOOK_FIELDS.map((f) => [f.key, f.label])),
};

const FIELD_PLACEHOLDERS: Record<string, Record<string, string>> = {
    line: Object.fromEntries(LINE_FIELDS.map((f) => [f.key, f.placeholder])),
    facebook: Object.fromEntries(FACEBOOK_FIELDS.map((f) => [f.key, f.placeholder])),
};

export default function ChannelConfigForm({ channelType }: { channelType: MessagingChannelType }) {
    const { selectedTeamId, selectedTeam } = useTeam();
    const [config, setConfig] = useState<ChannelConfig | null>(null);
    const [formValues, setFormValues] = useState<Record<string, string>>({});
    const [isActive, setIsActive] = useState(false);
    const [name, setName] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    const token = typeof window !== "undefined" ? localStorage.getItem("adminToken") || "" : "";
    const serverUrl = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";

    const loadConfig = useCallback(async () => {
        if (!token) return;
        try {
            setLoading(true);
            const configs = await getChannelConfigs(token, selectedTeamId);
            const cfg = configs.find((c) => c.type === channelType);
            if (cfg) {
                setConfig(cfg);
                setFormValues(cfg.config || {});
                setIsActive(cfg.is_active);
                setName(cfg.name);
            }
        } catch {
            // Config may not exist yet; defaults will be created on first fetch
        } finally {
            setLoading(false);
        }
    }, [channelType, token, selectedTeamId]);

    useEffect(() => {
        loadConfig();
    }, [loadConfig]);

    const handleSave = async () => {
        if (!token) return;
        setError(null);
        setSuccess(null);
        try {
            setSaving(true);
            const data: UpdateChannelConfigRequest = {
                name,
                config: formValues,
                is_active: isActive,
            };
            const updated = await updateChannelConfig(token, channelType, data, selectedTeamId);
            setConfig(updated);
            setSuccess(isActive ? "Channel settings saved and kept live." : "Draft saved successfully.");
            setTimeout(() => setSuccess(null), 3000);
        } catch (err: any) {
            setError(err.message || "Failed to save configuration.");
        } finally {
            setSaving(false);
        }
    };

    const webhookPath =
        formValues.webhook_url ||
        (channelType === "line"
            ? "/api/public/channels/line/webhook"
            : "/api/public/channels/facebook/webhook");

    const webhookUrl = `${serverUrl}${webhookPath}`;

    const fields = channelType === "line" ? LINE_FIELDS : FACEBOOK_FIELDS;
    const labels = FIELD_LABELS[channelType];
    const placeholders = FIELD_PLACEHOLDERS[channelType];

    if (loading) {
        return <p className="text-sm text-gray-500">Loading configuration...</p>;
    }

    return (
        <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                        {channelType === "line" ? "LINE Official Account" : "Facebook Messenger"}
                    </h3>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        Team: {selectedTeam?.name || "Selected team"}
                    </p>
                </div>
                <span
                    className={`inline-flex px-3 py-1 text-xs font-medium rounded-full ${
                        isActive
                            ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
                            : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
                    }`}
                >
                    {isActive ? "Live" : "Draft"}
                </span>
            </div>

            {error && (
                <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                    {error}
                </div>
            )}
            {success && (
                <div className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300">
                    {success}
                </div>
            )}

            <div className="grid gap-5 md:grid-cols-2">
                <div className="md:col-span-2">
                    <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Display Name
                    </label>
                    <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="w-full rounded-md border border-gray-200 bg-gray-50 p-2.5 text-sm text-gray-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                    />
                </div>

                {fields.map((field) => (
                    <div
                        key={field.key}
                        className={field.key === "page_access_token" || field.key === "channel_access_token" ? "md:col-span-2" : ""}
                    >
                        <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
                            {labels[field.key]}
                        </label>
                        <input
                            type={field.type}
                            value={formValues[field.key] || ""}
                            onChange={(e) =>
                                setFormValues((prev) => ({
                                    ...prev,
                                    [field.key]: e.target.value,
                                }))
                            }
                            placeholder={placeholders[field.key]}
                            className="w-full rounded-md border border-gray-200 bg-gray-50 p-2.5 text-sm font-mono text-gray-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
                        />
                    </div>
                ))}

                <div className="md:col-span-2">
                    <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Webhook URL
                    </label>
                    <div className="flex items-center gap-2">
                            <input
                                type="text"
                                readOnly
                                value={webhookUrl}
                            className="flex-1 rounded-md border border-gray-200 bg-gray-100 p-2.5 text-sm font-mono text-gray-600 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
                            />
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                    navigator.clipboard.writeText(webhookUrl);
                                }}
                                title="Copy webhook URL"
                            >
                                Copy
                            </Button>
                        </div>
                    </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 pt-4 dark:border-gray-700">
                <label className="flex items-center gap-3">
                    <button
                        type="button"
                        role="switch"
                        aria-checked={isActive}
                        onClick={() => setIsActive(!isActive)}
                        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ${
                            isActive ? "bg-blue-600" : "bg-gray-200 dark:bg-gray-700"
                        }`}
                    >
                        <span
                            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ${
                                isActive ? "translate-x-5" : "translate-x-0"
                            }`}
                        />
                    </button>
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Go live</span>
                </label>

                <div className="flex items-center gap-3">
                    {config && (
                        <span className="text-xs text-gray-400">
                            Updated {new Date(config.updated_at).toLocaleDateString()}
                        </span>
                    )}
                    <Button onClick={handleSave} disabled={saving} variant="primary">
                        {saving ? "Saving..." : isActive ? "Save and Keep Live" : "Save Draft"}
                    </Button>
                </div>
            </div>
        </div>
    );
}

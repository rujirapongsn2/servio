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
            const configs = await getChannelConfigs(token);
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
    }, [channelType, token]);

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
            const updated = await updateChannelConfig(token, channelType, data);
            setConfig(updated);
            setSuccess("Configuration saved successfully.");
            setTimeout(() => setSuccess(null), 3000);
        } catch (err: any) {
            setError(err.message || "Failed to save configuration.");
        } finally {
            setSaving(false);
        }
    };

    const webhookPath =
        channelType === "line"
            ? "/api/public/channels/line/webhook"
            : "/api/public/channels/facebook/webhook";

    const webhookUrl = `${serverUrl}${webhookPath}`;

    const fields = channelType === "line" ? LINE_FIELDS : FACEBOOK_FIELDS;
    const labels = FIELD_LABELS[channelType];
    const placeholders = FIELD_PLACEHOLDERS[channelType];

    if (loading) {
        return (
            <div className="bg-white dark:bg-gray-800 p-8 rounded-xl border border-gray-200 dark:border-gray-700">
                <p className="text-sm text-gray-500">Loading configuration...</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Status badge */}
            <div className="flex items-center gap-3">
                <span
                    className={`inline-flex px-3 py-1 text-xs font-medium rounded-full ${
                        isActive
                            ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
                            : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
                    }`}
                >
                    {isActive ? "Active" : "Inactive"}
                </span>
                {config && (
                    <span className="text-xs text-gray-400">
                        Last updated: {new Date(config.updated_at).toLocaleString()}
                    </span>
                )}
            </div>

            {/* Feedback messages */}
            {error && (
                <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
                    {error}
                </div>
            )}
            {success && (
                <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg text-sm text-green-700 dark:text-green-300">
                    {success}
                </div>
            )}

            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
                <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                        {channelType === "line" ? "LINE" : "Facebook"} Configuration
                    </h3>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Enter your {channelType === "line" ? "LINE Messaging API" : "Facebook Messenger Platform"} credentials.
                    </p>
                </div>

                <div className="p-6 space-y-5">
                    {/* Name field */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            Display Name
                        </label>
                        <input
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            className="w-full p-2.5 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:text-white"
                        />
                    </div>

                    {/* Credential fields */}
                    {fields.map((field) => (
                        <div key={field.key}>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
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
                                className="w-full p-2.5 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:text-white font-mono"
                            />
                        </div>
                    ))}

                    {/* Webhook URL (read-only) */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            Webhook URL
                        </label>
                        <div className="flex items-center gap-2">
                            <input
                                type="text"
                                readOnly
                                value={webhookUrl}
                                className="flex-1 p-2.5 text-sm bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-300 focus:outline-none font-mono"
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
                        <p className="mt-1 text-xs text-gray-400">
                            {channelType === "line"
                                ? "Set this as your LINE Bot's webhook URL in the LINE Developers Console."
                                : "Set this as your Callback URL in the Facebook App's Messenger settings."}
                        </p>
                    </div>

                    {/* Active toggle */}
                    <div className="flex items-center justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
                        <div>
                            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                                Enable Channel
                            </label>
                            <p className="text-xs text-gray-400 mt-0.5">
                                When enabled, incoming messages will be processed by your agents.
                            </p>
                        </div>
                        <button
                            type="button"
                            role="switch"
                            aria-checked={isActive}
                            onClick={() => setIsActive(!isActive)}
                            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ${
                                isActive
                                    ? "bg-blue-600"
                                    : "bg-gray-200 dark:bg-gray-700"
                            }`}
                        >
                            <span
                                className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ${
                                    isActive ? "translate-x-5" : "translate-x-0"
                                }`}
                            />
                        </button>
                    </div>
                </div>

                {/* Save button */}
                <div className="p-6 border-t border-gray-200 dark:border-gray-700">
                    <Button onClick={handleSave} disabled={saving} variant="primary">
                        {saving ? "Saving..." : "Save Configuration"}
                    </Button>
                </div>
            </div>

            {/* Webhook setup instructions */}
            <div className="bg-blue-50 dark:bg-blue-900/20 p-6 rounded-xl border border-blue-100 dark:border-blue-800">
                <h3 className="text-blue-800 dark:text-blue-300 font-semibold mb-2">
                    Setup Instructions
                </h3>
                {channelType === "line" ? (
                    <ol className="text-sm text-blue-600 dark:text-blue-400 space-y-1 list-decimal list-inside">
                        <li>Go to LINE Developers Console and select your channel</li>
                        <li>Under Messaging API settings, paste the webhook URL above</li>
                        <li>Copy Channel ID, Channel Secret, and create a Channel Access Token</li>
                        <li>Paste the credentials here and save</li>
                        <li>Enable the channel toggle to start receiving messages</li>
                    </ol>
                ) : (
                    <ol className="text-sm text-blue-600 dark:text-blue-400 space-y-1 list-decimal list-inside">
                        <li>Create a Facebook App with Messenger product on Meta for Developers</li>
                        <li>Generate a Page Access Token for your Facebook Page</li>
                        <li>Set the webhook URL above as the Callback URL in Messenger settings</li>
                        <li>Enter the same Verify Token you used during webhook setup</li>
                        <li>Subscribe your page to the webhook events (messages, messaging_postbacks)</li>
                        <li>Enable the channel toggle to start receiving messages</li>
                    </ol>
                )}
            </div>
        </div>
    );
}

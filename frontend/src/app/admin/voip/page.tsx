"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { getApiBaseUrl } from "@/lib/api";
import { Copy, Check, Eye, EyeOff, Save, Loader2 } from "lucide-react";

interface VoIPProvider {
    id: number;
    name: string;
    type: string;
    config: {
        account_sid: string;
        auth_token: string;
        phone_number: string;
        welcome_message?: string;
    } | null;
    is_active: boolean;
    updated_at: string;
}

export default function VoIPPage() {
    const apiBaseUrl = getApiBaseUrl();
    const [providers, setProviders] = useState<VoIPProvider[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [showToken, setShowToken] = useState(false);
    const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

    // For now we only handle the first provider (Twilio)
    const [selectedProvider, setSelectedProvider] = useState<VoIPProvider | null>(null);
    const [editConfig, setEditConfig] = useState({
        account_sid: "",
        auth_token: "",
        phone_number: "",
        welcome_message: "",
    });

    const [webhookUrl, setWebhookUrl] = useState("");

    useEffect(() => {
        fetchProviders();
        // Set webhook URL based on current window location
        if (typeof window !== "undefined") {
            setWebhookUrl(`${window.location.protocol}//${window.location.host}/incoming-call`);
        }
    }, [apiBaseUrl]);

    const fetchProviders = async () => {
        setIsLoading(true);
        setMessage(null);
        try {
            const token = localStorage.getItem("adminToken");
            const res = await fetch(`${apiBaseUrl}/api/admin/voip-providers`, {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });
            if (res.ok) {
                const data = await res.json();
                setProviders(data);
                if (data.length > 0) {
                    const twilio = data.find((p: any) => p.type === "twilio");
                    if (twilio) {
                        setSelectedProvider(twilio);
                        const config = twilio.config;
                        setEditConfig({
                            account_sid: config?.account_sid || "",
                            auth_token: config?.auth_token || "",
                            phone_number: config?.phone_number || "",
                            welcome_message: config?.welcome_message || "",
                        });
                    }
                }
            } else {
                const errorData = await res.json().catch(() => ({ detail: "Unknown server error" }));
                setMessage({ text: `Failed to load providers: ${errorData.detail || res.statusText}`, type: "error" });
            }
        } catch (error) {
            console.error("Failed to fetch providers:", error);
            setMessage({ text: "Network error: Could not reach the server", type: "error" });
        } finally {
            setIsLoading(false);
        }
    };

    const handleSave = async () => {

        if (!selectedProvider) return;

        setIsSaving(true);
        setMessage(null);

        try {
            const token = localStorage.getItem("adminToken");
            const res = await fetch(`${apiBaseUrl}/api/admin/voip-providers/${selectedProvider.id}`, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({
                    name: selectedProvider.name,
                    type: selectedProvider.type,
                    config: editConfig,
                    is_active: selectedProvider.is_active,
                }),
            });

            if (res.ok) {
                setMessage({ text: "Changes saved successfully", type: "success" });
                fetchProviders();
            } else {
                setMessage({ text: "Failed to save changes", type: "error" });
            }
        } catch (error) {
            setMessage({ text: "An error occurred", type: "error" });
        } finally {
            setIsSaving(false);
        }
    };

    const copyWebhook = () => {
        navigator.clipboard.writeText(webhookUrl);
        // Optional: show toast
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-[400px]">
                <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
            </div>
        );
    }

    return (
        <div className="max-w-4xl mx-auto space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                    VoIP Integration
                </h1>
                <p className="text-gray-500 dark:text-gray-400">
                    Manage your VoIP providers and telephony configuration.
                </p>
            </div>

            {/* Webhook Info Card */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
                <div className="flex flex-col space-y-4">
                    <div>
                        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                            Twilio Configuration
                        </h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                            Configure your Twilio number's "Voice & Fax" settings to use this Webhook URL.
                        </p>
                    </div>

                    <div className="flex items-end gap-4">
                        <div className="flex-1 space-y-2">
                            <Label>Webhook URL</Label>
                            <div className="flex items-center space-x-2">
                                <Input readOnly value={webhookUrl} className="font-mono text-sm bg-gray-50 dark:bg-gray-900" />
                                <Button variant="outline" size="iconSmall" onClick={copyWebhook} title="Copy URL">
                                    <Copy className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Provider Settings */}
            {selectedProvider ? (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
                    <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-6">
                        Account Credentials
                    </h3>

                    <div className="space-y-6">
                        <div className="space-y-2">
                            <Label htmlFor="sid">Account SID</Label>
                            <Input
                                id="sid"
                                value={editConfig.account_sid}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEditConfig({ ...editConfig, account_sid: e.target.value })}
                                placeholder="AC..."
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="token">Auth Token</Label>
                            <div className="relative">
                                <Input
                                    id="token"
                                    type={showToken ? "text" : "password"}
                                    value={editConfig.auth_token}
                                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEditConfig({ ...editConfig, auth_token: e.target.value })}
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowToken(!showToken)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                                >
                                    {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </button>
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="phone">Phone Number (Optional)</Label>
                            <Input
                                id="phone"
                                value={editConfig.phone_number}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEditConfig({ ...editConfig, phone_number: e.target.value })}
                                placeholder="+1234567890"
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="welcome">Welcome Message (Optional)</Label>
                            <Input
                                id="welcome"
                                value={editConfig.welcome_message}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEditConfig({ ...editConfig, welcome_message: e.target.value })}
                                placeholder="Hello! How can I help you today?"
                            />
                        </div>

                        {message && (
                            <div className={`p-3 rounded-md text-sm ${message.type === 'success' ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300'}`}>
                                {message.text}
                            </div>
                        )}

                        <div className="pt-4 flex justify-end">
                            <Button onClick={handleSave} disabled={isSaving}>
                                {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                <Save className="mr-2 h-4 w-4" />
                                Save Configuration
                            </Button>
                        </div>
                    </div>
                </div>
            ) : (
                <div className="text-center py-12 text-gray-500">
                    No providers found.
                </div>
            )}
        </div>
    );
}

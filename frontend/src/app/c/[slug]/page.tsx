"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import WidgetContent from "@/components/WidgetContent";
import { getApiBaseUrl } from "@/lib/api";

export default function ShortcutPage() {
    const params = useParams();
    const slug = typeof params.slug === "string" ? params.slug : "";
    const [config, setConfig] = useState<{ apiKey: string; voice_response_enabled: boolean } | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!slug) return;

        const fetchConfig = async () => {
            try {
                const apiUrl = getApiBaseUrl();
                const response = await fetch(`${apiUrl}/api/public/widget-config/${slug}`);

                if (!response.ok) {
                    if (response.status === 404) throw new Error("Shortcut not found");
                    if (response.status === 403) throw new Error("Shortcut is inactive");
                    throw new Error("Failed to load shortcut configuration");
                }

                const data = await response.json();
                setConfig(data);
            } catch (err: unknown) {
                setError(err instanceof Error ? err.message : "โหลดข้อมูลไม่สำเร็จ");
            } finally {
                setLoading(false);
            }
        };

        fetchConfig();
    }, [slug]);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-dvh min-h-0 bg-sky-50">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
            </div>
        );
    }

    if (error || !config) {
        return (
            <div className="flex flex-col items-center justify-center h-dvh min-h-0 bg-sky-50 text-slate-900 p-4">
                <h1 className="text-2xl font-bold mb-4 text-red-500">Error</h1>
                <p className="text-slate-400">{error || "Something went wrong"}</p>
            </div>
        );
    }

    return (
        <div className="w-full h-dvh min-h-0 overflow-hidden bg-sky-50">
            <WidgetContent variant="page" overrideApiKey={config.apiKey} />
        </div>
    );
}

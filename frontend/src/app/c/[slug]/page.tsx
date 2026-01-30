"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Widget from "@/app/widget/page";

export default function ShortcutPage() {
    const params = useParams();
    const slug = params.slug as string;
    const [config, setConfig] = useState<{ apiKey: string; voice_response_enabled: boolean } | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!slug) return;

        const fetchConfig = async () => {
            try {
                const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";
                const response = await fetch(`${apiUrl}/api/public/widget-config/${slug}`);

                if (!response.ok) {
                    if (response.status === 404) throw new Error("Shortcut not found");
                    if (response.status === 403) throw new Error("Shortcut is inactive");
                    throw new Error("Failed to load shortcut configuration");
                }

                const data = await response.json();
                setConfig(data);
            } catch (err: any) {
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        fetchConfig();
    }, [slug]);

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-slate-950">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
            </div>
        );
    }

    if (error || !config) {
        return (
            <div className="flex flex-col items-center justify-center min-h-screen bg-slate-950 text-white p-4">
                <h1 className="text-2xl font-bold mb-4 text-red-500">Error</h1>
                <p className="text-slate-400">{error || "Something went wrong"}</p>
            </div>
        );
    }

    // Render the widget in full-page mode
    // Note: Widget component expects URL params, but we can override them or 
    // we might need to adjust Widget component to accept props instead of just searchParams.
    // For now, we will use the existing Widget component and hope it handles missing params 
    // gracefully if we can't easily pass the apiKey.

    // Wait, the Widget component uses useSearchParams().
    // If we want to use the Widget component directly, we might need a wrapper or 
    // redirect to the widget page with the API key (which defeats the purpose of masking).

    // A better way: The Widget component in src/app/widget/page.tsx should be modified 
    // to optionally take config as props. Let's check it.

    return (
        <div className="w-full h-screen overflow-hidden bg-slate-950">
            <Widget overrideApiKey={config.apiKey} />
        </div>
    );
}

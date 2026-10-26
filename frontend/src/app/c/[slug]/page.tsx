"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Link2Off, Loader2, PauseCircle, RefreshCw, WifiOff } from "lucide-react";
import WidgetContent from "@/components/WidgetContent";
import styles from "@/components/ChatSurface.module.css";
import { getApiBaseUrl } from "@/lib/api";
import { chatThemeStyle, parseChatTheme, type ChatTheme } from "@/lib/chat-theme";

type ShortcutConfig = { apiKey: string; voice_response_enabled: boolean; theme: ChatTheme | null };
type LoadState =
    | { kind: "loading" }
    | { kind: "ready"; config: ShortcutConfig }
    | { kind: "error"; reason: "not_found" | "inactive" | "unavailable" };

const ERROR_COPY = {
    not_found: { icon: Link2Off, title: "ไม่พบหน้าแชตนี้", body: "ลิงก์อาจพิมพ์ผิดหรือถูกยกเลิกไปแล้ว กรุณาตรวจสอบลิงก์กับผู้ให้บริการอีกครั้ง" },
    inactive: { icon: PauseCircle, title: "แชตนี้ปิดให้บริการชั่วคราว", body: "ผู้ให้บริการปิดช่องทางนี้ไว้ กรุณาติดต่อผ่านช่องทางอื่นหรือกลับมาใหม่ภายหลัง" },
    unavailable: { icon: WifiOff, title: "เปิดหน้าแชตไม่สำเร็จ", body: "ระบบตอบกลับไม่ได้ในขณะนี้ ตรวจสอบอินเทอร์เน็ตแล้วลองอีกครั้ง" },
} as const;

export default function ShortcutPage() {
    const params = useParams();
    const slug = typeof params.slug === "string" ? params.slug : "";
    const [state, setState] = useState<LoadState>({ kind: "loading" });
    const [attempt, setAttempt] = useState(0);
    const retry = useCallback(() => { setState({ kind: "loading" }); setAttempt((value) => value + 1); }, []);

    useEffect(() => {
        if (!slug) { setState({ kind: "error", reason: "not_found" }); return; }
        const controller = new AbortController();
        (async () => {
            try {
                const response = await fetch(`${getApiBaseUrl()}/api/public/widget-config/${encodeURIComponent(slug)}`, { signal: controller.signal });
                if (response.status === 404) return setState({ kind: "error", reason: "not_found" });
                if (response.status === 403) return setState({ kind: "error", reason: "inactive" });
                if (!response.ok) return setState({ kind: "error", reason: "unavailable" });
                const data = await response.json();
                setState({ kind: "ready", config: { apiKey: data.apiKey, voice_response_enabled: data.voice_response_enabled !== false, theme: parseChatTheme(data.theme) } });
            } catch {
                if (!controller.signal.aborted) setState({ kind: "error", reason: "unavailable" });
            }
        })();
        return () => controller.abort();
    }, [slug, attempt]);

    if (state.kind === "ready") {
        return (
            <div className="w-full h-dvh min-h-0 overflow-hidden bg-[#eaf1fb]" data-color-scheme="light">
                <WidgetContent variant="page" overrideApiKey={state.config.apiKey} theme={state.config.theme} />
            </div>
        );
    }

    const copy = state.kind === "error" ? ERROR_COPY[state.reason] : null;
    const Icon = copy?.icon;
    return (
        <main className={`${styles.surface} ${styles.statusPage}`} style={chatThemeStyle(null)} data-color-scheme="light" lang="th" aria-busy={state.kind === "loading"}>
            <div className={styles.statusCard}>
                {state.kind === "loading" ? (
                    <div role="status" className={styles.statusBody}>
                        <Loader2 size={28} className={`${styles.statusIcon} animate-spin motion-reduce:animate-none`} aria-hidden="true" />
                        <p className={styles.statusText}>กำลังเปิดหน้าแชต…</p>
                    </div>
                ) : copy && Icon ? (
                    <div role="alert" className={styles.statusBody}>
                        <span className={styles.statusMark} aria-hidden="true"><Icon size={26} strokeWidth={1.8} /></span>
                        <h1>{copy.title}</h1>
                        <p className={styles.statusText}>{copy.body}</p>
                        {state.reason === "unavailable" && (
                            <button type="button" className={styles.statusButton} onClick={retry}>
                                <RefreshCw size={16} aria-hidden="true" /> ลองอีกครั้ง
                            </button>
                        )}
                    </div>
                ) : null}
            </div>
        </main>
    );
}

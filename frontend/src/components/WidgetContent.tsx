"use client";

import AudioChat from "@/components/AudioChat";
import { ChatHistory } from "@/components/ChatDialog";
import { Composer } from "@/components/Composer";
import { useAudio } from "@/hooks/useAudio";
import { useWebsocket } from "@/hooks/useWebsocket";
import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Headset, Loader2, MessageSquare, MessageSquarePlus, WifiOff, X } from "lucide-react";
import styles from "./ChatSurface.module.css";
import Image from "next/image";
import { VideoAttachmentComposer } from "@/components/VideoAttachmentComposer";
import { ImageSearchComposer } from "@/components/ImageSearchComposer";
import MicIcon from "@/components/icons/MicIcon";
import { useSearchParams } from "next/navigation";
import { chatThemeStyle, fetchPublicChatTheme, parseChatTheme, resolveGreeting, themeAssetUrl, type ChatLocale, type ChatTheme } from "@/lib/chat-theme";
import type { Message } from "@/lib/types";

interface WidgetContentProps {
    variant?: "page" | "widget";
    overrideApiKey?: string;
    overrideType?: string;
    overrideAllowToggle?: boolean;
    /** Theme already loaded by the caller (e.g. /c/[slug]); skips the widget's own fetch. */
    theme?: ChatTheme | null;
}

const PREVIEW_MESSAGE = "servio.theme.preview";
const PREVIEW_SAMPLE: Message[] = [
    { type: "message", role: "user", content: "ร้านเปิดกี่โมงคะ" },
    { type: "message", role: "assistant", content: "เปิดทุกวัน 09:00–18:00 น. ค่ะ ดู [แผนที่ร้าน](#) ได้เลย" },
] as Message[];

export default function WidgetContent({ variant = "widget", overrideApiKey, overrideType, overrideAllowToggle, theme: providedTheme }: WidgetContentProps) {
    const searchParams = useSearchParams();

    // Prioritize overrides, then searchParams, then defaults
    const explicitType = overrideType || searchParams.get("type");

    // For allowToggle: override -> searchParam -> default true
    // Explicit check for "false" string from URL
    const paramAllowToggle = searchParams.get("allowToggle");
    const allowToggle = overrideAllowToggle !== undefined
        ? overrideAllowToggle
        : (paramAllowToggle === "false" ? false : true);

    const apiKey = overrideApiKey || searchParams.get("apiKey") || searchParams.get("api_key") || "";
    const locale: ChatLocale = searchParams.get("lang") === "en" ? "en" : "th";
    // Admin live preview: rendered in a same-origin iframe, never opens a socket.
    const preview = variant === "widget" && searchParams.get("preview") === "1";

    // Initialize mode from localStorage or URL param
    const [currentMode, setCurrentMode] = useState<"voice" | "chat">(() => {
        if (explicitType === "chat" || explicitType === "voice") {
            return explicitType;
        }

        if (typeof window !== "undefined" && allowToggle) {
            const saved = localStorage.getItem("servio-widget-mode");
            return (saved === "voice" || saved === "chat") ? saved : "voice";
        }
        return "voice";
    });

    const [collapsed, setCollapsed] = useState(false);
    const [theme, setTheme] = useState<ChatTheme | null>(providedTheme ?? null);
    const needsThemeFetch = providedTheme === undefined && !preview && Boolean(apiKey);
    const [themeReady, setThemeReady] = useState(!needsThemeFetch);
    const [previewSample, setPreviewSample] = useState<"welcome" | "conversation">("welcome");

    useEffect(() => { if (providedTheme !== undefined) setTheme(providedTheme); }, [providedTheme]);

    useEffect(() => {
        if (!needsThemeFetch) return;
        const controller = new AbortController();
        // Never hold the chat hostage to a slow theme request.
        const reveal = window.setTimeout(() => setThemeReady(true), 1200);
        fetchPublicChatTheme(apiKey, controller.signal)
            .then((value) => setTheme(value))
            .catch(() => { /* keep the default theme */ })
            .finally(() => { window.clearTimeout(reveal); setThemeReady(true); });
        return () => { controller.abort(); window.clearTimeout(reveal); };
    }, [apiKey, needsThemeFetch]);

    useEffect(() => {
        if (!preview || window.parent === window) return;
        const handle = (event: MessageEvent) => {
            if (event.source !== window.parent || event.origin !== window.location.origin) return;
            const data = event.data as { type?: string; theme?: unknown; sample?: string; mode?: string } | null;
            if (!data || data.type !== PREVIEW_MESSAGE) return;
            setTheme(parseChatTheme(data.theme));
            setPreviewSample(data.sample === "conversation" ? "conversation" : "welcome");
            if (data.mode === "voice" || data.mode === "chat") setCurrentMode(data.mode);
        };
        window.addEventListener("message", handle);
        window.parent.postMessage({ type: `${PREVIEW_MESSAGE}.ready` }, window.location.origin);
        return () => window.removeEventListener("message", handle);
    }, [preview]);

    const {
        isReady: audioIsReady,
        playAudio,
        startRecording,
        stopRecording,
        frequencies,
    } = useAudio({ enabled: currentMode === "voice" && !preview });

    const {
        isReady: websocketReady,
        connection,
        reconnect,
        sendAudioMessage,
        sendTextMessage,
        history,
        resetHistory,
        presentations,
        a2uiSurfaces,
        sendDiscoveryAction,
        sendProductInquiry,
        sendKnowledgeInquiry,
        imageSearchAvailable,
        imageSearchState,
        imageComposerEpoch,
        sendImageSearch,
        videoUploadToken,
        sendVideoInquiry,
        productActionError,
        isLoading,
        agentName,
        voiceResponseEnabled,
    } = useWebsocket({
        apiKey: apiKey,
        onNewAudio: playAudio,
        enabled: !preview,
        inlineErrors: true,
    });

    const [videoBusy, setVideoBusy] = useState(false);
    const messages = preview && previewSample === "conversation" ? PREVIEW_SAMPLE : history;
    const chatReady = preview || websocketReady;

    // Determine if toggle should be shown
    // Hide toggle when voice response is disabled (admin setting)
    const showToggle = allowToggle && voiceResponseEnabled;

    const toggleCollapsed = () => setCollapsed((prev) => !prev);

    const toggleMode = () => {
        const newMode = currentMode === "voice" ? "chat" : "voice";
        setCurrentMode(newMode);
        if (typeof window !== "undefined") {
            localStorage.setItem("servio-widget-mode", newMode);
        }
    };

    const [framed, setFramed] = useState(false);
    useEffect(() => {
        const embedded = window.parent !== window;
        setFramed(embedded);
        if (variant !== "widget" || !embedded || preview) return;
        const handleKey = (event: KeyboardEvent) => {
            if (event.key === "Escape" && !event.defaultPrevented && !document.querySelector("dialog[open]")) {
                window.parent.postMessage({ type: "servio.widget.close" }, "*");
            }
        };
        window.addEventListener("keydown", handleKey);
        return () => window.removeEventListener("keydown", handleKey);
    }, [variant, preview]);

    // Only mention "connecting" if it takes long enough to notice.
    const [slowConnect, setSlowConnect] = useState(false);
    useEffect(() => {
        if (connection?.kind !== "connecting") { setSlowConnect(false); return; }
        const timer = window.setTimeout(() => setSlowConnect(true), 1500);
        return () => window.clearTimeout(timer);
    }, [connection?.kind]);

    const welcome = messages.length === 0 && !isLoading && !productActionError;
    const greeting = resolveGreeting(theme, locale);
    const logoUrl = themeAssetUrl(theme?.logo_url);
    const brandName = agentName || (locale === "en" ? "Customer assistant" : "ผู้ช่วยบริการลูกค้า");
    const connectionError = !preview && connection?.kind === "error" ? connection : null;

    return (
        <section className={styles.surface} style={chatThemeStyle(theme)} data-variant={variant} data-mode={currentMode} data-welcome={welcome}
            data-theme-ready={themeReady} data-color-scheme="light" lang={locale} aria-label="Servio chat" aria-busy={!themeReady}>
            <div className={styles.shell}>
                <header className={styles.header}>
                    <div className={styles.identity}>
                        {logoUrl
                            // eslint-disable-next-line @next/next/no-img-element -- customer logo comes from the API, sized by CSS
                            ? <img src={logoUrl} alt={brandName} className={styles.logo} />
                            : <Image src="/servio_logo.png" alt="Servio" width={104} height={60} className={styles.logo} priority />}
                        <span className={styles.agentName}>{brandName}</span>
                    </div>
                    <div className={styles.actions}>
                        {showToggle && <button onClick={toggleMode} title={currentMode === "voice" ? "เปลี่ยนเป็นแชต" : "เปลี่ยนเป็นเสียง"} aria-label={currentMode === "voice" ? "เปลี่ยนเป็นแชต" : "เปลี่ยนเป็นเสียง"}>
                            {currentMode === "voice" ? <MessageSquare size={16} aria-hidden="true" /> : <MicIcon className="w-4 h-4" />}
                            <span>{currentMode === "voice" ? "แชต" : "เสียง"}</span>
                        </button>}
                        {currentMode === "voice" && <button onClick={toggleCollapsed} title={collapsed ? "แสดงบทสนทนา" : "ซ่อนบทสนทนา"} aria-label={collapsed ? "แสดงบทสนทนา" : "ซ่อนบทสนทนา"} aria-expanded={!collapsed}>
                            {collapsed ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                        </button>}
                        <button onClick={resetHistory} title="เริ่มแชตใหม่" aria-label="เริ่มแชตใหม่"><MessageSquarePlus size={17} aria-hidden="true" /><span>แชตใหม่</span></button>
                        {variant === "widget" && framed && !preview && <button onClick={() => window.parent.postMessage({ type: "servio.widget.close" }, "*")} title="ปิดแชต" aria-label="ปิดแชต"><X size={19} /></button>}
                    </div>
                </header>
                <div className={styles.body}>
                    {welcome ? <div className={styles.welcome}>
                        {logoUrl
                            // eslint-disable-next-line @next/next/no-img-element -- customer logo comes from the API, sized by CSS
                            ? <img src={logoUrl} alt="" className={styles.welcomeLogo} />
                            : <div className={styles.welcomeMark} aria-hidden="true"><Headset size={28} strokeWidth={1.8} /></div>}
                        <h1>{greeting.title}</h1>
                        <p>{greeting.subtitle}</p>
                    </div> : <div className={styles.history}>
                        <ChatHistory locale={locale} messages={messages} isLoading={isLoading} collapsed={currentMode === "voice" && collapsed} presentations={presentations} a2uiSurfaces={a2uiSurfaces} onDiscoveryAction={sendDiscoveryAction} onProductInquiry={sendProductInquiry} onKnowledgeInquiry={sendKnowledgeInquiry} productActionsDisabled={!chatReady} productActionError={productActionError} showSystemEvents={false} />
                    </div>}
                    <div className={styles.composer}>
                        {connectionError ? (
                            <div className={styles.connection} role="alert" data-state="error">
                                <WifiOff size={18} aria-hidden="true" />
                                <div>
                                    <strong>{connectionError.reason === "auth" ? "แชตยังไม่พร้อมใช้งาน" : "ขาดการเชื่อมต่อ"}</strong>
                                    <span>{connectionError.message}</span>
                                </div>
                                {connectionError.reason === "network" && <button type="button" onClick={reconnect}>ลองอีกครั้ง</button>}
                            </div>
                        ) : slowConnect ? (
                            <div className={styles.connection} role="status" data-state="connecting">
                                <Loader2 size={18} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                                <div><span>กำลังเชื่อมต่อกับผู้ช่วย…</span></div>
                            </div>
                        ) : null}
                        <Composer audioChat={currentMode === "chat" ? (
                            <VideoAttachmentComposer key={`video-${imageComposerEpoch}`} token={videoUploadToken} disabled={!chatReady || isLoading || imageSearchState.kind === "pending"} locale={locale} onInquire={sendVideoInquiry} onBusyChange={setVideoBusy}
                              renderComposer={(attachmentActions) => <ImageSearchComposer key={imageComposerEpoch} available={imageSearchAvailable} disabled={!chatReady || isLoading || videoBusy} searchState={imageSearchState} onImageSearch={sendImageSearch} onTextMessage={sendTextMessage} attachmentActions={attachmentActions} />} />
                        ) : (
                            <AudioChat frequencies={frequencies} isReady={chatReady && (preview || audioIsReady)} startRecording={startRecording} stopRecording={stopRecording} sendAudioMessage={sendAudioMessage} />
                        )} />
                    </div>
                </div>
                <footer className={styles.footer}>Servio</footer>
            </div>
        </section>
    );
}

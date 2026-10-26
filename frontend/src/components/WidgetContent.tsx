"use client";

import AudioChat from "@/components/AudioChat";
import { ChatHistory } from "@/components/ChatDialog";
import { Composer } from "@/components/Composer";
import { useAudio } from "@/hooks/useAudio";
import { useWebsocket } from "@/hooks/useWebsocket";
import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import styles from "./ChatSurface.module.css";
import Image from "next/image";
import { ImageSearchComposer } from "@/components/ImageSearchComposer";
import WriteIcon from "@/components/icons/WriteIcon";
import MicIcon from "@/components/icons/MicIcon";
import { useSearchParams } from "next/navigation";

interface WidgetContentProps {
    variant?: "page" | "widget";
    overrideApiKey?: string;
    overrideType?: string;
    overrideAllowToggle?: boolean;
}

export default function WidgetContent({ variant = "widget", overrideApiKey, overrideType, overrideAllowToggle }: WidgetContentProps) {
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

    const {
        isReady: audioIsReady,
        playAudio,
        startRecording,
        stopRecording,
        frequencies,
    } = useAudio({ enabled: currentMode === "voice" });

    const {
        isReady: websocketReady,
        sendAudioMessage,
        sendTextMessage,
        history: messages,
        resetHistory,
        presentations,
        sendProductInquiry,
        sendKnowledgeInquiry,
        imageSearchAvailable,
        imageSearchState,
        imageComposerEpoch,
        sendImageSearch,
        productActionError,
        isLoading,
        agentName,
        voiceResponseEnabled,
    } = useWebsocket({
        apiKey: apiKey,
        onNewAudio: playAudio,
    });

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
        if (variant !== "widget" || !embedded) return;
        const handleKey = (event: KeyboardEvent) => {
            if (event.key === "Escape" && !event.defaultPrevented && !document.querySelector("dialog[open]")) {
                window.parent.postMessage({ type: "servio.widget.close" }, "*");
            }
        };
        window.addEventListener("keydown", handleKey);
        return () => window.removeEventListener("keydown", handleKey);
    }, [variant]);
    const welcome = messages.length === 0 && !isLoading && !productActionError;

    return (
        <section className={styles.surface} data-variant={variant} data-mode={currentMode} data-welcome={welcome} aria-label="Servio chat">
            <div className={styles.shell}>
                <header className={styles.header}>
                    <div className={styles.identity}>
                        <Image src="/servio_logo.png" alt="Servio" width={104} height={60} className={styles.logo} priority />
                        <span className={styles.agentName}>{agentName || "ผู้ช่วยบริการลูกค้า"}</span>
                    </div>
                    <div className={styles.actions}>
                        {showToggle && <button onClick={toggleMode} title={currentMode === "voice" ? "เปลี่ยนเป็นแชต" : "เปลี่ยนเป็นเสียง"} aria-label={currentMode === "voice" ? "เปลี่ยนเป็นแชต" : "เปลี่ยนเป็นเสียง"}>
                            {currentMode === "voice" ? <WriteIcon width={16} height={16} /> : <MicIcon className="w-4 h-4" />}
                            <span>{currentMode === "voice" ? "แชต" : "เสียง"}</span>
                        </button>}
                        {currentMode === "voice" && <button onClick={toggleCollapsed} title={collapsed ? "แสดงบทสนทนา" : "ซ่อนบทสนทนา"} aria-label={collapsed ? "แสดงบทสนทนา" : "ซ่อนบทสนทนา"} aria-expanded={!collapsed}>
                            {collapsed ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                        </button>}
                        <button onClick={resetHistory} title="เริ่มบทสนทนาใหม่" aria-label="เริ่มบทสนทนาใหม่"><WriteIcon width={18} height={18} /></button>
                        {variant === "widget" && framed && <button onClick={() => window.parent.postMessage({ type: "servio.widget.close" }, "*")} title="ปิดแชต" aria-label="ปิดแชต"><X size={19} /></button>}
                    </div>
                </header>
                <div className={styles.body}>
                    {welcome ? <div className={styles.welcome}>
                        <div className={styles.welcomeMark} aria-hidden="true"><WriteIcon width={26} height={26} /></div>
                        <h1>สวัสดีค่ะ ให้เราช่วยอะไรดีคะ</h1>
                        <p>สอบถามข้อมูลหรือบริการได้เลย</p>
                    </div> : <div className={styles.history}>
                        <ChatHistory messages={messages} isLoading={isLoading} collapsed={currentMode === "voice" && collapsed} presentations={presentations} onProductInquiry={sendProductInquiry} onKnowledgeInquiry={sendKnowledgeInquiry} productActionsDisabled={!websocketReady} productActionError={productActionError} />
                    </div>}
                    <div className={styles.composer}>
                        <Composer audioChat={currentMode === "chat" ? (
                            <ImageSearchComposer key={imageComposerEpoch} available={imageSearchAvailable} disabled={!websocketReady || isLoading} searchState={imageSearchState} onImageSearch={sendImageSearch} onTextMessage={sendTextMessage} />
                        ) : (
                            <AudioChat frequencies={frequencies} isReady={websocketReady && audioIsReady} startRecording={startRecording} stopRecording={stopRecording} sendAudioMessage={sendAudioMessage} />
                        )} />
                    </div>
                </div>
                <footer className={styles.footer}>Servio</footer>
            </div>
        </section>
    );
}

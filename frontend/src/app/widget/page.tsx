"use client";

import AudioChat from "@/components/AudioChat";
import { ChatHistory } from "@/components/ChatDialog";
import { Composer } from "@/components/Composer";
import { useAudio } from "@/hooks/useAudio";
import { useWebsocket } from "@/hooks/useWebsocket";
import { useState, Suspense } from "react";
import Image from "next/image";
import { Button } from "@/components/ui/Button";
import WriteIcon from "@/components/icons/WriteIcon";
import MicIcon from "@/components/icons/MicIcon";
import ArrowUpIcon from "@/components/icons/ArrowUpIcon";
import { useSearchParams } from "next/navigation";

import "../globals.css";

function WidgetContent() {
    const searchParams = useSearchParams();
    const initialType = searchParams.get("type") || "voice";
    const allowToggle = searchParams.get("allowToggle") !== "false"; // Default true
    const apiKey = searchParams.get("apiKey") || searchParams.get("api_key") || "";

    // Initialize mode from localStorage or URL param
    const [currentMode, setCurrentMode] = useState<"voice" | "chat">(() => {
        if (typeof window !== "undefined" && allowToggle) {
            const saved = localStorage.getItem("servio-widget-mode");
            return (saved === "voice" || saved === "chat") ? saved : initialType as "voice" | "chat";
        }
        return initialType as "voice" | "chat";
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
        isLoading,
        agentName,
    } = useWebsocket({
        apiKey: apiKey,
        onNewAudio: playAudio,
    });

    const toggleCollapsed = () => setCollapsed((prev) => !prev);

    const toggleMode = () => {
        const newMode = currentMode === "voice" ? "chat" : "voice";
        setCurrentMode(newMode);
        if (typeof window !== "undefined") {
            localStorage.setItem("servio-widget-mode", newMode);
        }
    };

    return (
        <div className="w-full h-screen flex flex-col bg-gray-50 dark:bg-gray-900 overflow-hidden">
            {/* Widget Header */}
            <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shrink-0">
                <div className="flex items-center gap-2">
                    <div className="bg-white rounded-lg p-1.5 shadow-sm">
                        <Image src="/servio_logo.png" alt="Logo" width={20} height={20} className="rounded" />
                    </div>
                    <span className="font-semibold text-sm truncate max-w-[150px]">
                        {agentName || (currentMode === "chat" ? "Chat Agent" : "Voice Agent")}
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    {allowToggle && (
                        <button
                            onClick={toggleMode}
                            className="text-white/90 hover:text-white hover:bg-white/10 px-2.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5"
                            title={currentMode === "voice" ? "Switch to Text Chat" : "Switch to Voice Chat"}
                        >
                            {currentMode === "voice" ? (
                                <>
                                    <WriteIcon width={14} height={14} />
                                    <span className="text-xs">Text</span>
                                </>
                            ) : (
                                <>
                                    <MicIcon className="w-3.5 h-3.5" />
                                    <span className="text-xs">Voice</span>
                                </>
                            )}
                        </button>
                    )}
                    {currentMode !== "chat" && (
                        <button
                            onClick={toggleCollapsed}
                            className="text-white/90 hover:text-white hover:bg-white/10 text-xs px-2.5 py-1.5 rounded-lg transition-all"
                            title={collapsed ? "Show conversation" : "Hide conversation"}
                        >
                            {collapsed ? "Show" : "Hide"}
                        </button>
                    )}
                    <button
                        onClick={resetHistory}
                        className="text-white/90 hover:text-white hover:bg-white/10 p-1.5 rounded-lg transition-all"
                        title="New Conversation"
                    >
                        <WriteIcon width={16} height={16} />
                    </button>
                </div>
            </div>

            {/* Chat Area */}
            <div className="flex-1 overflow-hidden relative flex flex-col bg-white dark:bg-gray-800">
                <ChatHistory messages={messages} isLoading={isLoading} collapsed={collapsed} />
            </div>

            {/* Controls Area */}
            <div className="shrink-0 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-3">
                <Composer
                    audioChat={
                        currentMode === "chat" ? (
                            <form
                                onSubmit={(e) => {
                                    e.preventDefault();
                                    const form = e.target as HTMLFormElement;
                                    const input = form.elements.namedItem("message") as HTMLInputElement;
                                    if (input.value.trim()) {
                                        sendTextMessage(input.value);
                                        input.value = "";
                                    }
                                }}
                                className="flex items-center gap-2 w-full"
                            >
                                <input
                                    name="message"
                                    type="text"
                                    placeholder="Type a message..."
                                    className="flex-1 p-3 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                                    autoComplete="off"
                                />
                                <Button type="submit" size="icon" className="rounded-full w-10 h-10 shrink-0 bg-blue-600 hover:bg-blue-700">
                                    <ArrowUpIcon className="w-5 h-5" />
                                </Button>
                            </form>
                        ) : (
                            <AudioChat
                                frequencies={frequencies}
                                isReady={websocketReady && audioIsReady}
                                startRecording={startRecording}
                                stopRecording={stopRecording}
                                sendAudioMessage={sendAudioMessage}
                            />
                        )
                    }
                />
            </div>
        </div>
    );
}

export default function WidgetPage() {
    return (
        <Suspense fallback={<div>Loading...</div>}>
            <WidgetContent />
        </Suspense>
    );
}

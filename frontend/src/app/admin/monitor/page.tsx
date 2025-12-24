"use client";

import { useEffect, useState, useRef } from "react";
import { Button } from "@/components/ui/Button";
import { getApiBaseUrl } from "@/lib/api";
import ReactMarkdown from "react-markdown";

function formatTimeAgo(timestamp: number) {
    const seconds = Math.floor((Date.now() - timestamp * 1000) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

function renderMessageContent(content: any): string {
    if (typeof content === 'string') {
        return content;
    }

    if (Array.isArray(content)) {
        // If it's an array, extract text from each item
        return content.map(item => {
            if (typeof item === 'string') return item;
            if (item && typeof item === 'object' && item.text) return item.text;
            return '';
        }).filter(Boolean).join('\n');
    }

    if (typeof content === 'object' && content !== null) {
        // If it's an object with a 'text' property, use that
        if (content.text) {
            return content.text;
        }
        // Otherwise, stringify it (fallback)
        return JSON.stringify(content);
    }

    return String(content);
}

interface Session {
    session_id: string;
    start_time: number;
    last_message_time: number;
    mode: "AI" | "MANUAL";
    last_message_preview: string;
    messages: any[];
}

export default function MonitorPage() {
    const [sessions, setSessions] = useState<Session[]>([]);
    const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
    const [messages, setMessages] = useState<any[]>([]);
    const [mode, setMode] = useState<"AI" | "MANUAL">("AI");
    const [inputMessage, setInputMessage] = useState("");
    const [isConnected, setIsConnected] = useState(false);
    const apiBaseUrl = getApiBaseUrl();
    const websocketBase = (process.env.NEXT_PUBLIC_WEBSOCKET_ENDPOINT
        ? process.env.NEXT_PUBLIC_WEBSOCKET_ENDPOINT.replace(/\/$/, "")
        : `${apiBaseUrl.replace(/^http/, "ws")}/ws`);

    const wsRef = useRef<WebSocket | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Poll for active sessions
    useEffect(() => {
        const fetchSessions = async () => {
            try {
                const token = localStorage.getItem("adminToken");
                const res = await fetch(`${apiBaseUrl}/api/admin/sessions`, {
                    headers: {
                        "Authorization": `Bearer ${token}`
                    }
                });
                if (res.ok) {
                    const data = await res.json();
                    setSessions(data);
                }
            } catch (error) {
                console.error("Failed to fetch sessions", error);
            }
        };

        fetchSessions();
        const interval = setInterval(fetchSessions, 5000);
        return () => clearInterval(interval);
    }, []);

    // Connect to WebSocket when a session is selected
    useEffect(() => {
        if (!selectedSessionId) return;

        // Close existing connection
        if (wsRef.current) {
            wsRef.current.close();
        }

        const token = localStorage.getItem("adminToken");
        const wsUrl = `${websocketBase}/admin/monitor?session_id=${selectedSessionId}&token=${token}`;
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            setIsConnected(true);
            console.log("Connected to monitor WS");
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "history") {
                setMessages(data.messages);
                // Also update mode if available in session list (or we should fetch it)
                const session = sessions.find(s => s.session_id === selectedSessionId);
                if (session) setMode(session.mode);
            } else if (data.type === "new_message") {
                setMessages(prev => [...prev, data.message]);
            } else if (data.type === "mode_update") {
                setMode(data.mode);
                // Update session list too
                setSessions(prev => prev.map(s => s.session_id === selectedSessionId ? { ...s, mode: data.mode } : s));
            }
        };

        ws.onclose = () => {
            setIsConnected(false);
        };

        wsRef.current = ws;

        return () => {
            ws.close();
        };
    }, [selectedSessionId]);

    // Scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const handleSendMessage = () => {
        if (!inputMessage.trim() || !wsRef.current || mode !== "MANUAL") return;

        wsRef.current.send(JSON.stringify({
            type: "admin_message",
            session_id: selectedSessionId,
            content: inputMessage
        }));
        setInputMessage("");
    };

    const toggleMode = () => {
        if (!wsRef.current) return;
        const newMode = mode === "AI" ? "MANUAL" : "AI";
        wsRef.current.send(JSON.stringify({
            type: "set_mode",
            session_id: selectedSessionId,
            mode: newMode
        }));
        // Optimistic update
        setMode(newMode);
    };

    return (
        <div className="h-[calc(100vh-6rem)] flex gap-6">
            {/* Session List */}
            <div className="w-1/3 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden flex flex-col">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                    <h2 className="font-semibold text-gray-900 dark:text-white">Active Sessions ({sessions.length})</h2>
                </div>
                <div className="flex-1 overflow-y-auto p-2 space-y-2">
                    {sessions.map(session => (
                        <button
                            key={session.session_id}
                            onClick={() => setSelectedSessionId(session.session_id)}
                            className={`w-full text-left p-3 rounded-lg border transition-all ${selectedSessionId === session.session_id
                                ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                                : "border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700"
                                }`}
                        >
                            <div className="flex justify-between items-start mb-1">
                                <span className="font-medium text-sm text-gray-900 dark:text-white truncate">
                                    {session.session_id.substring(0, 8)}...
                                </span>
                                <span className={`text-xs px-2 py-0.5 rounded-full ${session.mode === "MANUAL"
                                    ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300"
                                    : "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                                    }`}>
                                    {session.mode}
                                </span>
                            </div>
                            <p className="text-xs text-gray-500 dark:text-gray-400 truncate mb-1">
                                {session.last_message_preview || "No messages yet"}
                            </p>
                            <p className="text-[10px] text-gray-400">
                                Started {formatTimeAgo(session.start_time)}
                            </p>
                        </button>
                    ))}
                    {sessions.length === 0 && (
                        <div className="text-center py-8 text-gray-500 dark:text-gray-400 text-sm">
                            No active sessions
                        </div>
                    )}
                </div>
            </div>

            {/* Chat View */}
            <div className="flex-1 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden flex flex-col">
                {selectedSessionId ? (
                    <>
                        {/* Header */}
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-gray-900/50">
                            <div>
                                <h2 className="font-semibold text-gray-900 dark:text-white">
                                    Session: {selectedSessionId}
                                </h2>
                                <p className="text-xs text-gray-500">
                                    {isConnected ? "Connected" : "Connecting..."}
                                </p>
                            </div>
                            <div className="flex items-center gap-3">
                                <div className={`text-sm font-medium ${mode === "MANUAL" ? "text-yellow-600" : "text-green-600"}`}>
                                    Current: {mode} Mode
                                </div>
                                <Button
                                    variant={mode === "AI" ? "outline" : "primary"}
                                    onClick={toggleMode}
                                    className={mode === "AI" ? "border-yellow-500 text-yellow-600 hover:bg-yellow-50" : "bg-green-600 hover:bg-green-700"}
                                >
                                    {mode === "AI" ? "Switch to Manual Mode" : "Switch to AI Mode"}
                                </Button>
                            </div>
                        </div>

                        {/* Messages */}
                        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50/50 dark:bg-gray-900/50">
                            {messages.map((msg, idx) => (
                                <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                                    <div className={`max-w-[85%] p-3 rounded-lg ${msg.role === "user"
                                        ? "bg-blue-600 text-white rounded-br-none"
                                        : "bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-bl-none shadow-sm"
                                        }`}>
                                        <div className={`text-sm prose prose-sm max-w-none ${msg.role === "user" ? "prose-invert" : "dark:prose-invert"}`}>
                                            <ReactMarkdown>{renderMessageContent(msg.content)}</ReactMarkdown>
                                        </div>
                                        <span className={`text-[10px] mt-1 block ${msg.role === "user" ? "text-blue-100" : "text-gray-400"}`}>
                                            {msg.role === "user" ? "You" : msg.agent_name || "Assistant"} • {new Date(msg.timestamp * 1000).toLocaleTimeString()}
                                        </span>
                                    </div>
                                </div>
                            ))}
                            <div ref={messagesEndRef} />
                        </div>

                        {/* Input Area */}
                        <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
                            {mode === "MANUAL" ? (
                                <form
                                    onSubmit={(e) => {
                                        e.preventDefault();
                                        handleSendMessage();
                                    }}
                                    className="flex gap-2"
                                >
                                    <input
                                        type="text"
                                        value={inputMessage}
                                        onChange={(e) => setInputMessage(e.target.value)}
                                        placeholder="Type a message to the user..."
                                        className="flex-1 p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                    <Button type="submit" disabled={!inputMessage.trim()}>
                                        Send
                                    </Button>
                                </form>
                            ) : (
                                <div className="text-center text-sm text-gray-500 dark:text-gray-400 py-2 bg-gray-50 dark:bg-gray-900 rounded-lg border border-dashed border-gray-300 dark:border-gray-700">
                                    Switch to Manual Mode to send messages
                                </div>
                            )}
                        </div>
                    </>
                ) : (
                    <div className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-400">
                        Select a session to monitor
                    </div>
                )}
            </div>
        </div>
    );
}

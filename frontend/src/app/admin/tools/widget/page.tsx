"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import MicIcon from "@/components/icons/MicIcon";
import WriteIcon from "@/components/icons/WriteIcon";
import { ApiKeyManager } from "@/components/ApiKeyManager";

export default function WidgetGeneratorPage() {
    const [position, setPosition] = useState("bottom-right");
    const [widgetType, setWidgetType] = useState("voice"); // voice, chat
    const [allowToggle, setAllowToggle] = useState(true); // Allow mode switching
    const [copied, setCopied] = useState(false);
    const [selectedApiKey, setSelectedApiKey] = useState("");

    const serverUrl = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";

    const embedCode = selectedApiKey
        ? `<script src="${serverUrl}/embed.js" data-position="${position}" data-type="${widgetType}" data-allow-toggle="${allowToggle}" data-server-url="${serverUrl}" data-api-key="${selectedApiKey}"></script>`
        : `<!-- Please select or create an API key first -->
<script src="${serverUrl}/embed.js" data-position="${position}" data-type="${widgetType}" data-allow-toggle="${allowToggle}" data-server-url="${serverUrl}" data-api-key="YOUR_API_KEY_HERE"></script>`;

    const handleCopy = () => {
        navigator.clipboard.writeText(embedCode);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="max-w-6xl mx-auto space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                    Widget Generator
                </h1>
                <p className="mt-2 text-gray-600 dark:text-gray-400">
                    Create an embeddable chat widget for your website with secure API key authentication.
                </p>
            </div>

            {/* API Key Management - Full Width */}
            <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700">
                <ApiKeyManager onApiKeySelect={setSelectedApiKey} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Configuration */}
                <div className="space-y-6 bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                        Configuration
                    </h2>

                    <div className="space-y-6">
                        {/* Widget Type Selection */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Widget Type
                            </label>
                            <div className="grid grid-cols-2 gap-4">
                                <button
                                    onClick={() => setWidgetType("voice")}
                                    className={`p-4 rounded-lg border-2 text-center transition-all flex flex-col items-center gap-2 ${widgetType === "voice"
                                        ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300"
                                        : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
                                        }`}
                                >
                                    <div className={`p-3 rounded-full ${widgetType === "voice" ? "bg-blue-200 dark:bg-blue-800" : "bg-gray-100 dark:bg-gray-700"}`}>
                                        <MicIcon className="w-6 h-6" />
                                    </div>
                                    <span className="text-sm font-medium">Voice Agent</span>
                                </button>

                                <button
                                    onClick={() => setWidgetType("chat")}
                                    className={`p-4 rounded-lg border-2 text-center transition-all flex flex-col items-center gap-2 ${widgetType === "chat"
                                        ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300"
                                        : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
                                        }`}
                                >
                                    <div className={`p-3 rounded-full ${widgetType === "chat" ? "bg-blue-200 dark:bg-blue-800" : "bg-gray-100 dark:bg-gray-700"}`}>
                                        <WriteIcon width={24} height={24} />
                                    </div>
                                    <span className="text-sm font-medium">Chat Text Message</span>
                                </button>
                            </div>
                        </div>

                        {/* Position Selection */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Position
                            </label>
                            <div className="grid grid-cols-2 gap-4">
                                <button
                                    onClick={() => setPosition("bottom-right")}
                                    className={`p-4 rounded-lg border-2 text-center transition-all ${position === "bottom-right"
                                        ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300"
                                        : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
                                        }`}
                                >
                                    <div className="w-full h-20 bg-gray-100 dark:bg-gray-900 rounded mb-2 relative">
                                        <div className="absolute bottom-2 right-2 w-6 h-6 bg-blue-500 rounded-full"></div>
                                    </div>
                                    <span className="text-sm font-medium">Bottom Right</span>
                                </button>

                                <button
                                    onClick={() => setPosition("bottom-left")}
                                    className={`p-4 rounded-lg border-2 text-center transition-all ${position === "bottom-left"
                                        ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300"
                                        : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
                                        }`}
                                >
                                    <div className="w-full h-20 bg-gray-100 dark:bg-gray-900 rounded mb-2 relative">
                                        <div className="absolute bottom-2 left-2 w-6 h-6 bg-blue-500 rounded-full"></div>
                                    </div>
                                    <span className="text-sm font-medium">Bottom Left</span>
                                </button>
                            </div>
                        </div>

                        {/* Allow Toggle Option */}
                        <div>
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={allowToggle}
                                    onChange={(e) => setAllowToggle(e.target.checked)}
                                    className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600"
                                />
                                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                                    Allow users to switch between voice and text chat
                                </span>
                            </label>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 ml-6">
                                When enabled, users can toggle between voice and text modes within the widget.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Preview & Code */}
                <div className="space-y-6">
                    <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700">
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                            Generated Code
                        </h2>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                            Copy and paste this code into your website's HTML, just before the closing <code>&lt;/body&gt;</code> tag.
                        </p>

                        {!selectedApiKey && (
                            <div className="mb-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                                <p className="text-sm text-yellow-800 dark:text-yellow-300">
                                    ⚠️ Please select or create an API key above to get the complete embed code.
                                </p>
                            </div>
                        )}

                        <div className="relative">
                            <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg text-sm overflow-x-auto whitespace-pre-wrap break-all">
                                {embedCode}
                            </pre>
                            <Button
                                onClick={handleCopy}
                                size="sm"
                                className="absolute top-2 right-2"
                                variant={copied ? "primary" : "outline"}
                                disabled={!selectedApiKey}
                            >
                                {copied ? "Copied!" : "Copy Code"}
                            </Button>
                        </div>
                    </div>

                    <div className="bg-blue-50 dark:bg-blue-900/20 p-6 rounded-xl border border-blue-100 dark:border-blue-800">
                        <h3 className="text-blue-800 dark:text-blue-300 font-semibold mb-2">
                            Preview
                        </h3>
                        <p className="text-sm text-blue-600 dark:text-blue-400 mb-4">
                            The widget will appear in the {position.replace("-", " ")} corner of your website.
                        </p>
                        <a
                            href={`/test_widget.html?type=${widgetType}&position=${position}&allowToggle=${allowToggle}&apiKey=${selectedApiKey}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-block"
                        >
                            <Button variant="primary" size="sm">
                                Test Widget
                            </Button>
                        </a>
                    </div>
                </div>
            </div>
        </div>
    );
}

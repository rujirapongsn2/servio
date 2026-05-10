"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { getApiBaseUrl } from "@/lib/api";
import WorkflowNavigator from "@/components/WorkflowNavigator";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { normalizeMarkdownForChat } from "@/lib/markdown";

interface ToolCall {
  name?: string;
  arguments?: Record<string, unknown>;
}

interface ToolOutput {
  name?: string;
  output?: unknown;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  tool_calls?: ToolCall[];
  citations?: string[];
  tool_outputs?: ToolOutput[];
}

export default function AgentTestPage() {
  const FORCE_ARGS_PLACEHOLDER = 'Arguments (JSON or key=value, comma-separated). Example: {"symbol":"AAPL"} or symbol=AAPL';
  const params = useParams();
  const searchParams = useSearchParams();
  const apiBaseUrl = getApiBaseUrl();
  const agentId = parseInt((params && (params as any).id ? (params as any).id.toString() : "0"));
  const routeTeamId = searchParams.get("team_agent_id")
    ? parseInt(searchParams.get("team_agent_id") as string)
    : null;
  const returnTeamId = searchParams.get("return_team_id")
    ? parseInt(searchParams.get("return_team_id") as string)
    : null;
  const returnTeamName = searchParams.get("return_team_name");
  const teamManageHref = returnTeamId ? `/admin/teams?manage_team=${returnTeamId}` : "/admin/teams";
  const agentEditorHref = routeTeamId
    ? `/admin/agents/${agentId}?team_agent_id=${routeTeamId}&return_team_id=${returnTeamId ?? routeTeamId}&return_team_name=${encodeURIComponent(returnTeamName || "Manage Team")}`
    : `/admin/agents/${agentId}`;

  const [agentName, setAgentName] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [fetchingAgent, setFetchingAgent] = useState(true);
  const [forceEnabled, setForceEnabled] = useState(false);
  const [forceToolName, setForceToolName] = useState("");
  const [forceArgsText, setForceArgsText] = useState("");
  const [showToolOutputs, setShowToolOutputs] = useState(true);
  const [collapseToolOutputs, setCollapseToolOutputs] = useState(true);

  useEffect(() => {
    fetchAgent();
  }, []);

  const fetchAgent = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/agents/${agentId}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      const data = await response.json();
      setAgentName(data.name);
    } catch (error) {
      console.error("Failed to fetch agent:", error);
    } finally {
      setFetchingAgent(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage: ChatMessage = { role: "user", content: input };
    setMessages([...messages, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const token = localStorage.getItem("adminToken");
      // Build request body
      const bodyObj: any = { message: input };
      if (forceEnabled && forceToolName.trim()) {
        let args: any = {};
        const t = forceArgsText.trim();
        if (t) {
          try {
            const parsed = JSON.parse(t);
            if (parsed && typeof parsed === "object") args = parsed;
            else args = { query: String(parsed) };
          } catch (e) {
            // parse key=value pairs by comma/newline
            const parts = t
              .replace(/\n/g, ",")
              .split(",")
              .map((p) => p.trim())
              .filter(Boolean);
            for (const part of parts) {
              const idx = part.indexOf("=");
              if (idx > -1) {
                const k = part.slice(0, idx).trim();
                const v = part.slice(idx + 1).trim();
                if (k) args[k] = v;
              }
            }
            if (Object.keys(args).length === 0) args = { query: t };
          }
        }
        bodyObj.force_tool = { name: forceToolName.trim(), arguments: args };
      }

      const query = routeTeamId ? `?team_agent_id=${routeTeamId}` : "";
      const response = await fetch(
        `${apiBaseUrl}/api/admin/agents/${agentId}/test${query}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(bodyObj),
        }
      );

      if (!response.ok) throw new Error("Failed to get response");

      const data = await response.json();
      const assistantMessage: ChatMessage = {
        role: "assistant",
        content: data.response,
        tool_calls: data.tool_calls || [],
        citations: data.citations || [],
        tool_outputs: data.tool_outputs || [],
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Failed to send message:", error);
      const errorMessage: ChatMessage = {
        role: "assistant",
        content: "Error: Failed to get response from agent",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setMessages([]);
    setInput("");
  };

  if (fetchingAgent) {
    return (
      <div className="text-gray-600 dark:text-gray-400">Loading agent...</div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <WorkflowNavigator
        backLabel={returnTeamId ? "Team Manage" : "Team Agents"}
        backHref={teamManageHref}
        steps={[
          { label: "Team Agents", href: "/admin/teams" },
          ...(returnTeamId
            ? [{ label: returnTeamName || "Manage Team", href: teamManageHref }]
            : []),
          { label: "Test Agent", active: true },
        ]}
        actions={[
          { label: "Edit Agent", href: agentEditorHref, variant: "outline" },
          { label: "Agents", href: "/admin/agents", variant: "outline" },
        ]}
      />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Test Agent: {agentName}
          </h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Test your agent's responses and tool calls
          </p>
        </div>
        <div className="space-x-2">
          <button
            onClick={handleReset}
            className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Reset
          </button>
          <Link
            href={agentEditorHref}
            className="inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Edit Agent
          </Link>
        </div>
      </div>

      {/* Force Tool Controls */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center gap-3">
          <label className="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={forceEnabled}
              onChange={(e) => setForceEnabled(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-700"
            />
            Force tool for this test
          </label>
        </div>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label className="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={showToolOutputs}
              onChange={(e) => setShowToolOutputs(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-700"
            />
            Show tool outputs
          </label>
          <label className="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={collapseToolOutputs}
              onChange={(e) => setCollapseToolOutputs(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-700"
              disabled={!showToolOutputs}
            />
            Collapse tool outputs
          </label>
        </div>
        {forceEnabled && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
            <input
              type="text"
              placeholder="Tool name (e.g., mcp_alpha_vantage)"
              value={forceToolName}
              onChange={(e) => setForceToolName(e.target.value)}
              className="px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
            />
            <textarea
              placeholder={FORCE_ARGS_PLACEHOLDER}
              value={forceArgsText}
              onChange={(e) => setForceArgsText(e.target.value)}
              rows={1}
              className="sm:col-span-2 px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
            />
          </div>
        )}
      </div>

      {/* Chat Container */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-gray-200 dark:border-gray-700 flex flex-col h-[600px]">
        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 ? (
            <div className="text-center text-gray-500 dark:text-gray-400 mt-20">
              Send a message to start testing the agent
            </div>
          ) : (
            messages.map((message, index) => (
              <div
                key={index}
                className={`flex ${
                  message.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[70%] rounded-lg px-4 py-2 ${
                    message.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white"
                  }`}
                >
                  <div className="text-sm font-medium mb-1">
                    {message.role === "user" ? "You" : agentName}
                  </div>
                  <div className="text-sm markdown-content">
                    {message.role === "assistant" ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {normalizeMarkdownForChat(String(message.content || ""))}
                      </ReactMarkdown>
                    ) : (
                      <div className="whitespace-pre-wrap">{message.content}</div>
                    )}
                  </div>
                  {message.tool_calls && message.tool_calls.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-gray-300 dark:border-gray-600">
                      <div className="text-xs font-semibold mb-1">
                        Tool Calls:
                      </div>
                      {message.tool_calls.map((tc: ToolCall, i: number) => (
                        <div key={i} className="text-xs">
                          • {tc.name}
                        </div>
                      ))}
                    </div>
                  )}
                  {message.citations && message.citations.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-gray-300 dark:border-gray-600">
                      <div className="text-xs font-semibold mb-1">
                        Citations:
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {message.citations.map((c: string, i: number) => (
                          <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300 border border-purple-200 dark:border-purple-800">
                            {c}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {showToolOutputs && message.tool_outputs && message.tool_outputs.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-gray-300 dark:border-gray-600">
                      <div className="text-xs font-semibold mb-2">Tool Outputs:</div>
                      <div className="space-y-2">
                        {message.tool_outputs.map((to: ToolOutput, i: number) => {
                          const label = to?.name || `tool_${i+1}`;
                          const raw = to?.output;
                          let content = "";
                          let isJson = false;
                          try {
                            if (typeof raw === 'string') {
                              const trimmed = raw.trim();
                              if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
                                content = JSON.stringify(JSON.parse(trimmed), null, 2);
                                isJson = true;
                              } else {
                                content = raw;
                              }
                            } else {
                              content = JSON.stringify(raw, null, 2);
                              isJson = true;
                            }
                          } catch {
                            content = String(raw ?? '');
                          }
                          const box = (
                            <pre className="text-xs bg-gray-50 dark:bg-gray-900/30 border border-gray-200 dark:border-gray-700 rounded p-2 overflow-auto max-h-60 whitespace-pre-wrap">
                              {content}
                            </pre>
                          );
                          return (
                            <div key={i} className="text-xs">
                              {collapseToolOutputs ? (
                                <details>
                                  <summary className="cursor-pointer select-none font-medium">
                                    {label} {isJson ? <span className="opacity-60">(JSON)</span> : null}
                                  </summary>
                                  <div className="mt-1">{box}</div>
                                </details>
                              ) : (
                                <div>
                                  <div className="font-medium mb-1">{label} {isJson ? <span className="opacity-60">(JSON)</span> : null}</div>
                                  {box}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-gray-100 dark:bg-gray-700 rounded-lg px-4 py-2">
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  {agentName} is typing...
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="border-t border-gray-200 dark:border-gray-700 p-4">
          <div className="flex space-x-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && handleSend()}
              placeholder="Type your message..."
              className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              disabled={loading}
            />
            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";

interface Message {
  role: "user" | "assistant";
  content: string;
  tool_calls?: any[];
}

export default function AgentTestPage() {
  const router = useRouter();
  const params = useParams();
  const agentId = parseInt(params.id as string);

  const [agentName, setAgentName] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [fetchingAgent, setFetchingAgent] = useState(true);

  useEffect(() => {
    fetchAgent();
  }, []);

  const fetchAgent = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `http://localhost:8000/api/admin/agents/${agentId}`,
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

    const userMessage: Message = { role: "user", content: input };
    setMessages([...messages, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `http://localhost:8000/api/admin/agents/${agentId}/test`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ message: input }),
        }
      );

      if (!response.ok) throw new Error("Failed to get response");

      const data = await response.json();
      const assistantMessage: Message = {
        role: "assistant",
        content: data.response,
        tool_calls: data.tool_calls || [],
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Failed to send message:", error);
      const errorMessage: Message = {
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
            href={`/admin/agents/${agentId}`}
            className="inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Edit Agent
          </Link>
        </div>
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
                  <div className="text-sm whitespace-pre-wrap">
                    {message.content}
                  </div>
                  {message.tool_calls && message.tool_calls.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-gray-300 dark:border-gray-600">
                      <div className="text-xs font-semibold mb-1">
                        Tool Calls:
                      </div>
                      {message.tool_calls.map((tc, i) => (
                        <div key={i} className="text-xs">
                          • {tc.name}
                        </div>
                      ))}
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

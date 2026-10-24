"use client";
import { useEffect, useRef, useState } from "react";
import { getApiBaseUrl } from "@/lib/api";
import AgentTestContent from "@/components/AgentTestContent";
import { parseProductPresentations, type ProductPresentations } from "@/lib/product-presentations";
import WorkflowPanelDialog from "@/components/WorkflowPanelDialog";
interface TestMessage {
  role: "user" | "assistant";
  content: string;
  tool_calls?: unknown[];
  tool_outputs?: unknown[];
  citations?: unknown[];
  presentations?: ProductPresentations;
}
export function parseForcedToolArguments(text: string): Record<string, unknown> {
  const value = text.trim();
  if (!value)
    return {};
  try {
    const parsed: unknown = JSON.parse(value);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed))
      return parsed as Record<string, unknown>;
    return { query: String(parsed) };
  }
  catch {
    const entries = value.split(/[,\n]/).map(part => {
      const index = part.indexOf("=");
      return index > 0 ? [part.slice(0, index).trim(), part.slice(index + 1).trim()] : null;
    }).filter((entry): entry is string[] => entry !== null);
    return entries.length ? Object.fromEntries(entries) : { query: value };
  }
}
export default function WorkflowAgentTestPanel({ teamId, agent, hasUnsavedChanges, onClose }: {
  teamId: number;
  agent: {
    id: number;
    name: string;
  };
  hasUnsavedChanges: boolean;
  onClose: () => void;
}) {
  const [messages, setMessages] = useState<TestMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [force, setForce] = useState(false);
  const [tool, setTool] = useState("");
  const [args, setArgs] = useState("");
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const active = useRef(false);
  useEffect(() => {
    generation.current++;
    request.current?.abort();
    active.current = false;
    setLoading(false);
    setMessages([]);
    setInput("");
    setError("");
    setForce(false);
    setTool("");
    setArgs("");
    return () => {
      generation.current++;
      request.current?.abort();
      active.current = false;
    };
  }, [teamId, agent.id]);
  const reset = () => {
    generation.current++;
    request.current?.abort();
    active.current = false;
    setLoading(false);
    setMessages([]);
    setInput("");
    setError("");
  };
  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!input.trim() || active.current)
      return;
    if (force && !tool.trim()) {
      setError("Enter a tool name");
      return;
    }
    const message = input.trim();
    const version = generation.current;
    const controller = new AbortController();
    request.current = controller;
    active.current = true;
    setLoading(true);
    setError("");
    setInput("");
    setMessages(previous => [...previous, { role: "user", content: message }]);
    try {
      const response = await fetch(`${getApiBaseUrl()}/api/admin/agents/${agent.id}/test?team_agent_id=${teamId}`, { method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("adminToken")}` }, body: JSON.stringify({ message, ...(force ? { force_tool: { name: tool.trim(), arguments: parseForcedToolArguments(args) } } : {}) }) });
      const data: unknown = await response.json().catch(() => null);
      if (!response.ok)
        throw new Error(data && typeof data === "object" && "detail" in data && typeof data.detail === "string" ? data.detail : "Failed to test agent");
      if (!data || typeof data !== "object" || !("response" in data) || typeof data.response !== "string")
        throw new Error("Invalid agent test response");
      if (controller.signal.aborted || version !== generation.current)
        return;
      const content = data.response;
      setMessages(previous => [...previous, { role: "assistant", content, presentations: parseProductPresentations("presentations" in data ? data.presentations : null), tool_calls: "tool_calls" in data && Array.isArray(data.tool_calls) ? data.tool_calls : [], tool_outputs: "tool_outputs" in data && Array.isArray(data.tool_outputs) ? data.tool_outputs : [], citations: "citations" in data && Array.isArray(data.citations) ? data.citations : [] }]);
    }
    catch (failure) {
      if (!controller.signal.aborted && version === generation.current)
        setError(failure instanceof Error ? failure.message : "Failed to test agent");
    }
    finally {
      if (version === generation.current) {
        active.current = false;
        setLoading(false);
      }
    }
  };
  const json = (value: unknown) => typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return <WorkflowPanelDialog title={`Test Agent · ${agent.name}`} onClose={onClose}>
  <div className="space-y-4">
  <div className="flex items-center justify-between gap-3">
  <p role="status" className="text-sm text-gray-500">{hasUnsavedChanges ? "Testing saved settings. Unsaved changes are excluded." : "Testing saved settings"}</p>
  <button type="button" onClick={reset} className="rounded border px-3 py-1.5 text-sm">Reset</button>
  </div>
  <details className="rounded-lg border p-3 dark:border-gray-700">
  <summary className="cursor-pointer text-sm">Tool controls</summary>
  <label className="mt-3 flex gap-2 text-sm">
  <input type="checkbox" checked={force} onChange={event => setForce(event.target.checked)}/>Force tool</label>{force && <div className="mt-3 grid gap-3 sm:grid-cols-2">
    <label className="text-sm">Tool name<input aria-label="Tool name" value={tool} onChange={event => setTool(event.target.value)} className="mt-1 w-full rounded border p-2 dark:bg-gray-800"/>
    </label>
    <label className="text-sm">Arguments<textarea aria-label="Arguments" value={args} onChange={event => setArgs(event.target.value)} placeholder={'{"query":"example"} or query=example'} rows={3} className="mt-1 w-full rounded border p-2 dark:bg-gray-800"/>
    </label>
    </div>}</details>
  <div role="log" aria-label="Test messages" aria-live="polite" className="min-h-48 max-h-[55dvh] space-y-4 overflow-y-auto rounded-lg border p-3 dark:border-gray-700">{messages.length === 0 && <p className="py-12 text-center text-sm text-gray-500">Send a message to test this Agent</p>}{messages.map((message, index) => <article key={index} className={`min-w-0 rounded-lg p-3 ${message.role === "user" ? "bg-blue-50 dark:bg-blue-950" : "bg-gray-50 dark:bg-gray-800"}`}>
    <p className="mb-1 text-xs font-semibold">{message.role === "user" ? "You" : agent.name}</p>
    <AgentTestContent content={message.content} presentations={message.presentations} />{message.citations && message.citations.length > 0 && <details className="mt-2 text-sm">
      <summary>Citations ({message.citations.length})</summary>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs">{message.citations.map(json).join("\n")}</pre>
      </details>}{(["tool_calls", "tool_outputs"] as const).map(key => message[key] && message[key].length > 0 && <details key={key} className="mt-2 text-sm">
      <summary>{key === "tool_calls" ? "Tool calls" : "Tool outputs"} ({message[key].length})</summary>
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(message[key], null, 2)}</pre>
      </details>)}</article>)}{loading && <p role="status" className="text-sm text-gray-500">Waiting for response…</p>}</div>{error && <p role="alert" className="text-sm text-red-600">{error}</p>}<form onSubmit={send} className="flex items-end gap-2">
  <label className="min-w-0 flex-1 text-sm">Message<textarea aria-label="Test message" rows={2} value={input} disabled={loading} onChange={event => setInput(event.target.value)} className="mt-1 w-full rounded border p-2 dark:bg-gray-800"/>
  </label>
  <button type="submit" disabled={loading || !input.trim()} className="mb-1 rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">Send</button>
  </form>
  </div>
  </WorkflowPanelDialog>;
}

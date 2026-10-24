"use client";

import { Bot, GitBranch, Network, BookOpen, Wrench, Star } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, { Background, Controls, Handle, MarkerType, Position, type Node, type Edge, type NodeProps, type ReactFlowInstance, type Connection } from "reactflow";
import type { WorkflowAgent, WorkflowTool } from "@/lib/team-workflow";
import { isKnowledgeTool } from "@/lib/team-workflow";
import type { HandoffChange } from "@/lib/workflow-authoring";
import "reactflow/dist/style.css";

type AgentNodeData = { kind: "coordinator" } | {
  kind: "agent";
  agent: WorkflowAgent;
  isFallback: boolean;
  selected: boolean;
  tools: number;
  knowledge: number;
  onSelect: (id: number) => void;
  editable: boolean;
  targetConnectable: boolean;
  pending: boolean;
};

function AgentNode({ data }: NodeProps<AgentNodeData>) {
  if (data.kind === "coordinator") {
    return (
      <div className="w-60 rounded-2xl border border-orange-200 bg-orange-50 p-4 text-center shadow-sm">
        <div className="flex items-center justify-center gap-2 font-semibold text-orange-900"><Network className="h-5 w-5" />Coordinator</div>
        <div className="mt-1 text-xs text-orange-800">System router</div>
        <Handle type="source" position={Position.Bottom} isConnectable={false} className="!bg-orange-400" />
      </div>
    );
  }
  return (
    <div className="relative">
      <Handle id="routing" type="target" position={Position.Top} isConnectable={false} className="!bg-slate-400" />
      <Handle id="handoff-in-left" type="target" position={Position.Left} isConnectable={data.targetConnectable} style={{ top: "35%" }} title="Receive handoff" className="!h-3 !w-3 !bg-sky-500" />
      <Handle id="handoff-in-right" type="target" position={Position.Right} isConnectable={data.targetConnectable} style={{ top: "35%" }} title="Receive handoff" className="!h-3 !w-3 !bg-sky-500" />
      <button type="button" onClick={(event) => { event.stopPropagation(); data.onSelect(data.agent.id); }} aria-pressed={data.selected}
        aria-label={`Edit ${data.agent.name}`} className={`nodrag nowheel w-60 rounded-2xl border bg-white p-4 text-left shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-sky-500 ${data.selected ? "border-sky-500 ring-2 ring-sky-100" : "border-slate-200 hover:border-sky-400"}`}>
        <div className="flex items-start gap-2"><Bot className="mt-0.5 h-5 w-5 shrink-0 text-sky-600" /><span className="min-w-0 break-words font-semibold text-slate-900">{data.agent.name || "Untitled agent"}</span></div>
        <div className="mt-1 truncate pl-7 text-xs text-slate-500" title={data.agent.model}>{data.agent.model}</div>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-600">
          {data.isFallback && <span className="inline-flex items-center gap-1 text-amber-700"><Star className="h-3.5 w-3.5" />Fallback</span>}
          <span className="inline-flex items-center gap-1" title={`${data.tools} tools`}><Wrench className="h-3.5 w-3.5" />{data.tools}</span>
          <span className="inline-flex items-center gap-1" title={`${data.knowledge} knowledge sources`}><BookOpen className="h-3.5 w-3.5" />{data.knowledge}</span>
          {data.pending && <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-800">Unsaved</span>}
          {data.agent.shared && <span className="rounded bg-slate-100 px-1.5 py-0.5">Shared</span>}
        </div>
      </button>
      <Handle id="handoff-out-right" type="source" position={Position.Right} isConnectable={data.editable} style={{ top: "65%" }} title="Drag to add handoff" className="!h-3 !w-3 !bg-sky-500" />
      <Handle id="handoff-out-left" type="source" position={Position.Left} isConnectable={data.editable} style={{ top: "65%" }} title="Drag to add handoff" className="!h-3 !w-3 !bg-sky-500" />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };
const fitViewOptions = { padding: 0.2, maxZoom: 0.87 };

export default function AgentFlowGraph({ agents, tools, fallbackAgentId, selectedAgentId, onSelect, canEdit = false, disabled = false, pendingAgentIds = [], onHandoffChange }: {
  agents: WorkflowAgent[];
  tools: WorkflowTool[];
  fallbackAgentId: number | null;
  selectedAgentId: number | null;
  onSelect: (id: number) => void;
  canEdit?: boolean;
  disabled?: boolean;
  pendingAgentIds?: number[];
  onHandoffChange?: (change: HandoffChange) => void;
}) {
  const editable = canEdit && !disabled && onHandoffChange !== undefined;
  const container = useRef<HTMLDivElement>(null);
  const [instance, setInstance] = useState<ReactFlowInstance<AgentNodeData> | null>(null);
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<Set<string>>(new Set());
  const memberKey = agents.map((agent) => agent.id).join(",");
  useEffect(() => {
    if (!instance) return;
    const frame = requestAnimationFrame(() => { void instance.fitView(fitViewOptions); });
    return () => cancelAnimationFrame(frame);
  }, [instance, memberKey]);
  useEffect(() => {
    if (!instance || !container.current) return;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { void instance.fitView(fitViewOptions); });
    });
    observer.observe(container.current);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, [instance]);
  const { nodes, edges } = useMemo(() => {
    const columns = Math.min(3, agents.length);
    const nodes: Node<AgentNodeData>[] = [{ id: "coordinator", type: "agent", data: { kind: "coordinator" }, selectable: false, position: { x: Math.max(0, columns - 1) * 170, y: 0 } }];
    const edges: Edge[] = [];
    const memberIds = new Set(agents.map((agent) => agent.id));
    agents.forEach((agent, index) => {
      const assigned = tools.filter((tool) => agent.tool_ids.includes(tool.id));
      nodes.push({
        id: String(agent.id), type: "agent", selectable: false, position: { x: index % 3 * 340, y: 180 + Math.floor(index / 3) * 210 },
        data: { kind: "agent", agent, isFallback: agent.id === fallbackAgentId, selected: agent.id === selectedAgentId,
          tools: assigned.filter((tool) => !isKnowledgeTool(tool)).length,
          knowledge: assigned.filter(isKnowledgeTool).length, onSelect, editable: editable && !agent.shared, targetConnectable: editable, pending: pendingAgentIds.includes(agent.id) },
      });
      edges.push({ id: `routing-${agent.id}`, source: "coordinator", target: String(agent.id), targetHandle: "routing", type: "smoothstep", deletable: false, focusable: false, className: "!pointer-events-none",
        label: agent.id === fallbackAgentId ? "fallback" : undefined,
        style: { stroke: "#9aa3b0", strokeDasharray: "5 5" }, markerEnd: { type: MarkerType.ArrowClosed, color: "#9aa3b0" } });
      agent.handoff_agent_ids.filter((id) => memberIds.has(id)).forEach((id) => edges.push({
        id: `handoff-${agent.id}-${id}`, source: String(agent.id), target: String(id), sourceHandle: index % 3 <= agents.findIndex((target) => target.id === id) % 3 ? "handoff-out-right" : "handoff-out-left",
        targetHandle: index % 3 <= agents.findIndex((target) => target.id === id) % 3 ? "handoff-in-left" : "handoff-in-right",
        type: "default", className: editable && !agent.shared ? undefined : "!pointer-events-none", deletable: editable && !agent.shared, focusable: editable && !agent.shared, style: { stroke: "#4582b8", strokeWidth: 2 }, markerEnd: { type: MarkerType.ArrowClosed, color: "#4582b8" },
      }));
    });
    return { nodes, edges };
  }, [agents, tools, fallbackAgentId, selectedAgentId, onSelect, editable, pendingAgentIds]);

  const validConnection = (connection: Connection) => {
    const source = agents.find((agent) => String(agent.id) === connection.source);
    const target = agents.find((agent) => String(agent.id) === connection.target);
    return editable && !!source && !!target && source.id !== target.id && !source.shared &&
      !!connection.sourceHandle?.startsWith("handoff-out-") && !!connection.targetHandle?.startsWith("handoff-in-") &&
      !source.handoff_agent_ids.includes(target.id);
  };

  return (
    <div ref={container} className="relative h-[55vh] min-h-80 w-full overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 lg:h-full lg:min-h-0" aria-label="Team workflow diagram">
      <ReactFlow nodes={nodes} edges={edges.map((edge) => ({ ...edge, selected: editable && edge.deletable !== false && selectedEdgeIds.has(edge.id) }))} nodeTypes={nodeTypes} nodesDraggable={false} nodesConnectable={editable} onInit={setInstance}
        onEdgesChange={(changes) => setSelectedEdgeIds((previous) => {
          const next = new Set(previous);
          for (const change of changes) {
            if (change.type === "select") {
              if (change.selected) next.add(change.id);
              else next.delete(change.id);
            } else if (change.type === "remove") next.delete(change.id);
          }
          return next;
        })}
        isValidConnection={validConnection}
        onConnect={(connection) => {
          if (validConnection(connection)) onHandoffChange?.({ sourceId: Number(connection.source), targetId: Number(connection.target), connected: true });
        }}
        onEdgesDelete={(deleted) => {
          for (const edge of deleted) {
            const source = agents.find((agent) => String(agent.id) === edge.source);
            if (editable && source && !source.shared && edge.id.startsWith("handoff-")) onHandoffChange?.({ sourceId: source.id, targetId: Number(edge.target), connected: false });
          }
        }}
        deleteKeyCode={editable ? ["Backspace", "Delete"] : null}
        onNodeClick={(_, node) => { if (node.id !== "coordinator") onSelect(Number(node.id)); }}
        nodesFocusable={false} edgesFocusable={editable} elementsSelectable={editable} fitView fitViewOptions={fitViewOptions} minZoom={0.2} maxZoom={1.5}>
        <Background gap={24} color="#e2e5ea" />
        <Controls showInteractive={false} fitViewOptions={fitViewOptions} position="bottom-right" />
      </ReactFlow>
      <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap gap-3 rounded-lg bg-white/95 px-3 py-2 text-xs text-slate-600">
        <span className="inline-flex items-center gap-1"><Network className="h-3.5 w-3.5 text-slate-400" />Auto routing</span>
        <span className="inline-flex items-center gap-1"><GitBranch className="h-3.5 w-3.5 text-sky-600" />Handoff</span>
      </div>
    </div>
  );
}

"use client";

import { useMemo, useState, MouseEvent } from "react";
import {
  Bot,
  BrainCircuit,
  GitBranch,
  Network,
  Sparkles,
  UserRoundCog,
  Wrench,
  X,
} from "lucide-react";
import ReactFlow, {
  Background,
  Controls,
  Edge,
  MarkerType,
  Node,
  NodeProps,
  Position,
  ConnectionLineType,
  Handle,
} from "reactflow";
import "reactflow/dist/style.css";

type Agent = {
  id: number;
  name: string;
  instructions?: string;
  is_starting_agent?: boolean;
  tools?: { name: string }[];
  handoffs?: { id: number; name: string }[];
};

function truncate(text: string, max = 140) {
  if (!text) return "No description";
  const cleaned = text.replace(/\*+/g, "");
  return cleaned.length > max ? cleaned.slice(0, max - 1) + "..." : cleaned;
}

function AgentNode({ data, targetPosition = Position.Top, sourcePosition = Position.Bottom }: NodeProps) {
  const isCoordinator = data.variant === "coordinator";
  const Icon = isCoordinator ? Network : data.hasHandoffs ? GitBranch : data.hasTools ? UserRoundCog : Bot;

  return (
    <div className="relative flex w-[156px] flex-col items-center text-center">
      <Handle id="top-target" type="target" position={targetPosition} isConnectable={false} style={{ opacity: 0 }} />
      <Handle id="bottom-target" type="target" position={Position.Bottom} isConnectable={false} style={{ opacity: 0 }} />
      <Handle id="left-target" type="target" position={Position.Left} isConnectable={false} style={{ opacity: 0 }} />
      <Handle id="right-target" type="target" position={Position.Right} isConnectable={false} style={{ opacity: 0 }} />
      <div
        className={[
          "grid h-20 w-20 place-items-center rounded-full border-2 bg-white shadow-[0_18px_45px_-24px_rgba(15,23,42,0.8)]",
          isCoordinator
            ? "border-[#FB923C] text-[#EA580C] ring-4 ring-orange-100"
            : "border-[#38BDF8] text-[#0369A1] ring-4 ring-sky-100",
        ].join(" ")}
      >
        <Icon className="h-9 w-9" strokeWidth={1.9} />
      </div>
      <div className="mt-2 max-w-[156px] rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[13px] font-semibold leading-tight text-slate-900 shadow-sm">
        {data.label}
      </div>
      {data.badge ? (
        <div
          className={[
            "mt-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-normal",
            isCoordinator ? "bg-orange-50 text-orange-700" : "bg-slate-100 text-slate-600",
          ].join(" ")}
        >
          {data.hasTools ? <Wrench className="h-3 w-3" /> : null}
          {data.badge}
        </div>
      ) : null}
      <Handle id="bottom-source" type="source" position={sourcePosition} isConnectable={false} style={{ opacity: 0 }} />
      <Handle id="left-source" type="source" position={Position.Left} isConnectable={false} style={{ opacity: 0 }} />
      <Handle id="right-source" type="source" position={Position.Right} isConnectable={false} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes = { agentNode: AgentNode };

const edgeLabelStyle = {
  fill: "#475569",
  fontSize: 11,
  fontWeight: 600,
};

const edgeLabelBgStyle = {
  fill: "#ffffff",
  fillOpacity: 0.94,
};

export default function AgentFlowGraph({ agents }: { agents: Agent[] }) {
  const [selected, setSelected] = useState<Agent | null>(null);
  const { nodes, edges, yHeight } = useMemo(() => {
    const baseX = 0;
    const baseY = 0;
    const xSpacing = 380;
    const ySpacing = 200;

    const nodes: Node[] = [];
    const edges: Edge[] = [];
    const idMap = new Map<number, string>();
    const nodeX = new Map<number, number>();
    const handoffSourceIds = new Set<number>();
    const hasHandoffs = agents.some((agent) => (agent.handoffs || []).length > 0);
    const startingAgents = agents.filter((agent) => agent.is_starting_agent);
    const coordinatorTargets = hasHandoffs && startingAgents.length > 0 ? startingAgents : agents;

    const edgeDefaults = {
      type: "smoothstep",
      animated: false,
      labelStyle: edgeLabelStyle,
      labelBgStyle: edgeLabelBgStyle,
      labelBgPadding: [8, 4] as [number, number],
      labelBgBorderRadius: 10,
    };

    nodes.push({
      id: "coordinator",
      type: "agentNode",
      data: {
        label: "Coordinator",
        variant: "coordinator",
        badge: "router",
        hasHandoffs: true,
        hasTools: false,
      },
      position: { x: baseX, y: baseY },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    });

    agents.forEach((agent, idx) => {
      const maxColumns = 3;
      const col = idx % maxColumns;
      const row = Math.floor(idx / 3);
      const itemsInRow = Math.min(maxColumns, agents.length - row * maxColumns);
      const rowOffset = (itemsInRow - 1) / 2;
      const x = baseX + (col - rowOffset) * xSpacing;
      const y = baseY + ySpacing + row * ySpacing;
      const hasTools = Boolean(agent.tools && agent.tools.length > 0);
      const hasAgentHandoffs = Boolean(agent.handoffs && agent.handoffs.length > 0);

      idMap.set(agent.id, `agent-${agent.id}`);
      nodeX.set(agent.id, x);
      nodes.push({
        id: `agent-${agent.id}`,
        type: "agentNode",
        data: {
          label: agent.name,
          badge: hasTools ? `${agent.tools?.length || 0} tools` : agent.is_starting_agent ? "starting" : "agent",
          hasHandoffs: hasAgentHandoffs,
          hasTools,
        },
        position: { x, y },
        targetPosition: Position.Top,
        sourcePosition: Position.Bottom,
      });
    });

    coordinatorTargets.forEach((agent) => {
      const toolCount = agent.tools?.length || 0;
      edges.push({
        id: `edge-coordinator-${agent.id}`,
        source: "coordinator",
        target: `agent-${agent.id}`,
        sourceHandle: "bottom-source",
        targetHandle: "top-target",
        ...edgeDefaults,
        label: agent.is_starting_agent ? "starts here" : toolCount > 0 ? "uses tools" : "routes requests",
        style: { stroke: "#FB923C", strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#FB923C" },
      });
    });

    const handoffGroups = new Map<string, { from: number; to: number; bidirectional: boolean }>();
    agents.forEach((agent) => {
      if (!agent.handoffs) return;
      agent.handoffs.forEach((handoff) => {
        const targetId = idMap.get(handoff.id);
        if (!targetId) return;
        handoffSourceIds.add(agent.id);
        const key = [agent.id, handoff.id].sort((a, b) => a - b).join("-");
        const existing = handoffGroups.get(key);
        if (existing) {
          existing.bidirectional = true;
        } else {
          handoffGroups.set(key, { from: agent.id, to: handoff.id, bidirectional: false });
        }
      });
    });

    handoffGroups.forEach((handoff, key) => {
      const fromX = nodeX.get(handoff.from) ?? 0;
      const toX = nodeX.get(handoff.to) ?? 0;
      const sourceHandle = fromX <= toX ? "right-source" : "left-source";
      const targetHandle = fromX <= toX ? "left-target" : "right-target";
      edges.push({
        id: `edge-handoff-${key}`,
        source: `agent-${handoff.from}`,
        target: `agent-${handoff.to}`,
        sourceHandle,
        targetHandle,
        ...edgeDefaults,
        label: handoff.bidirectional ? "two-way handoff" : "handoff",
        type: "default",
        labelBgPadding: [4, 2],
        labelBgStyle: { fill: "#ffffff", fillOpacity: 0.82 },
        style: { stroke: "#0EA5E9", strokeWidth: 2.25 },
        interactionWidth: 18,
        markerEnd: { type: MarkerType.ArrowClosed, color: "#0EA5E9" },
        markerStart: handoff.bidirectional ? { type: MarkerType.ArrowClosed, color: "#0EA5E9" } : undefined,
      });
    });

    agents.forEach((agent) => {
      if (!hasHandoffs || !agent.tools || agent.tools.length === 0 || handoffSourceIds.has(agent.id)) return;
      edges.push({
        id: `edge-tools-${agent.id}`,
        source: "coordinator",
        target: `agent-${agent.id}`,
        sourceHandle: "bottom-source",
        targetHandle: "top-target",
        ...edgeDefaults,
        label: agent.tools.length === 1 ? "uses tool" : "uses tools",
        style: { stroke: "#22C55E", strokeWidth: 1.25, strokeDasharray: "5 5" },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#22C55E" },
      });
    });

    const yHeight = baseY + ySpacing + Math.max(0, Math.ceil(agents.length / 3)) * ySpacing;

    return { nodes, edges, yHeight };
  }, [agents]);

  const onNodeClick = (_: MouseEvent, node: Node) => {
    if (node.id === "coordinator") {
      setSelected({
        id: 0,
        name: "Coordinator",
        instructions: "Starts every conversation and routes requests to the available digital employee agents.",
        tools: [],
      });
      return;
    }
    const found = agents.find((agent) => `agent-${agent.id}` === node.id);
    if (found) setSelected(found);
  };

  return (
    <div
      className="relative w-full overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-950"
      style={{ height: Math.min(480, Math.max(340, yHeight + 20)) }}
    >
      <div className="pointer-events-none absolute left-4 top-4 z-10 flex items-center gap-2 rounded-full border border-slate-200 bg-white/95 px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm dark:border-slate-700 dark:bg-slate-900/95 dark:text-slate-300">
        <Sparkles className="h-3.5 w-3.5 text-orange-500" />
        Digital employee map
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        nodesDraggable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        panOnDrag={false}
        panOnScroll
        minZoom={0.4}
        maxZoom={1.2}
        onNodeClick={onNodeClick}
        onPaneClick={() => setSelected(null)}
        defaultEdgeOptions={{
          type: "smoothstep",
          animated: false,
          style: { stroke: "#94a3b8", strokeWidth: 1.25 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
        }}
        connectionLineType={ConnectionLineType.Bezier}
        className="!bg-transparent"
      >
        <Background gap={28} color="#e2e8f0" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
      {selected && (
        <div className="absolute right-4 top-4 z-20 max-w-md rounded-lg border border-slate-200 bg-white p-4 shadow-xl dark:border-slate-700 dark:bg-slate-800">
          <div className="mb-2 flex items-start justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
              <BrainCircuit className="h-4 w-4 text-sky-600" />
              <span>{selected.name}</span>
            </div>
            <button
              onClick={(event) => {
                event.stopPropagation();
                setSelected(null);
              }}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              type="button"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-1 text-xs text-slate-600 dark:text-slate-400">
            {truncate(selected.instructions || "", 200)}
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] font-medium text-slate-500 dark:text-slate-400">
            {selected.tools && selected.tools.length > 0 ? (
              selected.tools.map((tool) => (
                <span key={tool.name} className="rounded-full bg-slate-100 px-2 py-1 text-slate-600 dark:bg-slate-700 dark:text-slate-200">
                  {tool.name}
                </span>
              ))
            ) : (
              <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-600 dark:bg-slate-700 dark:text-slate-200">
                No tools
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

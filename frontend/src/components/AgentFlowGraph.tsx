"use client";

import { useMemo, useState, MouseEvent } from "react";
import ReactFlow, {
  Background,
  Controls,
  Edge,
  MarkerType,
  Node,
  NodeProps,
  Position,
  ConnectionLineType,
} from "reactflow";
import "reactflow/dist/style.css";

type Agent = {
  id: number;
  name: string;
  instructions?: string;
  tools?: { name: string }[];
  handoffs?: { id: number; name: string }[];
};

function truncate(text: string, max = 140) {
  if (!text) return "No description";
  const cleaned = text.replace(/\*+/g, "");
  return cleaned.length > max ? cleaned.slice(0, max - 1) + "…" : cleaned;
}

const pillStyle = {
  background: "#fff",
  border: "1px solid #e5e7eb",
  borderRadius: 16,
  boxShadow:
    "0 14px 32px rgba(15,23,42,0.12), 0 3px 10px rgba(15,23,42,0.08)",
  padding: "12px 14px",
  width: 240,
};

function AgentNode({ data }: NodeProps) {
  return (
    <div style={pillStyle}>
      <div className="text-center text-base font-semibold text-slate-900">
        {data.label}
      </div>
      {data.description ? (
        <div className="text-[11px] text-slate-500 mt-1 leading-relaxed">
          {data.description}
        </div>
      ) : null}
      {data.tools ? (
        <div className="text-[10px] text-slate-400 mt-1">Tools: {data.tools}</div>
      ) : null}
    </div>
  );
}

const nodeTypes = { agentNode: AgentNode };

export default function AgentFlowGraph({ agents }: { agents: Agent[] }) {
  const [selected, setSelected] = useState<Agent | null>(null);
  const { nodes, edges, yHeight } = useMemo(() => {
    const baseX = 0;
    const baseY = 0;
    const xSpacing = 260;
    const ySpacing = 180;

    const nodes: Node[] = [];
    const edges: Edge[] = [];

    // Coordinator node at top center
    nodes.push({
      id: "coordinator",
      type: "agentNode",
      data: { label: "Coordinator Agent", description: "จุดเริ่มทุกบทสนทนา" },
      position: { x: baseX, y: baseY },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Bottom,
    });

    // Place agents below in a grid (max 3 per row)
    agents.forEach((agent, idx) => {
      const col = idx % 3;
      const row = Math.floor(idx / 3);
      const x = baseX + (col - 1) * xSpacing;
      const y = baseY + ySpacing + row * ySpacing;

      const node: Node = {
        id: `agent-${agent.id}`,
        type: "agentNode",
        data: {
          label: agent.name,
          description: truncate(agent.instructions || "", 110),
          tools:
            agent.tools && agent.tools.length > 0
              ? agent.tools.map((t) => t.name).join(", ")
              : "No tools",
        },
        position: { x, y },
        targetPosition: Position.Top,
        sourcePosition: Position.Bottom,
      };

      nodes.push(node);

      // Edge from coordinator -> agent
      edges.push({
        id: `edge-coordinator-${agent.id}`,
        source: "coordinator",
        target: `agent-${agent.id}`,
        type: "smoothstep",
        animated: false,
        style: { stroke: "#0f172a", strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#0f172a" },
      });
    });

    // Edges for handoffs agent -> agent
    const idMap = new Map<number, string>();
    agents.forEach((a) => idMap.set(a.id, `agent-${a.id}`));
    agents.forEach((agent) => {
      if (!agent.handoffs) return;
      agent.handoffs.forEach((h) => {
        const targetId = idMap.get(h.id);
        if (!targetId) return;
        edges.push({
          id: `edge-${agent.id}-${h.id}`,
          source: `agent-${agent.id}`,
          target: targetId,
          type: "smoothstep",
          animated: false,
          style: { stroke: "#0f172a", strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#0f172a" },
        });
      });
    });

    const yHeight =
      baseY + ySpacing + Math.max(0, Math.ceil(agents.length / 3)) * ySpacing;

    return { nodes, edges, yHeight };
  }, [agents]);

  const onNodeClick = (_: MouseEvent, node: Node) => {
    if (node.id === "coordinator") {
      setSelected({
        id: 0,
        name: "Coordinator Agent",
        instructions: "จุดเริ่มทุกบทสนทนา โอนต่อ agent ที่มีในระบบ",
        tools: [],
      });
      return;
    }
    const found = agents.find((a) => `agent-${a.id}` === node.id);
    if (found) setSelected(found);
  };

  return (
    <div
      className="relative w-full bg-gradient-to-b from-slate-50 to-white dark:from-slate-900 dark:to-slate-950 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden"
      style={{ height: Math.max(520, yHeight + 180) }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        panOnDrag={false}
        panOnScroll={true}
        minZoom={0.6}
        maxZoom={1.2}
        onNodeClick={onNodeClick}
        defaultEdgeOptions={{
          type: "smoothstep",
          animated: false,
          style: { stroke: "#0f172a", strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#0f172a" },
        }}
        connectionLineType={ConnectionLineType.Bezier}
        className="!bg-transparent"
      >
        <Background gap={24} color="#cbd5e1" />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
      {selected && (
        <div className="absolute top-4 right-4 max-w-md bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-lg rounded-lg p-4">
          <div className="text-sm font-semibold text-slate-900 dark:text-white">
            {selected.name}
          </div>
          <div className="text-xs text-slate-600 dark:text-slate-400 mt-1">
            {truncate(selected.instructions || "", 200)}
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">
            Tools:{" "}
            {selected.tools && selected.tools.length > 0
              ? selected.tools.map((t) => t.name).join(", ")
              : "No tools"}
          </div>
        </div>
      )}
    </div>
  );
}

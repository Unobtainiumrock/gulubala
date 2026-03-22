export interface CallTreeData {
  tree_id: string;
  root_node_id: string;
  nodes: CallTreeNodeData[];
}

export interface CallTreeNodeData {
  id: string;
  label: string;
  input_type: string;
  intent?: string;
  transitions: CallTreeTransition[];
}

export interface CallTreeTransition {
  input: string;
  next_node_id: string;
  label?: string;
}

export interface TranscriptMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  turnCount: number;
  timestamp: string;
}

export interface Session {
  id: string;
  transcript: TranscriptMessage[];
  currentNodeId: string | null;
  visitedNodeIds: string[];
  escalated: boolean;
  escalationReason: string | null;
  resolved: boolean;
  completionSummary: string | null;
  bridgeActive: boolean;
  startedAt: number;
}

import { create } from "zustand";
import type { CallTreeData, Session, TranscriptMessage } from "@/types/events";

/* ── helpers ─────────────────────────────────────────────────────────── */

/** Matches `API_PROXY_TARGET` default in `next.config.ts` (Next rewrites cannot upgrade WebSockets). */
const DEFAULT_DEV_API_ORIGIN = "http://localhost:8000";

function resolveClientApiOrigin(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE?.trim();
  if (raw) return raw.replace(/\/$/, "");
  return DEFAULT_DEV_API_ORIGIN;
}

function getWsUrl(path: string): string {
  if (typeof window === "undefined") return "";
  try {
    const url = new URL(resolveClientApiOrigin());
    const proto = url.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${url.host}${path}`;
  } catch {
    return "";
  }
}

let reconnectDelay = 1000;
const MAX_RECONNECT = 30_000;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

/* ── store types ─────────────────────────────────────────────────────── */

interface DashboardState {
  connected: boolean;
  ws: WebSocket | null;
  sessions: Record<string, Session>;
  activeSessionId: string | null;
  callTree: CallTreeData | null;

  connect: () => void;
  disconnect: () => void;
  setActiveSession: (id: string | null) => void;
  loadCallTree: (treeId?: string) => Promise<void>;
}

/* ── session factory ─────────────────────────────────────────────────── */

function ensureSession(
  sessions: Record<string, Session>,
  sid: string,
): Record<string, Session> {
  if (sessions[sid]) return sessions;
  return {
    ...sessions,
    [sid]: {
      id: sid,
      transcript: [],
      currentNodeId: null,
      visitedNodeIds: [],
      escalated: false,
      escalationReason: null,
      resolved: false,
      completionSummary: null,
      bridgeActive: false,
      startedAt: Date.now(),
    },
  };
}

/* ── event processor ─────────────────────────────────────────────────── */

function processEvent(
  event: Record<string, unknown>,
  set: (partial: Partial<DashboardState>) => void,
  get: () => DashboardState,
) {
  const sid = event.session_id as string | undefined;
  if (!sid) return;

  let { sessions, activeSessionId } = get();
  sessions = ensureSession(sessions, sid);

  if (!activeSessionId) activeSessionId = sid;

  const session = sessions[sid];
  const etype = event.event_type as string;

  switch (etype) {
    case "transcript": {
      const msg: TranscriptMessage = {
        id: `${sid}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        role: (event.role as "user" | "assistant") ?? "user",
        content: (event.content as string) ?? "",
        turnCount: (event.turn_count as number) ?? 0,
        timestamp: (event.timestamp as string) ?? new Date().toISOString(),
      };
      sessions = {
        ...sessions,
        [sid]: { ...session, transcript: [...session.transcript, msg] },
      };
      break;
    }

    case "ivr_calltree_position": {
      const nodeId = event.node_id as string;
      if (!nodeId) break;
      const visited = session.visitedNodeIds.includes(nodeId)
        ? session.visitedNodeIds
        : [...session.visitedNodeIds, nodeId];
      sessions = {
        ...sessions,
        [sid]: { ...session, currentNodeId: nodeId, visitedNodeIds: visited },
      };
      break;
    }

    case "escalation": {
      sessions = {
        ...sessions,
        [sid]: {
          ...session,
          escalated: true,
          escalationReason: (event.reason as string) ?? "Unknown",
        },
      };
      break;
    }

    case "completed": {
      sessions = {
        ...sessions,
        [sid]: {
          ...session,
          resolved: true,
          completionSummary: (event.action_result as string) ?? "Completed",
        },
      };
      break;
    }

    case "bridge_active": {
      sessions = {
        ...sessions,
        [sid]: { ...session, bridgeActive: true },
      };
      break;
    }

    default:
      break;
  }

  set({ sessions, activeSessionId });
}

/* ── zustand store ───────────────────────────────────────────────────── */

export const useDashboardStore = create<DashboardState>((set, get) => ({
  connected: false,
  ws: null,
  sessions: {},
  activeSessionId: null,
  callTree: null,

  connect: () => {
    const existing = get().ws;
    if (existing && existing.readyState <= WebSocket.OPEN) return;

    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    const url = getWsUrl("/ws");
    if (!url) return;

    const ws = new WebSocket(url);

    ws.onopen = () => {
      reconnectDelay = 1000;
      set({ connected: true });
    };

    ws.onclose = () => {
      set({ connected: false, ws: null });
      reconnectTimer = setTimeout(() => get().connect(), reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT);
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (e) => {
      try {
        processEvent(JSON.parse(e.data), set, get);
      } catch {
        /* ignore malformed */
      }
    };

    set({ ws });
  },

  disconnect: () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    const ws = get().ws;
    if (ws) {
      ws.onclose = null;
      ws.close();
    }
    set({ ws: null, connected: false });
  },

  setActiveSession: (id) => set({ activeSessionId: id }),

  loadCallTree: async (treeId = "acme_corp") => {
    const directBase = resolveClientApiOrigin();
    const targets = [
      `/calltree/${treeId}`,
      `${directBase}/calltree/${treeId}`,
    ];
    for (const url of targets) {
      try {
        const res = await fetch(url);
        if (!res.ok) continue;
        set({ callTree: await res.json() });
        return;
      } catch {
        /* try next */
      }
    }
  },
}));

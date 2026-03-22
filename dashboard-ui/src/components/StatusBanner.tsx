"use client";

import { useDashboardStore } from "@/store/dashboard";

export default function StatusBanner() {
  const session = useDashboardStore((s) =>
    s.activeSessionId ? s.sessions[s.activeSessionId] : null,
  );

  if (!session) return null;

  if (session.resolved) {
    return (
      <div className="shrink-0 px-6 py-3.5 bg-emerald-950/70 border-t border-emerald-800/40 flex items-center gap-3 backdrop-blur-sm">
        <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.5)]" />
        <span className="text-sm font-medium text-emerald-300">
          Completed &mdash;{" "}
          {session.completionSummary || "Call resolved successfully"}
        </span>
      </div>
    );
  }

  if (session.escalated) {
    return (
      <div className="shrink-0 px-6 py-3.5 bg-rose-950/70 border-t border-rose-800/40 flex items-center gap-3 backdrop-blur-sm">
        <div className="w-2.5 h-2.5 rounded-full bg-rose-400 animate-pulse shadow-[0_0_10px_rgba(251,113,133,0.5)]" />
        <span className="text-sm font-medium text-rose-300">
          Escalated &mdash;{" "}
          {session.escalationReason || "Agent requested help"}
        </span>
      </div>
    );
  }

  if (session.bridgeActive) {
    return (
      <div className="shrink-0 px-6 py-3.5 bg-amber-950/70 border-t border-amber-800/40 flex items-center gap-3 backdrop-blur-sm">
        <div className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse shadow-[0_0_10px_rgba(251,191,36,0.5)]" />
        <span className="text-sm font-medium text-amber-300">
          Bridge Active &mdash; Presenter connected to conference
        </span>
      </div>
    );
  }

  return null;
}

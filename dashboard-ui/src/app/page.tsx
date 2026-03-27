"use client";

import { useEffect, useState } from "react";
import { useDashboardStore } from "@/store/dashboard";
import CallTreeGraph from "@/components/CallTreeGraph";
import TranscriptPanel from "@/components/TranscriptPanel";
import StatusBanner from "@/components/StatusBanner";

export default function Dashboard() {
  const connected = useDashboardStore((s) => s.connected);
  const activeSessionId = useDashboardStore((s) => s.activeSessionId);
  const session = useDashboardStore((s) =>
    s.activeSessionId ? s.sessions[s.activeSessionId] : null,
  );

  useEffect(() => {
    const { connect, loadCallTree, disconnect } = useDashboardStore.getState();
    connect();
    loadCallTree();
    return () => disconnect();
  }, []);

  /* ── session timer ─────────────────────────────────────── */
  const startedAt = session?.startedAt;
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!startedAt) {
      setElapsed(0);
      return;
    }
    setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    const tick = setInterval(
      () => setElapsed(Math.floor((Date.now() - startedAt) / 1000)),
      1000,
    );
    return () => clearInterval(tick);
  }, [startedAt]);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <main className="h-screen flex flex-col bg-zinc-950 text-zinc-100 overflow-hidden">
      {/* ── header ───────────────────────────────────────── */}
      <header className="h-14 flex items-center justify-between px-6 border-b border-zinc-800/80 bg-zinc-900/50 backdrop-blur-md shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-base font-semibold tracking-tight bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
            Gulubala
          </h1>
          <span className="hidden sm:inline text-[11px] text-zinc-600 font-mono">
            IVR Navigator
          </span>
        </div>

        {session && (
          <div className="flex items-center gap-3 text-sm">
            <span className="px-2.5 py-0.5 rounded-full bg-zinc-800/80 text-zinc-400 font-mono text-[11px] border border-zinc-700/50">
              {activeSessionId?.slice(0, 10)}
            </span>

            {session.currentNodeId && (
              <span className="px-2.5 py-0.5 rounded-full bg-blue-950/60 text-blue-400 text-[11px] font-medium border border-blue-800/40">
                {session.currentNodeId.replace(/_/g, " ")}
              </span>
            )}

            <span className="font-mono text-zinc-500 tabular-nums text-xs">
              {mm}:{ss}
            </span>
          </div>
        )}

        <div className="flex items-center gap-2">
          <div
            className={`w-2 h-2 rounded-full transition-colors duration-500 ${
              connected
                ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]"
                : "bg-zinc-600"
            }`}
          />
          <span className="text-[11px] text-zinc-500">
            {connected ? "Live" : "Reconnecting\u2026"}
          </span>
        </div>
      </header>

      {/* ── main content ─────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">
        {/* left: call tree */}
        <section className="w-[55%] border-r border-zinc-800/50 flex flex-col">
          <div className="px-5 py-3 border-b border-zinc-800/30 shrink-0 flex items-center justify-between">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
              Call Tree
            </h2>
            {session && (
              <span className="text-[10px] text-zinc-600">
                {session.visitedNodeIds.length} node
                {session.visitedNodeIds.length !== 1 ? "s" : ""} visited
              </span>
            )}
          </div>
          <div className="flex-1 relative">
            <CallTreeGraph />
          </div>
        </section>

        {/* right: transcript */}
        <section className="w-[45%] flex flex-col">
          <div className="px-5 py-3 border-b border-zinc-800/30 shrink-0 flex items-center justify-between">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.15em] text-zinc-500">
              Live Transcript
            </h2>
            {session && (
              <span className="text-[10px] text-zinc-600">
                {session.transcript.length} message
                {session.transcript.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
          <div className="flex-1 overflow-hidden">
            <TranscriptPanel />
          </div>
        </section>
      </div>

      {/* ── status banner ────────────────────────────────── */}
      <StatusBanner />
    </main>
  );
}

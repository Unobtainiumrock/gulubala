"use client";

import { useEffect, useRef } from "react";
import { useDashboardStore } from "@/store/dashboard";

export default function TranscriptPanel() {
  const session = useDashboardStore((s) =>
    s.activeSessionId ? s.sessions[s.activeSessionId] : null,
  );
  const messages = session?.transcript ?? [];
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  /* ── empty states ──────────────────────────────────── */

  if (!session) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-600">
        <div className="flex gap-1.5">
          <span className="w-2 h-2 rounded-full bg-zinc-700 animate-bounce [animation-delay:0ms]" />
          <span className="w-2 h-2 rounded-full bg-zinc-700 animate-bounce [animation-delay:150ms]" />
          <span className="w-2 h-2 rounded-full bg-zinc-700 animate-bounce [animation-delay:300ms]" />
        </div>
        <p className="text-sm">Waiting for a session&hellip;</p>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-600">
        <div className="w-3 h-3 rounded-full bg-blue-500/50 animate-pulse" />
        <p className="text-sm">Session connected. Listening&hellip;</p>
      </div>
    );
  }

  /* ── message list ──────────────────────────────────── */

  return (
    <div className="flex flex-col gap-3 p-4 overflow-y-auto h-full scrollbar-thin">
      {messages.map((msg) => {
        const isIvr = msg.role === "user";
        return (
          <div
            key={msg.id}
            className={`flex flex-col max-w-[85%] animate-fade-in-up ${
              isIvr ? "self-start" : "self-end"
            }`}
          >
            <div
              className={[
                "rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed",
                isIvr
                  ? "bg-zinc-800/80 text-zinc-200 rounded-bl-md border border-zinc-700/30"
                  : "bg-blue-600/80 text-white rounded-br-md border border-blue-500/20",
              ].join(" ")}
            >
              {msg.content}
            </div>
            <span
              className={`text-[10px] mt-1 px-1 text-zinc-600 ${
                isIvr ? "text-left" : "text-right"
              }`}
            >
              {isIvr ? "IVR" : "Agent"} &middot; Turn {msg.turnCount}
            </span>
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}

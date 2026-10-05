import React from "react";
import Panel from "./Panel.jsx";

const LEVEL_COLOR = {
  INFO: "text-accent",
  WARN: "text-warn",
  ERROR: "text-bear",
};

export default function ExecutionLog({ logs }) {
  return (
    <Panel
      title="System Execution Log · Live"
      badge={<span className="h-1.5 w-1.5 rounded-full bg-bull" />}
    >
      <div className="h-64 space-y-1.5 overflow-y-auto font-mono text-[11px] leading-relaxed">
        {logs.map((log) => (
          <div key={log.id} className="flex gap-2">
            <span className="shrink-0 text-ink-faint">{log.time}</span>
            <span className={`shrink-0 ${LEVEL_COLOR[log.level] ?? "text-ink-dim"}`}>[{log.level}]</span>
            <span className="text-ink-dim">{log.message}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
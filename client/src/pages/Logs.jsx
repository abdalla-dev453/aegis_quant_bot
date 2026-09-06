import { useMemo, useState } from "react";
import Panel from "../components/Panel.jsx";
import TopBar from "../components/TopBar.jsx";
import { useBotFeed } from "../lib/useBotFeed.js";

export default function Logs() {
  const { logs, connected } = useBotFeed();
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState("ALL");
  const filtered = useMemo(
    () =>
      logs.filter((log) => {
        const matchesText = `${log.time} ${log.message}`
          .toLowerCase()
          .includes(query.toLowerCase());
        return matchesText && (level === "ALL" || log.level === level);
      }),
    [logs, query, level],
  );

  return (
    <div className="flex min-h-full flex-col">
      <TopBar
        title="Execution Logs"
        subtitle={`${connected ? "Live server stream" : "Server unavailable"} · ${filtered.length} records`}
      />
      <div className="flex-1 overflow-y-auto px-8 py-5">
        <Panel title="Bot activity">
          <div className="mb-4 flex flex-col gap-2 sm:flex-row">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search messages"
              className="flex-1 rounded-md border border-border bg-surface-alt px-3 py-2 text-[12px] text-ink outline-none focus:border-accent"
            />
            <select
              value={level}
              onChange={(event) => setLevel(event.target.value)}
              className="rounded-md border border-border bg-surface-alt px-3 py-2 text-[12px] text-ink outline-none focus:border-accent"
            >
              <option>ALL</option>
              <option>INFO</option>
              <option>WARN</option>
              <option>ERROR</option>
            </select>
          </div>
          <div className="divide-y divide-border">
            {filtered.length === 0 ? (
              <div className="py-8 text-center text-[12px] text-ink-faint">
                No matching log entries.
              </div>
            ) : (
              filtered
                .slice()
                .reverse()
                .map((log) => <LogRow key={log.id} log={log} />)
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function LogRow({ log }) {
  const color =
    log.level === "ERROR"
      ? "text-bear"
      : log.level === "WARN"
        ? "text-warn"
        : "text-ink-dim";
  return (
    <div className="grid grid-cols-[70px_58px_1fr] gap-3 py-2 font-mono text-[11px]">
      <span className="text-ink-faint">{log.time}</span>
      <span className={color}>{log.level}</span>
      <span className="wrap-break-word text-ink-dim">{log.message}</span>
    </div>
  );
}

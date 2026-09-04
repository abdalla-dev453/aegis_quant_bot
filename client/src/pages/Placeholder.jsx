import React from "react";
import TopBar from "../components/TopBar.jsx";

export default function Placeholder({ title, note }) {
  return (
    <div className="flex h-full flex-1 flex-col overflow-hidden">
      <TopBar title={title} subtitle="Not yet wired up" />
      <div className="flex flex-1 items-center justify-center">
        <div className="rounded-lg border border-dashed border-border px-8 py-6 text-center">
          <div className="text-[13px] text-ink-dim">{note}</div>
        </div>
      </div>
    </div>
  );
}
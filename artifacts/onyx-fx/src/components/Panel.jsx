import React from "react";

export default function Panel({ title, badge, children, className = "" }) {
  return (
    <div className={`rounded-lg border border-border bg-surface shadow-panel ${className}`}>
      {title && (
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="text-[10px] font-medium uppercase tracking-wider text-ink-faint">
            {title}
          </span>
          {badge}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
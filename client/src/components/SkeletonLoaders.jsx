export function Skeleton({ className = "", style }) {
  return (
    <div
      className={`animate-pulse bg-surface-alt border border-border rounded-md ${className}`}
      style={style}
      aria-hidden="true"
    />
  );
}

export function SkeletonCard({ className = "" }) {
  return (
    <div className={`rounded-lg border border-border bg-surface p-4 ${className}`}>
      <Skeleton className="h-4 w-1/4 mb-4" />
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-4 w-3/4 mt-2" />
    </div>
  );
}

export function SkeletonStatCard({ className = "" }) {
  return (
    <div className={`rounded-lg border border-border bg-surface p-4 ${className}`}>
      <Skeleton className="h-3 w-1/3 mb-3" />
      <Skeleton className="h-10 w-3/4 font-mono" />
      <div className="mt-3 flex gap-4">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-3 w-24" />
      </div>
    </div>
  );
}

export function SkeletonChart({ className = "", height = 300 }) {
  return (
    <div className={`rounded-lg border border-border bg-surface p-4 ${className}`}>
      <Skeleton className="h-4 w-1/4 mb-4" />
      <Skeleton className="w-full" style={{ height }} />
    </div>
  );
}

export function SkeletonTable({ className = "", rows = 5 }) {
  return (
    <div className={`rounded-lg border border-border bg-surface ${className}`}>
      <div className="p-4 border-b border-border">
        <Skeleton className="h-4 w-1/3" />
      </div>
      <div className="divide-y divide-border">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="p-4 grid grid-cols-6 gap-4">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonGauge({ className = "" }) {
  return (
    <div className={`rounded-lg border border-border bg-surface p-4 ${className}`}>
      <Skeleton className="h-4 w-1/3 mb-4" />
      <div className="flex items-center justify-center">
        <Skeleton className="h-32 w-32 rounded-full" />
      </div>
      <Skeleton className="h-3 w-1/2 mt-4 mx-auto" />
    </div>
  );
}

export function SkeletonList({ className = "", items = 5 }) {
  return (
    <div className={`rounded-lg border border-border bg-surface ${className}`}>
      <div className="p-4 border-b border-border">
        <Skeleton className="h-4 w-1/3" />
      </div>
      <div className="divide-y divide-border">
        {Array.from({ length: items }).map((_, i) => (
          <div key={i} className="p-4 flex items-center gap-3">
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-3 w-3/4" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonRow({ className = "", columns = 4 }) {
  return (
    <div className={`flex gap-4 ${className}`}>
      {Array.from({ length: columns }).map((_, i) => (
        <Skeleton key={i} className="h-4 flex-1" />
      ))}
    </div>
  );
}
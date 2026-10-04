export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="w-full max-w-4xl space-y-6">
        <div className="flex items-center justify-between border-b border-[#232734] pb-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-[#F8FAFC]">
              AegisQuant Terminal
            </h1>
            <p className="text-xs text-[#94A3B8]">
              EA Bridge & Quantitative Trade Management
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-[#232734] bg-[#11131A] px-2.5 py-1 text-xs font-mono text-[#94A3B8]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#10B981]" />
              SYSTEM READY
            </span>
          </div>
        </div>
      </div>
    </main>
  );
}

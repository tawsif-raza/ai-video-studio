export function AuthShowcase() {
  return (
    <div className="relative hidden flex-col justify-between overflow-hidden border-r border-zinc-800/80 bg-zinc-950 p-12 lg:flex">
      {/* Subtle cinematic radial lighting */}
      <div
        className="pointer-events-none absolute -top-24 left-1/2 h-[500px] w-[500px] -translate-x-1/2 rounded-full bg-indigo-600/10 blur-3xl"
        aria-hidden="true"
      />

      {/* Top Header & Studio Status */}
      <div className="relative z-10">
        <div className="inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900/90 px-3 py-1 text-xs font-medium text-zinc-300">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          <span>Production Suite v1.1</span>
        </div>
      </div>

      {/* Center Cinematic Card & Narrative */}
      <div className="relative z-10 my-auto flex max-w-lg flex-col gap-6">
        <div className="flex flex-col gap-3">
          <h2 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            From script to screen, orchestrated by autonomous AI agents.
          </h2>
          <p className="text-sm leading-relaxed text-zinc-400">
            Direct scenes, synthesize characters, generate cinematic frames, and assemble multi-scene master cuts in one unified workspace.
          </p>
        </div>

        {/* Mock Cinematic Timeline Preview Card */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5 shadow-2xl backdrop-blur-sm">
          <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-indigo-500" />
              <span className="text-xs font-mono font-medium text-zinc-300">TIMELINE • SCENE 03</span>
            </div>
            <span className="rounded bg-zinc-800 px-2 py-0.5 text-[10px] font-mono text-zinc-400">
              4K UHD • 24 FPS
            </span>
          </div>

          <div className="mt-4 flex flex-col gap-2.5">
            <div className="flex items-center justify-between text-xs text-zinc-400">
              <span className="font-medium text-zinc-200">Director Agent</span>
              <span className="text-[11px] text-emerald-400">Shot Approved</span>
            </div>
            <p className="text-xs italic text-zinc-400">
              &ldquo;Camera dollies through neon rain, rack-focus to lead subject.&rdquo;
            </p>

            <div className="mt-2 flex gap-1.5">
              <div className="h-1.5 flex-1 rounded-full bg-indigo-500" />
              <div className="h-1.5 flex-1 rounded-full bg-indigo-500" />
              <div className="h-1.5 flex-1 rounded-full bg-indigo-500/40" />
              <div className="h-1.5 flex-1 rounded-full bg-zinc-800" />
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Footer Note */}
      <div className="relative z-10 flex items-center justify-between text-xs text-zinc-500">
        <span>AI Video Studio</span>
        <span>Built for professional creators</span>
      </div>
    </div>
  );
}

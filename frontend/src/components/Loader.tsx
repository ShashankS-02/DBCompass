import { useEffect, useState } from "react";
import { CompassMark } from "./Brand";

const DEFAULT_STEPS = ["Reading the knowledge base", "Checking the numbers", "Almost there"];
const STEP_INTERVAL_MS = 1800;

/** Full-width loading state: a seeking compass needle with rotating status messages. */
export function PageLoader({ label = "Loading", steps = DEFAULT_STEPS, showSkeleton = true }: { label?: string; steps?: string[]; showSkeleton?: boolean }) {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => setStepIndex((current) => (current + 1) % steps.length), STEP_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [steps.length]);

  return (
    <div className="flex animate-fade-in flex-col items-center justify-center gap-5 py-20" role="status" aria-live="polite">
      <div className="relative grid h-24 w-24 place-items-center">
        <span className="absolute inset-0 rounded-full bg-coral-200/60 animate-pulse-ring" />
        <span className="absolute inset-0 rounded-full bg-coral-200/40 animate-pulse-ring [animation-delay:0.6s]" />
        <span className="relative grid h-20 w-20 place-items-center rounded-full bg-ink-900 shadow-lift">
          <CompassMark className="h-14 w-14" spinning />
        </span>
      </div>
      <div className="text-center">
        <p className="font-display text-base font-semibold text-slate-800">{label}</p>
        <p key={stepIndex} className="mt-1 animate-fade-up text-sm text-slate-500">
          {steps[stepIndex]}
          <Dots />
        </p>
      </div>
      {showSkeleton && <SkeletonBlock />}
    </div>
  );
}

function Dots() {
  return (
    <span className="ml-1 inline-flex gap-0.5 align-middle">
      <span className="h-1 w-1 rounded-full bg-coral-500 animate-dot-bounce" />
      <span className="h-1 w-1 rounded-full bg-coral-500 animate-dot-bounce [animation-delay:0.15s]" />
      <span className="h-1 w-1 rounded-full bg-coral-500 animate-dot-bounce [animation-delay:0.3s]" />
    </span>
  );
}

function SkeletonBlock() {
  return (
    <div className="mt-4 grid w-full max-w-3xl gap-3 sm:grid-cols-3" aria-hidden="true">
      <div className="skeleton h-24" />
      <div className="skeleton h-24 [animation-delay:0.15s]" />
      <div className="skeleton h-24 [animation-delay:0.3s]" />
      <div className="skeleton h-4 sm:col-span-2" />
      <div className="skeleton h-4 sm:col-span-3" />
    </div>
  );
}

/** Small inline spinner for buttons. */
export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`${className} animate-spin`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

/** Busy overlay for long actions (running the engine, building a plan). */
export function BusyOverlay({ label, steps }: { label: string; steps: string[] }) {
  return (
    <div className="fixed inset-0 z-50 grid animate-fade-in place-items-center bg-ink-950/40 backdrop-blur-sm">
      <div className="w-[min(92vw,30rem)] animate-fade-up rounded-3xl border border-sand-200 bg-sand-50 px-6 shadow-lift">
        <PageLoader label={label} steps={steps} showSkeleton={false} />
      </div>
    </div>
  );
}

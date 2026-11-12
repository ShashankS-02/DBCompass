import type { ReactNode } from "react";
import { Spinner } from "../Loader";

export interface StepMeta {
  id: string;
  title: string;
  short: string;
}

interface Props {
  steps: StepMeta[];
  index: number;
  title: string;
  lead?: string;
  children: ReactNode;
  canContinue: boolean;
  continueLabel?: string;
  skipLabel?: string | null;
  onBack: () => void;
  onNext: () => void;
  onSkip?: () => void;
  busy?: boolean;
  aside?: ReactNode;
}

/** Progress bar, step title and the Back / Skip / Continue row shared by every intake step. */
export default function StepFrame({ steps, index, title, lead, children, canContinue, continueLabel = "Continue", skipLabel = "I don't know, assume defaults", onBack, onNext, onSkip, busy = false, aside }: Props) {
  const percent = Math.round(((index + 1) / steps.length) * 100);
  return (
    <div className="mx-auto max-w-4xl">
      <ol className="mb-3 hidden items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400 sm:flex" aria-label="Steps">
        {steps.map((step, position) => (
          <li key={step.id} className={`flex items-center gap-1 ${position === index ? "text-coral-700" : position < index ? "text-teal-700" : ""}`}>
            <span className={`grid h-5 w-5 place-items-center rounded-full text-[10px] ${position < index ? "bg-teal-600 text-white" : position === index ? "bg-coral-500 text-white" : "bg-sand-100 text-slate-500"}`}>
              {position < index ? "✓" : position + 1}
            </span>
            {step.short}
            {position < steps.length - 1 && <span className="mx-1 h-px w-4 bg-sand-200" />}
          </li>
        ))}
      </ol>
      <div className="mb-5 h-1.5 overflow-hidden rounded-full bg-sand-100">
        <div className="h-full rounded-full bg-gradient-to-r from-coral-500 to-coral-400 transition-all duration-500" style={{ width: `${percent}%` }} />
      </div>

      <div className={`grid gap-6 ${aside ? "lg:grid-cols-[minmax(0,1fr)_280px]" : ""}`}>
        <div key={steps[index]?.id} className="card animate-fade-up p-6">
          <p className="eyebrow">
            Step {index + 1} of {steps.length}
          </p>
          <h1 className="mt-1 font-display text-2xl font-bold text-slate-900">{title}</h1>
          {lead && <p className="mt-1 text-sm text-slate-600">{lead}</p>}
          <div className="mt-5 space-y-6">{children}</div>

          <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-sand-100 pt-4">
            <button type="button" onClick={onBack} disabled={index === 0 || busy} className="btn-ghost px-3 py-2 disabled:opacity-40">
              ← Back
            </button>
            <span className="mr-auto" />
            {onSkip && skipLabel && (
              <button type="button" onClick={onSkip} disabled={busy} className="link-underline text-sm font-semibold text-slate-500 hover:text-coral-700">
                {skipLabel}
              </button>
            )}
            <button type="button" onClick={onNext} disabled={!canContinue || busy} className="btn-primary px-5 py-2 disabled:opacity-50">
              {busy ? <Spinner /> : null} {continueLabel}
            </button>
          </div>
        </div>
        {aside}
      </div>
    </div>
  );
}

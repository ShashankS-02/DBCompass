import { useEffect, useState } from "react";
import { CSP_LABELS, type Recommendation } from "../api/assessments";

export const SETUP_GUIDE_ID = "setup-guide";

function optionName(recommendation: Recommendation): string {
  return recommendation.components.map((component) => component.service_name).join(" + ");
}

/** Basic steps to stand up each recommended option for a new application, one tab per option. */
export default function SetupGuide({ recommendations, selectedRank, onSelect }: { recommendations: Recommendation[]; selectedRank: number; onSelect: (rank: number) => void }) {
  const withGuide = recommendations.filter((recommendation) => (recommendation.setup_guide ?? []).length > 0);
  const [openPhase, setOpenPhase] = useState<string | null>(null);
  const selected = withGuide.find((recommendation) => recommendation.rank === selectedRank) ?? withGuide[0];

  useEffect(() => setOpenPhase(null), [selectedRank]);

  if (!selected) return null;
  const phases = selected.setup_guide ?? [];
  const totalSteps = phases.reduce((count, phase) => count + phase.steps.length, 0);
  let stepNumber = 0;

  return (
    <section id={SETUP_GUIDE_ID} className="card scroll-mt-24 overflow-hidden">
      <div className="border-b border-sand-200 bg-coral-50/60 px-5 py-4">
        <p className="eyebrow">New application</p>
        <h2 className="mt-1 text-xl font-bold text-slate-900">Set up your database</h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Basic steps to stand up the option you pick and connect the application, including any cache, vector or search
          add-on. Work through them with your cloud and DBA teams; the org landing zone rules come first.
        </p>
        <div className="mt-3 flex flex-wrap gap-2" role="tablist" aria-label="Recommended options">
          {withGuide.map((recommendation) => {
            const active = recommendation.rank === selected.rank;
            return (
              <button
                key={recommendation.rank}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => onSelect(recommendation.rank)}
                className={`rounded-xl border px-3 py-1.5 text-left text-xs font-semibold transition ${
                  active ? "border-coral-500 bg-coral-500 text-white shadow-glow" : "border-sand-200 bg-white text-slate-700 hover:border-coral-300"
                }`}
              >
                #{recommendation.rank} · {CSP_LABELS[recommendation.csp]} · {optionName(recommendation)}
              </button>
            );
          })}
        </div>
      </div>
      <div className="px-5 py-4">
        <p className="text-xs text-slate-500">
          {phases.length} phases · {totalSteps} steps · <button type="button" className="font-semibold text-coral-700 hover:underline" onClick={() => setOpenPhase(openPhase === "all" ? null : "all")}>{openPhase === "all" ? "Collapse all" : "Expand all"}</button>
        </p>
        <ol className="mt-3 space-y-2">
          {phases.map((phase, index) => {
            const firstStep = stepNumber + 1;
            stepNumber += phase.steps.length;
            const open = openPhase === "all" || openPhase === phase.id;
            return (
              <li key={phase.id} className="relative pl-10">
                <span className={`absolute left-0 top-2 grid h-7 w-7 place-items-center rounded-full font-display text-xs font-bold ${open ? "bg-coral-500 text-white" : "bg-ink-900 text-white"}`}>
                  {index + 1}
                </span>
                {index < phases.length - 1 && <span className="absolute bottom-[-0.5rem] left-[13px] top-10 w-0.5 bg-sand-200" aria-hidden="true" />}
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => setOpenPhase(open && openPhase !== "all" ? null : phase.id)}
                  className={`flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-2 text-left transition ${open ? "border-coral-300 bg-coral-50/60" : "border-sand-200 bg-white hover:border-coral-200"}`}
                >
                  <span className="text-sm font-semibold text-slate-900">{phase.title}</span>
                  <span className="text-[11px] text-slate-500">{phase.steps.length} step{phase.steps.length > 1 ? "s" : ""}</span>
                </button>
                {open && (
                  <ol className="mt-2 animate-fade-up space-y-1.5 pb-1 text-sm text-slate-700" start={firstStep}>
                    {phase.steps.map((step, stepIndex) => (
                      <li key={step} className="flex gap-2">
                        <span className="w-6 shrink-0 text-right font-semibold tabular-nums text-coral-600">{firstStep + stepIndex}.</span>
                        <span>{step}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createAssessment, type AssessmentResult } from "../api/assessments";
import { ApiError } from "../api/client";
import type { PrioritySlider, Question } from "../api/questions";
import { runWhatIf, type WhatIfRequest, type WhatIfResult } from "../api/whatif";
import { useAuth } from "../auth/AuthProvider";
import { Spinner } from "./Loader";

const TRAFFIC_MULTIPLIERS = [0.5, 1, 2, 5, 10, 20];
const BASE_MULTIPLIER_INDEX = 1;
const DEBOUNCE_MS = 450;

type Money = { amount: number; currency: string };

function baseValue(result: AssessmentResult, fieldId: string): unknown {
  if (fieldId in result.input.answers) {
    return result.input.answers[fieldId];
  }
  return result.trace.assumed_fields.find((field) => field.field_id === fieldId)?.value;
}

function sameSet(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((item) => right.includes(item));
}

interface Controls {
  multiplierIndex: number;
  sla: string;
  regions: string[];
  budget: string;
  priorities: Record<string, number>;
}

function initialControls(result: AssessmentResult, sliders: PrioritySlider[]): Controls {
  const budget = result.input.answers["cost.monthly_cap"] as Money | undefined;
  const priorities: Record<string, number> = {};
  for (const slider of sliders) {
    priorities[slider.id] = result.input.priorities[slider.id] ?? slider.default;
  }
  return {
    multiplierIndex: BASE_MULTIPLIER_INDEX,
    sla: (baseValue(result, "ha.sla") as string | undefined) ?? "",
    regions: (baseValue(result, "geo.user_regions") as string[] | undefined) ?? [],
    budget: budget ? String(budget.amount) : "",
    priorities,
  };
}

function buildRequest(result: AssessmentResult, base: Controls, current: Controls): WhatIfRequest {
  const answers: Record<string, unknown> = {};
  const baseTps = baseValue(result, "wl.peak_tps") as number | undefined;
  if (current.multiplierIndex !== BASE_MULTIPLIER_INDEX && baseTps) {
    answers["wl.peak_tps"] = Math.max(1, Math.round(baseTps * TRAFFIC_MULTIPLIERS[current.multiplierIndex]));
  }
  if (current.sla && current.sla !== base.sla) answers["ha.sla"] = current.sla;
  if (!sameSet(current.regions, base.regions) && current.regions.length > 0) answers["geo.user_regions"] = current.regions;
  if (current.budget.trim() !== base.budget) {
    const amount = Number(current.budget);
    const currency = (result.input.answers["cost.monthly_cap"] as Money | undefined)?.currency ?? "usd";
    answers["cost.monthly_cap"] = current.budget.trim() === "" ? null : Number.isFinite(amount) && amount > 0 ? { amount, currency } : undefined;
    if (answers["cost.monthly_cap"] === undefined) delete answers["cost.monthly_cap"];
  }
  const priorities: Record<string, number> = {};
  for (const [sliderId, value] of Object.entries(current.priorities)) {
    if (value !== base.priorities[sliderId]) priorities[sliderId] = value;
  }
  return { answers, priorities };
}

function isEmpty(request: WhatIfRequest): boolean {
  return Object.keys(request.answers).length === 0 && Object.keys(request.priorities).length === 0;
}

interface Props {
  result: AssessmentResult;
  sliders: PrioritySlider[];
  questions: Map<string, Question>;
  scenario: WhatIfResult | null;
  onScenario: (scenario: WhatIfResult | null) => void;
}

/** Sliders that re-run the engine on a copy of the inputs; nothing is stored until "Save". */
export default function WhatIfPanel({ result, sliders, questions, scenario, onScenario }: Props) {
  const { getAccessToken } = useAuth();
  const navigate = useNavigate();
  const base = useMemo(() => initialControls(result, sliders), [result, sliders]);
  const [controls, setControls] = useState<Controls>(base);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestCounter = useRef(0);

  useEffect(() => setControls(base), [base]);

  const request = useMemo(() => buildRequest(result, base, controls), [result, base, controls]);
  const requestKey = JSON.stringify(request);

  useEffect(() => {
    if (isEmpty(request)) {
      onScenario(null);
      setError(null);
      return;
    }
    const ticket = ++requestCounter.current;
    const timer = window.setTimeout(() => {
      setRunning(true);
      runWhatIf(result.id, request, getAccessToken)
        .then((outcome) => {
          if (ticket === requestCounter.current) {
            onScenario(outcome);
            setError(null);
          }
        })
        .catch((caught) => {
          if (ticket === requestCounter.current) {
            setError(caught instanceof ApiError && caught.status === 422 ? "These values are not valid for this assessment." : (caught as Error).message);
          }
        })
        .finally(() => ticket === requestCounter.current && setRunning(false));
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey, result.id, getAccessToken]);

  const save = async () => {
    if (!scenario) return;
    setSaving(true);
    try {
      const created = await createAssessment(scenario.input, getAccessToken);
      navigate(`/assessments/${created.id}`);
    } catch (caught) {
      setError((caught as Error).message);
      setSaving(false);
    }
  };

  const slaQuestion = questions.get("ha.sla");
  const regionQuestion = questions.get("geo.user_regions");
  const baseTps = baseValue(result, "wl.peak_tps") as number | undefined;
  const multiplier = TRAFFIC_MULTIPLIERS[controls.multiplierIndex];
  const set = (patch: Partial<Controls>) => setControls((current) => ({ ...current, ...patch }));

  return (
    <section className={`card overflow-hidden transition duration-300 ${scenario ? "ring-2 ring-coral-200" : ""}`}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-sand-100 bg-gradient-to-r from-teal-700 to-teal-600 px-5 py-3 text-snow">
        <div>
          <h2 className="text-lg font-semibold">What if…?</h2>
          <p className="text-xs text-teal-100">Change an input and the engine re-ranks straight away. Nothing is saved.</p>
        </div>
        <div className="flex items-center gap-2">
          {running && <Spinner className="h-4 w-4 text-coral-300" />}
          {!isEmpty(request) && (
            <button type="button" onClick={() => setControls(base)} className="rounded-lg border border-white/25 px-3 py-1.5 text-xs font-semibold hover:bg-white/10">
              Reset
            </button>
          )}
        </div>
      </div>

      <div className="grid gap-6 p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <label className="block">
            <span className="flex items-baseline justify-between text-sm">
              <span className="font-semibold text-slate-800">Peak traffic</span>
              <span className={`font-display text-lg font-bold tabular-nums transition ${multiplier === 1 ? "text-slate-400" : "text-coral-600"}`}>
                ×{multiplier}
              </span>
            </span>
            <input
              type="range"
              min={0}
              max={TRAFFIC_MULTIPLIERS.length - 1}
              step={1}
              value={controls.multiplierIndex}
              disabled={!baseTps}
              onChange={(event) => set({ multiplierIndex: Number(event.target.value) })}
              className="mt-2 w-full"
              aria-label="Peak traffic multiplier"
            />
            <span className="text-xs text-slate-500">
              {baseTps ? `${Math.round(baseTps * multiplier).toLocaleString()} TPS (now ${baseTps.toLocaleString()})` : "Peak traffic was not given."}
            </span>
          </label>

          {slaQuestion && (
            <div>
              <span className="text-sm font-semibold text-slate-800">Availability target</span>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {slaQuestion.options.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => set({ sla: option.value })}
                    className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                      controls.sla === option.value ? "border-teal-600 bg-teal-600 text-white" : "border-sand-200 bg-white text-slate-600 hover:border-coral-300"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {regionQuestion && (
            <div>
              <span className="text-sm font-semibold text-slate-800">Where users are</span>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {regionQuestion.options.map((option) => {
                  const selected = controls.regions.includes(option.value);
                  return (
                    <button
                      key={option.value}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => set({ regions: selected ? controls.regions.filter((item) => item !== option.value) : [...controls.regions, option.value] })}
                      className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                        selected ? "border-teal-600 bg-teal-600 text-white" : "border-sand-200 bg-white text-slate-600 hover:border-coral-300"
                      }`}
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <label className="block">
            <span className="text-sm font-semibold text-slate-800">Monthly budget cap</span>
            <input
              type="number"
              min={0}
              className="mt-2 w-full border px-3 py-1.5 text-sm"
              placeholder="No cap"
              value={controls.budget}
              onChange={(event) => set({ budget: event.target.value })}
            />
          </label>
        </div>

        <div className="space-y-3">
          <span className="text-sm font-semibold text-slate-800">Priorities</span>
          {sliders.map((slider) => (
            <label key={slider.id} className="block">
              <span className="flex justify-between text-xs">
                <span className="text-slate-600">{slider.label}</span>
                <span className={`tabular-nums ${controls.priorities[slider.id] !== base.priorities[slider.id] ? "font-bold text-coral-600" : "text-slate-400"}`}>
                  {controls.priorities[slider.id]}
                </span>
              </span>
              <input
                type="range"
                min={0}
                max={100}
                value={controls.priorities[slider.id] ?? slider.default}
                onChange={(event) => set({ priorities: { ...controls.priorities, [slider.id]: Number(event.target.value) } })}
                className="w-full"
                aria-label={`${slider.label} priority`}
              />
            </label>
          ))}
        </div>
      </div>

      {error && <p className="px-5 pb-4 text-sm text-rose-600">{error}</p>}

      {scenario && (
        <div className="animate-fade-up border-t border-coral-100 bg-coral-50/50 px-5 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow">What changed</p>
              <ul className="mt-2 space-y-1 text-sm text-slate-700">
                {scenario.changes.summary.map((line, index) => (
                  <li key={line} className="flex gap-2" style={{ animation: `fade-up 0.4s ease-out ${index * 60}ms backwards` }}>
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-coral-500" />
                    {line}
                  </li>
                ))}
              </ul>
            </div>
            <button type="button" onClick={() => void save()} disabled={saving} className="btn-primary">
              {saving ? <Spinner /> : null} Save as new assessment
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

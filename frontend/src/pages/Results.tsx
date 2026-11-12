import { useEffect, useMemo, useState } from "react";
import { PageLoader } from "../components/Loader";
import { Link, useParams } from "react-router-dom";
import { CSP_LABELS, ROLE_LABELS, fetchAssessment, type AssessmentResult, type Baseline, type Recommendation } from "../api/assessments";
import { fetchIntake, type IntakeConfig } from "../api/intake";
import { describeValue, fetchQuestions, type PrioritySlider, type Question } from "../api/questions";
import type { RankMove, WhatIfResult } from "../api/whatif";
import { useAuth } from "../auth/AuthProvider";
import { READINESS_STYLES, type Readiness } from "../api/intake";
import { engineLabel } from "../api/labels";
import { COMMERCIAL_ENGINES } from "../api/requests";
import CostTiers, { formatMoney, type Currency } from "../components/CostTiers";
import ScoreRadar from "../components/ScoreRadar";
import WhyNotPanel from "../components/WhyNotPanel";
import ExplanationPanel from "../components/ExplanationPanel";
import ExportMenu from "../components/ExportMenu";
import WhatIfPanel from "../components/WhatIfPanel";

interface CardProps {
  recommendation: Recommendation;
  currency: Currency;
  inrPerUsd: number | null;
  move?: RankMove;
  planLink?: string; // existing application: plan the migration to this option
}

function optionTitle(recommendation: Recommendation): string {
  return recommendation.components.map((component) => component.service_name).join(" + ");
}

function MoveBadge({ move }: { move?: RankMove }) {
  if (!move || move.after_rank === null) return null;
  if (move.before_rank === null) {
    return <span className="rounded-full bg-gold-100 px-2 py-0.5 text-[11px] font-bold text-gold-800">New</span>;
  }
  if (move.before_rank === move.after_rank) return null;
  const up = move.after_rank < move.before_rank;
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${up ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>
      {up ? "▲" : "▼"} was #{move.before_rank}
    </span>
  );
}

function ReadinessPanel({ readiness }: { readiness: Readiness }) {
  return (
    <section className={`card border p-4 ${READINESS_STYLES[readiness.verdict]}`}>
      <p className="eyebrow">Team readiness</p>
      <h2 className="mt-1 font-display text-lg font-bold">{readiness.label}</h2>
      <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm">
        {readiness.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      {readiness.actions.length > 0 && (
        <p className="mt-2 text-sm">
          <span className="font-semibold">Next: </span>
          {readiness.actions.join(" ")}
        </p>
      )}
    </section>
  );
}

function VersusBaseline({ recommendation, currency, inrPerUsd }: { recommendation: Recommendation; currency: Currency; inrPerUsd: number | null }) {
  const versus = recommendation.versus_baseline;
  if (!versus) return null;
  if (versus.same_service) {
    return (
      <p className="mt-3 rounded-xl border-2 border-sand-300 bg-sand-50 px-3 py-2 text-sm font-semibold text-slate-700">
        Like-for-like: this is staying on {versus.engine_label}
      </p>
    );
  }
  if (versus.delta_usd === null) {
    return <p className="mt-3 rounded-xl border border-sand-200 bg-sand-50 px-3 py-2 text-xs text-slate-600">Versus staying on {versus.engine_label}: {versus.message}</p>;
  }
  const cheaper = versus.delta_usd < 0;
  const same = Math.abs(versus.delta_usd) < 1;
  const tone = same ? "border-sand-300 bg-sand-50 text-slate-800" : cheaper ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-rose-300 bg-rose-50 text-rose-900";
  const percent = versus.baseline_core_usd ? Math.round((Math.abs(versus.delta_usd) / versus.baseline_core_usd) * 100) : null;
  return (
    <div className={`mt-3 rounded-xl border-2 px-3 py-2 ${tone}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wide opacity-80">vs staying on {versus.engine_label}</p>
      <p className="text-2xl font-extrabold tabular-nums leading-tight">
        {same ? "About the same" : `${cheaper ? "−" : "+"}${formatMoney(Math.abs(versus.delta_usd), currency, inrPerUsd)}`}
        {!same && <span className="text-sm font-semibold"> / month{percent !== null ? ` (${cheaper ? "−" : "+"}${percent}%)` : ""}</span>}
      </p>
      {!same && <p className="text-xs font-medium opacity-80">{cheaper ? "Saves" : "Costs"} {formatMoney(Math.abs(versus.delta_usd) * 12, currency, inrPerUsd)} a year on compute and licences</p>}
    </div>
  );
}

function ComparisonBar({ label, value, max, tone, currency, inrPerUsd }: { label: string; value: number; max: number; tone: string; currency: Currency; inrPerUsd: number | null }) {
  const width = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return (
    <div className="text-xs">
      <div className="flex justify-between gap-2 text-slate-600">
        <span className="truncate">{label}</span>
        <span className="tabular-nums font-semibold text-slate-800">{formatMoney(value, currency, inrPerUsd)}</span>
      </div>
      <div className="mt-0.5 h-2.5 w-full rounded-full bg-sand-100">
        <div className={`h-2.5 rounded-full ${tone}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

/** The headline comparison with staying on the current engine, shown above the recommendation cards (M9). */
function PriceDifferenceBanner({ recommendations, baselines, currency, inrPerUsd }: { recommendations: Recommendation[]; baselines: Record<string, Baseline>; currency: Currency; inrPerUsd: number | null }) {
  const compared = recommendations.filter((item) => item.versus_baseline && !item.versus_baseline.same_service && item.versus_baseline.delta_usd !== null);
  const entries = Object.values(baselines);
  if (!entries.length) return null;
  const engine = entries[0].engine_label;
  const bestSaving = compared.reduce((best, item) => Math.min(best, item.versus_baseline?.delta_usd ?? 0), 0);
  return (
    <section className="card overflow-hidden border-2 border-emerald-200">
      <div className="bg-gradient-to-r from-emerald-50 to-white p-5">
        <p className="eyebrow">Price difference against staying on {engine}</p>
        <h2 className="mt-1 text-2xl font-extrabold text-slate-900 sm:text-3xl">
          {bestSaving < -1 ? (
            <>
              Up to <span className="text-emerald-700">{formatMoney(Math.abs(bestSaving), currency, inrPerUsd)} less a month</span>{" "}
              <span className="text-lg font-semibold text-slate-600">({formatMoney(Math.abs(bestSaving) * 12, currency, inrPerUsd)} a year)</span>
            </>
          ) : compared.length ? (
            <>No recommended option is cheaper than staying on {engine}</>
          ) : (
            <>Staying on {engine} cannot be priced for comparison</>
          )}
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Compute and licences at the Balanced tier, compared with running {engine} on the same cloud. Storage, backup and network would be about the
          same either way and are left out. On-prem costs are not needed.
        </p>
      </div>
      {compared.length > 0 && (
        <div className="grid gap-4 border-t border-emerald-100 p-5 md:grid-cols-3">
          {compared.map((item) => {
            const versus = item.versus_baseline!;
            const delta = versus.delta_usd ?? 0;
            const cheaper = delta < 0;
            const baseline = versus.baseline_core_usd ?? 0;
            const option = versus.recommendation_core_usd ?? 0;
            const max = Math.max(baseline, option);
            const percent = baseline ? Math.round((Math.abs(delta) / baseline) * 100) : null;
            return (
              <div key={`${item.rank}-${item.components[0].service_id}`} className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">#{item.rank} · {CSP_LABELS[item.csp]}</p>
                <p className="font-semibold text-slate-900">{optionTitle(item)}</p>
                <p className={`text-3xl font-extrabold tabular-nums ${cheaper ? "text-emerald-700" : "text-rose-700"}`}>
                  {cheaper ? "−" : "+"}{formatMoney(Math.abs(delta), currency, inrPerUsd)}
                  <span className="text-sm font-semibold text-slate-500"> / month{percent !== null ? ` · ${cheaper ? "−" : "+"}${percent}%` : ""}</span>
                </p>
                <ComparisonBar label={`Staying: ${versus.baseline_service_name}`} value={baseline} max={max} tone="bg-slate-400" currency={currency} inrPerUsd={inrPerUsd} />
                <ComparisonBar label={`Moving: ${optionTitle(item)}`} value={option} max={max} tone={cheaper ? "bg-emerald-500" : "bg-rose-500"} currency={currency} inrPerUsd={inrPerUsd} />
              </div>
            );
          })}
        </div>
      )}
      <ul className="space-y-1 border-t border-emerald-100 bg-white px-5 py-3 text-xs text-slate-500">
        {entries.map((baseline) => (
          <li key={baseline.csp}>
            <span className="font-semibold text-slate-700">{CSP_LABELS[baseline.csp]} baseline:</span>{" "}
            {baseline.core_monthly_usd !== null ? `${formatMoney(baseline.core_monthly_usd, currency, inrPerUsd)} a month on ${baseline.service_name}. ` : ""}
            {baseline.note}
          </li>
        ))}
      </ul>
    </section>
  );
}

function AddOnsPanel({ result, intake }: { result: AssessmentResult; intake: IntakeConfig | null }) {
  if (!intake) return null;
  const keptOut = result.trace.filtered_out.filter((reason) => reason.rule_id === "SPECIAL-CASE");
  const byKind = new Map<string, string[]>();
  keptOut.forEach((reason) => {
    const message = reason.message;
    const kind = Object.entries(intake.org_support.special_cases).find(([, spec]) => message.toLowerCase().includes(spec.label.toLowerCase()))?.[0];
    if (!kind) return;
    const list = byKind.get(kind) ?? [];
    const name = message.split(" is kept for")[0];
    if (!list.includes(name)) list.push(name);
    byKind.set(kind, list);
  });
  if (!byKind.size) return null;
  return (
    <section className="card p-4">
      <p className="eyebrow">If you need more than a database</p>
      <p className="mt-1 text-sm text-slate-600">
        These special-purpose services are kept for one job each. They are never the main database, but the engine adds them to a combination when the
        answers call for caching, search or analytics.
      </p>
      <ul className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
        {[...byKind.entries()].map(([kind, serviceIds]) => (
          <li key={kind} className="rounded-xl border border-sand-200 bg-white p-3">
            <p className="font-semibold text-slate-900">{intake.org_support.special_cases[kind as keyof typeof intake.org_support.special_cases]?.label ?? kind}</p>
            <p className="text-xs text-slate-500">{intake.org_support.special_cases[kind as keyof typeof intake.org_support.special_cases]?.description}</p>
            <p className="mt-1 text-xs text-slate-700">{serviceIds.join(" · ")}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function RecommendationCard({ recommendation, currency, inrPerUsd, move, planLink }: CardProps) {
  return (
    <article className={`card card-hover flex flex-col p-5 ${recommendation.rank === 1 ? "border-t-4 border-t-coral-500" : ""}`}>
      <header className="flex items-start justify-between gap-2">
        <div>
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            #{recommendation.rank} · {CSP_LABELS[recommendation.csp]}
            <MoveBadge move={move} />
          </p>
          <h2 className="mt-1 font-semibold text-slate-900">
            {recommendation.components.map((component) => component.service_name).join(" + ")}
          </h2>
        </div>
        <span className="rounded-lg bg-coral-500 px-2 py-0.5 text-sm font-bold tabular-nums text-white shadow-glow">
          {recommendation.total_score.toFixed(1)}
        </span>
      </header>

      <VersusBaseline recommendation={recommendation} currency={currency} inrPerUsd={inrPerUsd} />

      <ScoreRadar scores={recommendation.dimension_scores} />

      <dl className="space-y-2 text-sm">
        {recommendation.components.map((component) => (
          <div key={component.service_id} className="rounded-xl bg-sand-50 p-2.5">
            <dt className="text-xs font-medium text-slate-500">
              {ROLE_LABELS[component.role] ?? component.role} · {component.engine}
              {component.engine_version ? ` ${component.engine_version}` : ""}
            </dt>
            <dd className="text-slate-800">
              {component.instance_class} · {component.storage_tier}
              {component.replicas > 0 ? ` · ${component.replicas} replica${component.replicas > 1 ? "s" : ""}` : ""}
            </dd>
          </div>
        ))}
        <div>
          <dt className="text-xs font-medium text-slate-500">HA layout</dt>
          <dd className="text-slate-800">{recommendation.ha_topology}</dd>
        </div>
        <div>
          <dt className="mb-1 text-xs font-medium text-slate-500">Monthly cost (list price)</dt>
          <dd>
            <CostTiers tiers={recommendation.cost_tiers} currency={currency} inrPerUsd={inrPerUsd} />
          </dd>
        </div>
      </dl>

      <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">Why this</h3>
      <ul className="mt-1 list-disc space-y-1 pl-4 text-sm text-slate-700">
        {recommendation.why.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>

      {recommendation.design_guidance.length > 0 && (
        <>
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">Design notes</h3>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-sm text-slate-700">
            {recommendation.design_guidance.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
      {planLink && (
        <Link to={planLink} className="btn-ghost mt-4 justify-center px-3 py-1.5 text-sm hover:border-slate-500">
          Plan migration to this option
        </Link>
      )}
    </article>
  );
}

function engineOf(value: unknown): string | null {
  const engine = (value as { engine?: string } | undefined)?.engine;
  return engine && engine !== "none" ? engine : null;
}

function NextSteps({ result }: { result: AssessmentResult }) {
  const answers = result.input.answers;
  const requested = engineOf(answers["app.requested_engine"]);
  const source = engineOf(answers["mig.source_engine"]) ?? engineOf(answers["app.existing_db"]);
  const licensedEngine = [requested, source].find((engine) => engine && COMMERCIAL_ENGINES.includes(engine)) ?? null;
  const kind = requested && requested !== source ? "new_database" : source ? "migration" : "new_database";
  return (
    <section className="flex flex-wrap items-center gap-3 card p-4">
      <div className="mr-auto text-sm">
        <h2 className="font-medium text-slate-900">Next steps</h2>
        {licensedEngine ? (
          <p className="text-amber-800">
            {engineLabel(licensedEngine)} needs a commercial licence. Before a request is approved the team must explain why, and DBCompass
            compares it with the best licence-free option.
          </p>
        ) : (
          <p className="text-slate-600">Plan the migration, or raise a database request for approval.</p>
        )}
      </div>
      {source && (
        <Link to={`/migrations/new?assessment=${result.id}`} className="btn-ghost px-3 py-1.5 hover:border-slate-500">
          Plan migration
        </Link>
      )}
      <Link
        to={`/requests/new?assessment=${result.id}&kind=${kind}${licensedEngine ? `&engine=${licensedEngine}` : requested ? `&engine=${requested}` : ""}`}
        className="btn-primary"
      >
        {licensedEngine ? `Justify ${engineLabel(licensedEngine)}` : "Raise a database request"}
      </Link>
    </section>
  );
}

export default function Results() {
  const { id = "" } = useParams();
  const { getAccessToken } = useAuth();
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [questions, setQuestions] = useState<Map<string, Question>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [currency, setCurrency] = useState<Currency>("usd");
  const [sliders, setSliders] = useState<PrioritySlider[]>([]);
  const [scenario, setScenario] = useState<WhatIfResult | null>(null);
  const [intake, setIntake] = useState<IntakeConfig | null>(null);

  useEffect(() => {
    fetchAssessment(id, getAccessToken)
      .then(setResult)
      .catch((loadError: Error) => setError(loadError.message));
    fetchQuestions("expert", getAccessToken)
      .then((schema) => {
        const index = new Map<string, Question>();
        schema.sections.forEach((section) => section.questions.forEach((question) => index.set(question.id, question)));
        setQuestions(index);
        setSliders(schema.priority_sliders);
      })
      .catch(() => setQuestions(new Map()));
    fetchIntake(getAccessToken).then(setIntake).catch(() => setIntake(null));
  }, [id, getAccessToken]);

  const view: AssessmentResult | null = useMemo(
    () => (result && scenario ? { ...result, ...scenario.outcome, input: scenario.input } : result),
    [result, scenario],
  );

  const moves = useMemo(() => {
    const byTitle = new Map<string, RankMove>();
    scenario?.changes.rank_moves.forEach((move) => byTitle.set(`${move.option}|${move.csp}`, move));
    return byTitle;
  }, [scenario]);

  const recommendedIds = useMemo(() => {
    const ids = new Set<string>();
    view?.recommendations.forEach((recommendation) => recommendation.components.forEach((component) => ids.add(component.service_id)));
    return ids;
  }, [view]);

  if (error) {
    return <p className="text-rose-600">Could not load this assessment: {error}</p>;
  }
  const isExisting = Boolean(engineOf(result?.input.answers["mig.source_engine"]) ?? engineOf(result?.input.answers["app.existing_db"]));
  if (!result || !view) {
    return <PageLoader label="Loading recommendations" steps={["Fetching the assessment", "Laying out cost tiers", "Drawing score charts"]} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">
            {(result.input.answers["app.name"] as string | undefined) ? `${result.input.answers["app.name"] as string}: recommendations` : "Recommendations"}
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            {new Date(result.created_at).toLocaleString()} · engine {result.engine_version} · {result.trace.rules_fired.length} rules
            fired · {new Set(result.trace.filtered_out.map((reason) => reason.service_id)).size} services filtered out
          </p>
        </div>
        <div className="flex items-center gap-2">
          {result.pricing?.inr_per_usd && (
            <div className="inline-flex rounded-xl border border-sand-200 bg-white p-1 shadow-soft" role="group" aria-label="Currency">
              {(["usd", "inr"] as Currency[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  aria-pressed={currency === option}
                  onClick={() => setCurrency(option)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${currency === option ? "bg-teal-600 text-white shadow-soft" : "text-slate-600 hover:bg-sand-50"}`}
                >
                  {option.toUpperCase()}
                </button>
              ))}
            </div>
          )}
          <Link to="/assessments/new" className="btn-ghost px-3 py-1.5">
            New assessment
          </Link>
          <ExportMenu assessmentId={result.id} />
        </div>
      </div>

      {result.pricing && (
        <p className="text-xs text-slate-500">
          Prices as of{" "}
          {Object.entries(result.pricing.prices_as_of)
            .map(([csp, date]) => `${CSP_LABELS[csp]} ${new Date(date).toLocaleDateString()}`)
            .join(" · ") || "—"}
          {result.pricing.inr_per_usd ? ` · ₹${result.pricing.inr_per_usd}/USD (${result.pricing.inr_rate_date || "date not set"})` : ""}
          {" · "}
          {result.pricing.notes.join(" ")}
        </p>
      )}

      <NextSteps result={result} />

      {(view.readiness || typeof result.input.answers["app.notes"] === "string") && (
        <div className="grid gap-4 lg:grid-cols-2">
          {view.readiness && <ReadinessPanel readiness={view.readiness} />}
          {typeof result.input.answers["app.notes"] === "string" && (
            <section className="card p-4">
              <p className="eyebrow">Notes from the team</p>
              <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{result.input.answers["app.notes"] as string}</p>
            </section>
          )}
        </div>
      )}

      {Object.keys(view.baselines ?? {}).length > 0 && view.recommendations.length > 0 && (
        <PriceDifferenceBanner recommendations={view.recommendations} baselines={view.baselines} currency={currency} inrPerUsd={result.pricing?.inr_per_usd ?? null} />
      )}

      {scenario && (
        <p className="flex items-center gap-2 text-sm font-semibold text-coral-700">
          <span className="h-2 w-2 animate-pulse rounded-full bg-coral-500" /> Showing the what-if scenario. The saved result is unchanged.
        </p>
      )}

      {view.recommendations.length === 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          {view.trace.combination_notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
        </div>
      ) : (
        <div key={scenario ? JSON.stringify(scenario.input) : "saved"} className="stagger grid gap-5 lg:grid-cols-3">
          {view.recommendations.map((recommendation) => (
            <RecommendationCard
              key={`${optionTitle(recommendation)}|${recommendation.csp}`}
              recommendation={recommendation}
              move={moves.get(`${optionTitle(recommendation)}|${recommendation.csp}`)}
              currency={currency}
              inrPerUsd={result.pricing?.inr_per_usd ?? null}
              planLink={!scenario && isExisting ? `/migrations/new?assessment=${result.id}&target=${recommendation.components[0].service_id}` : undefined}
            />
          ))}
        </div>
      )}

      {sliders.length > 0 && <WhatIfPanel result={result} sliders={sliders} questions={questions} scenario={scenario} onScenario={setScenario} />}

      <AddOnsPanel result={view} intake={intake} />

      <ExplanationPanel assessmentId={result.id} scenarioActive={scenario !== null} />

      <div className="grid gap-4 lg:grid-cols-2">
        <WhyNotPanel filteredOut={view.trace.filtered_out} scores={view.trace.scores} recommendedIds={recommendedIds} />

        <section className="card p-4">
          <h2 className="font-medium text-slate-900">Assumptions ({view.trace.assumed_fields.length})</h2>
          <p className="mt-1 text-sm text-slate-600">Fields you left empty, filled from defaults.</p>
          <ul className="mt-3 space-y-1 text-sm text-slate-700">
            {view.trace.assumed_fields.map((field) => (
              <li key={field.field_id}>
                {questions.get(field.field_id)?.label ?? field.field_id}:{" "}
                <span className="font-medium">{describeValue(questions.get(field.field_id), field.value)}</span>
                <span className="text-xs text-slate-500"> ({field.reason})</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

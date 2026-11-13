import { useEffect, useMemo, useState } from "react";
import { PageLoader } from "../components/Loader";
import { Link, useParams } from "react-router-dom";
import { CSP_LABELS, ROLE_LABELS, fetchAssessment, type AssessmentResult, type Baseline, type CostLine, type Recommendation, type ServiceChoice } from "../api/assessments";
import { fetchIntake, type IntakeConfig } from "../api/intake";
import { describeValue, fetchQuestions, type PrioritySlider, type Question } from "../api/questions";
import Disclosure from "../components/Disclosure";
import SetupGuide, { SETUP_GUIDE_ID } from "../components/SetupGuide";
import { useAuth } from "../auth/AuthProvider";
import { READINESS_STYLES, type Readiness } from "../api/intake";
import { engineLabel } from "../api/labels";
import { COMMERCIAL_ENGINES } from "../api/requests";
import CostTiers, { formatMoney, formatUnitPrice, type Currency } from "../components/CostTiers";
import ScoreRadar from "../components/ScoreRadar";
import WhyNotPanel from "../components/WhyNotPanel";
import ExplanationPanel from "../components/ExplanationPanel";
import ExportMenu from "../components/ExportMenu";

interface CardProps {
  recommendation: Recommendation;
  currency: Currency;
  inrPerUsd: number | null;
  planLink?: string; // existing application: plan the migration to this option
  onSetupGuide?: () => void; // new application: open this option's setup guide
}

function optionTitle(recommendation: Recommendation): string {
  return recommendation.components.map((component) => component.service_name).join(" + ");
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

function lineLabel(line: CostLine): string {
  const parts = line.component.split(" · ");
  const kind = parts[parts.length - 1];
  if (kind === "licence") return "Licence";
  if (kind === "compute") return "Servers (compute)";
  const words = kind.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** One side of the comparison: its compute and licence lines, the environments factor and the total. */
function CoreBreakdown({ title, name, lines, multiplier, total, tone, currency, inrPerUsd }: {
  title: string; name: string; lines: CostLine[]; multiplier: number; total: number; tone: "stay" | "move";
  currency: Currency; inrPerUsd: number | null;
}) {
  const subtotal = lines.reduce((sum, line) => sum + line.monthly_usd, 0);
  return (
    <div className={`rounded-xl border p-3 ${tone === "stay" ? "border-sand-300 bg-sand-50" : "border-coral-200 bg-coral-50/50"}`}>
      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{title}</p>
      <p className="font-semibold text-slate-900">{name}</p>
      <table className="mt-2 w-full text-xs">
        <tbody>
          {lines.map((line) => (
            <tr key={`${line.component}-${line.description}`} className="border-t border-sand-200/70 align-top">
              <td className="py-1 pr-2">
                <span className="font-semibold text-slate-800">{lineLabel(line)}</span>
                <span className="block text-slate-500">{line.description}</span>
                <span className="block text-slate-400">
                  {line.quantity.toLocaleString()} {line.unit} × {formatUnitPrice(line.unit_usd, currency, inrPerUsd)}
                </span>
              </td>
              <td className="py-1 text-right font-semibold tabular-nums text-slate-800">{formatMoney(line.monthly_usd, currency, inrPerUsd)}</td>
            </tr>
          ))}
          {multiplier !== 1 && (
            <tr className="border-t border-sand-200/70">
              <td className="py-1 pr-2 text-slate-600">
                {formatMoney(subtotal, currency, inrPerUsd)} × {multiplier.toFixed(2)} for your environments
                <span className="block text-slate-400">Production counts once; each other environment adds its share.</span>
              </td>
              <td />
            </tr>
          )}
          <tr className="border-t-2 border-sand-300">
            <td className="py-1.5 font-bold text-slate-900">Per month</td>
            <td className="py-1.5 text-right text-base font-extrabold tabular-nums text-slate-900">{formatMoney(total, currency, inrPerUsd)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/** The comparison with staying on the current engine, with the full working (M9, redone in M11). */
function PriceDifferenceBanner({ recommendations, baselines, currency, inrPerUsd }: { recommendations: Recommendation[]; baselines: Record<string, Baseline>; currency: Currency; inrPerUsd: number | null }) {
  const compared = recommendations.filter((item) => item.versus_baseline && !item.versus_baseline.same_service && item.versus_baseline.delta_usd !== null);
  const likeForLike = recommendations.filter((item) => item.versus_baseline?.same_service);
  const unpriced = recommendations.filter((item) => item.versus_baseline && !item.versus_baseline.same_service && item.versus_baseline.delta_usd === null);
  const entries = Object.values(baselines);
  if (!entries.length) return null;
  const engine = entries[0].engine_label;
  const bestSaving = compared.reduce((best, item) => Math.min(best, item.versus_baseline?.delta_usd ?? 0), 0);
  return (
    <section className="card overflow-hidden">
      <div className="bg-gradient-to-r from-coral-50 to-white p-5">
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
        <ol className="mt-3 grid gap-3 text-sm text-slate-700 md:grid-cols-3">
          <li className="rounded-xl bg-white/80 p-3 ring-1 ring-sand-200">
            <span className="font-bold text-coral-700">1. What "staying" means.</span> Keep {engine} but move it to the same cloud as the option, on the
            cheapest {engine} service there that has a list price. It gets the same size and the same high-availability layout as the option.
          </li>
          <li className="rounded-xl bg-white/80 p-3 ring-1 ring-sand-200">
            <span className="font-bold text-coral-700">2. What is compared.</span> Only the monthly cost of the servers and the database licences, at
            the Balanced tier list price. Storage, backup and network cost about the same either way, so they are left out.
          </li>
          <li className="rounded-xl bg-white/80 p-3 ring-1 ring-sand-200">
            <span className="font-bold text-coral-700">3. The result.</span> Difference = option per month minus staying per month. A minus sign
            means the option is cheaper. A year is 12 months. List prices only: no enterprise discounts or taxes.
          </li>
        </ol>
      </div>

      {compared.length > 0 && (
        <div className="space-y-4 border-t border-sand-200 p-5">
          {compared.map((item) => {
            const versus = item.versus_baseline!;
            const baseline = baselines[item.csp];
            const delta = versus.delta_usd ?? 0;
            const cheaper = delta < 0;
            const percent = versus.baseline_core_usd ? Math.round((Math.abs(delta) / versus.baseline_core_usd) * 100) : null;
            return (
              <div key={`${item.rank}-${item.components[0].service_id}`} className="rounded-2xl border border-sand-200 p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="font-semibold text-slate-900">
                    <span className="text-xs font-bold uppercase tracking-wide text-slate-500">#{item.rank} · {CSP_LABELS[item.csp]} · </span>
                    {optionTitle(item)}
                  </p>
                  <p className={`text-2xl font-extrabold tabular-nums ${cheaper ? "text-emerald-700" : "text-rose-700"}`}>
                    {cheaper ? "−" : "+"}{formatMoney(Math.abs(delta), currency, inrPerUsd)}
                    <span className="text-sm font-semibold text-slate-500">
                      {" "}/ month{percent !== null ? ` (${cheaper ? "−" : "+"}${percent}%)` : ""} · {cheaper ? "saves" : "costs"} {formatMoney(Math.abs(delta) * 12, currency, inrPerUsd)} a year
                    </span>
                  </p>
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-[1fr_auto_1fr] md:items-stretch">
                  <CoreBreakdown
                    title={`Staying on ${engine}`} name={versus.baseline_service_name} tone="stay"
                    lines={baseline?.core_lines ?? []} multiplier={baseline?.environment_multiplier ?? 1} total={versus.baseline_core_usd ?? 0}
                    currency={currency} inrPerUsd={inrPerUsd}
                  />
                  <div className="grid place-items-center text-xl font-bold text-slate-400" aria-hidden="true">vs</div>
                  <CoreBreakdown
                    title="Moving to this option" name={optionTitle(item)} tone="move"
                    lines={versus.recommendation_core_lines ?? []} multiplier={versus.recommendation_environment_multiplier ?? 1} total={versus.recommendation_core_usd ?? 0}
                    currency={currency} inrPerUsd={inrPerUsd}
                  />
                </div>
                <p className="mt-2 text-xs text-slate-600">
                  {formatMoney(versus.recommendation_core_usd ?? 0, currency, inrPerUsd)} − {formatMoney(versus.baseline_core_usd ?? 0, currency, inrPerUsd)} ={" "}
                  <span className="font-semibold">{cheaper ? "−" : "+"}{formatMoney(Math.abs(delta), currency, inrPerUsd)}</span> a month.
                </p>
              </div>
            );
          })}
        </div>
      )}

      {(likeForLike.length > 0 || unpriced.length > 0) && (
        <ul className="space-y-1 border-t border-sand-200 px-5 py-3 text-xs text-slate-600">
          {likeForLike.map((item) => (
            <li key={`same-${item.rank}`}>#{item.rank} {optionTitle(item)} is staying on {engine} itself, so there is no difference to show.</li>
          ))}
          {unpriced.map((item) => (
            <li key={`unpriced-${item.rank}`}>#{item.rank} {optionTitle(item)}: {item.versus_baseline?.message}</li>
          ))}
        </ul>
      )}

      <div className="border-t border-sand-200 bg-white px-5 py-3 text-xs text-slate-500">
        <p className="font-semibold text-slate-700">How the "staying" price was found</p>
        <ul className="mt-1 space-y-1">
          {entries.map((baseline) => (
            <li key={baseline.csp}>
              <span className="font-semibold text-slate-700">{CSP_LABELS[baseline.csp]}:</span>{" "}
              {baseline.core_monthly_usd !== null ? `${formatMoney(baseline.core_monthly_usd, currency, inrPerUsd)} a month on ${baseline.service_name}. ` : ""}
              {baseline.note}
            </li>
          ))}
        </ul>
      </div>
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

function AboutService({ component }: { component: ServiceChoice }) {
  const about = component.about;
  if (!about) return null;
  return (
    <div className="space-y-3">
      <div>
        <p className="font-semibold text-slate-900">{about.title}</p>
        <p className="mt-1 text-slate-700">{about.summary}</p>
      </div>
      <div className="space-y-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">The cloud provider handles</p>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-slate-700">
            {about.provider_handles.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-coral-700">Your team handles</p>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-slate-700">
            {about.team_handles.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      </div>
      {about.facts.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{component.service_name}</p>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-slate-700">
            {about.facts.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      {about.source_url && (
        <a href={about.source_url} target="_blank" rel="noreferrer" className="link-underline text-xs font-semibold text-coral-700">
          Shared responsibility model
        </a>
      )}
    </div>
  );
}

function RecommendationCard({ recommendation, currency, inrPerUsd, planLink, onSetupGuide }: CardProps) {
  const primary = recommendation.components[0];
  const aboutTitle = primary.about?.deployment === "iaas" ? "About self-managed" : primary.about?.deployment === "serverless" ? "About this serverless service" : "About this managed service";
  return (
    <article className={`card card-hover flex flex-col p-5 ${recommendation.rank === 1 ? "border-t-4 border-t-coral-500" : ""}`}>
      <header className="flex items-start justify-between gap-2">
        <div>
          <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            #{recommendation.rank} · {CSP_LABELS[recommendation.csp]}
          </p>
          <h2 className="mt-1 font-semibold text-slate-900">
            {recommendation.components.map((component) => component.service_name).join(" + ")}
          </h2>
        </div>
        <span className="rounded-lg bg-coral-500 px-2 py-0.5 text-sm font-bold tabular-nums text-white shadow-glow">
          {recommendation.total_score.toFixed(1)}
        </span>
      </header>

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

      <div className="mt-4 space-y-2">
        {primary.about && (
          <Disclosure title={aboutTitle} hint={primary.about.title}>
            <AboutService component={primary} />
          </Disclosure>
        )}
        <Disclosure title="Why this" hint={`${recommendation.why.length} reasons`}>
          <ul className="list-disc space-y-1 pl-4 text-slate-700">
            {recommendation.why.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Disclosure>
        {recommendation.design_guidance.length > 0 && (
          <Disclosure title="Design notes" hint={`${recommendation.design_guidance.length} notes`}>
            <ul className="list-disc space-y-1 pl-4 text-slate-700">
              {recommendation.design_guidance.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </Disclosure>
        )}
      </div>
      {onSetupGuide && (recommendation.setup_guide ?? []).length > 0 && (
        <button type="button" onClick={onSetupGuide} className="btn-ghost mt-4 justify-center px-3 py-1.5 text-sm">
          Setup guide for this option
        </button>
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

function YourAnswers({ result, questions, sliders }: { result: AssessmentResult; questions: Map<string, Question>; sliders: PrioritySlider[] }) {
  const answered = Object.entries(result.input.answers).filter(([fieldId]) => questions.has(fieldId));
  const assumed = result.trace.assumed_fields;
  const priorities = sliders;
  return (
    <Disclosure title="Review your answers" hint={`${answered.length} answered · ${assumed.length} assumed · the inputs these recommendations are based on`}>
      <div className="space-y-4">
        <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
          {answered.map(([fieldId, value]) => (
            <div key={fieldId} className="flex justify-between gap-3 border-b border-sand-100 py-1.5">
              <span className="text-slate-500">{questions.get(fieldId)?.label}</span>
              <span className="text-right font-medium text-slate-800">{describeValue(questions.get(fieldId), value)}</span>
            </div>
          ))}
        </div>
        {priorities.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">What matters most</p>
            <div className="mt-1 flex flex-wrap gap-2">
              {priorities.map((slider) => (
                <span key={slider.id} className="rounded-full border border-sand-200 bg-sand-50 px-2.5 py-0.5 text-xs text-slate-700">
                  {slider.label} <span className="font-semibold tabular-nums">{result.input.priorities?.[slider.id] ?? slider.default}</span>
                </span>
              ))}
            </div>
          </div>
        )}
        {assumed.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Assumed ({assumed.length}): fields you left empty, filled from defaults</p>
            <ul className="mt-1 space-y-1 text-slate-700">
              {assumed.map((field) => (
                <li key={field.field_id}>
                  {questions.get(field.field_id)?.label ?? field.field_id}:{" "}
                  <span className="font-medium">{describeValue(questions.get(field.field_id), field.value)}</span>
                  <span className="text-xs text-slate-500"> ({field.reason})</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Disclosure>
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
  const [intake, setIntake] = useState<IntakeConfig | null>(null);
  const [guideRank, setGuideRank] = useState(1);

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

  const view: AssessmentResult | null = result;

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
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${currency === option ? "bg-coral-500 text-white shadow-soft" : "text-slate-600 hover:bg-sand-50"}`}
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

      {(view.notices ?? []).map((notice) => (
        <div key={notice} role="alert" className="rounded-2xl border-2 border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-semibold">Check your answers</p>
          <p className="mt-1">{notice}</p>
        </div>
      ))}

      <YourAnswers result={result} questions={questions} sliders={sliders} />

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


      {view.recommendations.length === 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          {view.trace.combination_notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
        </div>
      ) : (
        <div className="stagger grid items-start gap-5 lg:grid-cols-3">
          {view.recommendations.map((recommendation) => (
            <RecommendationCard
              key={`${optionTitle(recommendation)}|${recommendation.csp}`}
              recommendation={recommendation}
              currency={currency}
              inrPerUsd={result.pricing?.inr_per_usd ?? null}
              onSetupGuide={() => {
                setGuideRank(recommendation.rank);
                document.getElementById(SETUP_GUIDE_ID)?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
              planLink={isExisting ? `/migrations/new?assessment=${result.id}&target=${recommendation.components[0].service_id}` : undefined}
            />
          ))}
        </div>
      )}

      {!isExisting && view.recommendations.length > 0 && (
        <SetupGuide recommendations={view.recommendations} selectedRank={guideRank} onSelect={setGuideRank} />
      )}

      <AddOnsPanel result={view} intake={intake} />

      <ExplanationPanel assessmentId={result.id} />

      <WhyNotPanel filteredOut={view.trace.filtered_out} scores={view.trace.scores} recommendedIds={recommendedIds} />
    </div>
  );
}

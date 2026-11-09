import { useEffect, useMemo, useState } from "react";
import { PageLoader } from "../components/Loader";
import { Link, useParams } from "react-router-dom";
import { CSP_LABELS, ROLE_LABELS, fetchAssessment, type AssessmentResult, type Recommendation } from "../api/assessments";
import { describeValue, fetchQuestions, type Question } from "../api/questions";
import { useAuth } from "../auth/AuthProvider";
import { engineLabel } from "../api/labels";
import { COMMERCIAL_ENGINES } from "../api/requests";
import CostTiers, { type Currency } from "../components/CostTiers";
import ScoreRadar from "../components/ScoreRadar";
import WhyNotPanel from "../components/WhyNotPanel";

interface CardProps {
  recommendation: Recommendation;
  currency: Currency;
  inrPerUsd: number | null;
}

function RecommendationCard({ recommendation, currency, inrPerUsd }: CardProps) {
  return (
    <article className={`card card-hover flex flex-col p-5 ${recommendation.rank === 1 ? "border-t-4 border-t-coral-500" : ""}`}>
      <header className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
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

  useEffect(() => {
    fetchAssessment(id, getAccessToken)
      .then(setResult)
      .catch((loadError: Error) => setError(loadError.message));
    fetchQuestions("expert", getAccessToken)
      .then((schema) => {
        const index = new Map<string, Question>();
        schema.sections.forEach((section) => section.questions.forEach((question) => index.set(question.id, question)));
        setQuestions(index);
      })
      .catch(() => setQuestions(new Map()));
  }, [id, getAccessToken]);

  const recommendedIds = useMemo(() => {
    const ids = new Set<string>();
    result?.recommendations.forEach((recommendation) => recommendation.components.forEach((component) => ids.add(component.service_id)));
    return ids;
  }, [result]);

  if (error) {
    return <p className="text-rose-600">Could not load this assessment: {error}</p>;
  }
  if (!result) {
    return <PageLoader label="Loading recommendations" steps={["Fetching the assessment", "Laying out cost tiers", "Drawing score charts"]} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Recommendations</h1>
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
          <Link to="/assessments/new" className="btn-ghost px-3 py-1.5 hover:border-slate-500">
            New assessment
          </Link>
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

      {result.recommendations.length === 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          {result.trace.combination_notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
        </div>
      ) : (
        <div className="stagger grid gap-5 lg:grid-cols-3">
          {result.recommendations.map((recommendation) => (
            <RecommendationCard
              key={recommendation.rank}
              recommendation={recommendation}
              currency={currency}
              inrPerUsd={result.pricing?.inr_per_usd ?? null}
            />
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <WhyNotPanel filteredOut={result.trace.filtered_out} scores={result.trace.scores} recommendedIds={recommendedIds} />

        <section className="card p-4">
          <h2 className="font-medium text-slate-900">Assumptions ({result.trace.assumed_fields.length})</h2>
          <p className="mt-1 text-sm text-slate-600">Fields you left empty, filled from defaults.</p>
          <ul className="mt-3 space-y-1 text-sm text-slate-700">
            {result.trace.assumed_fields.map((field) => (
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

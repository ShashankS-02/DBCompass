import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CSP_LABELS, ROLE_LABELS, fetchAssessment, type AssessmentResult, type Recommendation } from "../api/assessments";
import { describeValue, fetchQuestions, type Question } from "../api/questions";
import { useAuth } from "../auth/AuthProvider";
import ScoreRadar from "../components/ScoreRadar";
import WhyNotPanel from "../components/WhyNotPanel";

function RecommendationCard({ recommendation }: { recommendation: Recommendation }) {
  return (
    <article className="flex flex-col rounded-lg border border-slate-200 bg-white p-4">
      <header className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            #{recommendation.rank} · {CSP_LABELS[recommendation.csp]}
          </p>
          <h2 className="mt-1 font-semibold text-slate-900">
            {recommendation.components.map((component) => component.service_name).join(" + ")}
          </h2>
        </div>
        <span className="rounded bg-slate-900 px-2 py-0.5 text-sm font-medium tabular-nums text-white">
          {recommendation.total_score.toFixed(1)}
        </span>
      </header>

      <ScoreRadar scores={recommendation.dimension_scores} />

      <dl className="space-y-2 text-sm">
        {recommendation.components.map((component) => (
          <div key={component.service_id} className="rounded bg-slate-50 p-2">
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
          <dt className="text-xs font-medium text-slate-500">Relative cost</dt>
          <dd className="text-slate-800">
            {recommendation.relative_cost_units} units{" "}
            <span className="text-xs text-slate-500">(comparison only; monthly prices arrive with pricing)</span>
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

export default function Results() {
  const { id = "" } = useParams();
  const { getAccessToken } = useAuth();
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [questions, setQuestions] = useState<Map<string, Question>>(new Map());
  const [error, setError] = useState<string | null>(null);

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
    return <p className="text-slate-500">Loading results…</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Recommendations</h1>
          <p className="mt-1 text-sm text-slate-600">
            {new Date(result.created_at).toLocaleString()} · engine {result.engine_version} · {result.trace.rules_fired.length} rules
            fired · {new Set(result.trace.filtered_out.map((reason) => reason.service_id)).size} services filtered out
          </p>
        </div>
        <Link to="/assessments/new" className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm hover:border-slate-500">
          New assessment
        </Link>
      </div>

      {result.recommendations.length === 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          {result.trace.combination_notes.map((note) => (
            <p key={note}>{note}</p>
          ))}
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {result.recommendations.map((recommendation) => (
            <RecommendationCard key={recommendation.rank} recommendation={recommendation} />
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <WhyNotPanel filteredOut={result.trace.filtered_out} scores={result.trace.scores} recommendedIds={recommendedIds} />

        <section className="rounded-lg border border-slate-200 bg-white p-4">
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

import { useEffect, useState, type FormEvent } from "react";
import { BusyOverlay, PageLoader, Spinner } from "../components/Loader";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { CSP_LABELS, fetchAssessment, fetchHistory, type AssessmentResult, type AssessmentSummary, type Recommendation } from "../api/assessments";
import { ApiError } from "../api/client";
import { createPlan, fetchPlan, type MigrationPlan, type MigrationPlanRequest, type StrategyOption } from "../api/migrations";
import { fetchQuestions, type Answers, type QuestionOption } from "../api/questions";
import { useAuth } from "../auth/AuthProvider";
import { clearDraft, readDraft, useDraft } from "../hooks/useDraft";
import PlanView from "../components/PlanView";

const inputClass = "w-full btn-ghost px-3 py-1.5 focus:border-slate-500 focus:outline-none";

interface FormState {
  assessmentId: string;
  sourceEngine: string;
  sourceVersion: string;
  platform: string;
  sizeGb: string;
  changeRate: string;
  downtime: string;
  bandwidth: string;
  charset: string;
  dependencies: string;
  teamSize: string;
  refactorLow: string;
  refactorHigh: string;
  target: string; // primary service id of the chosen recommendation; "" lets DBCompass pick per strategy
}

const PLAN_DRAFT_KEY = "dbcompass.migration-plan.draft.v1";

const EMPTY: FormState = {
  assessmentId: "", sourceEngine: "", sourceVersion: "", platform: "on_prem", sizeGb: "", changeRate: "", downtime: "", bandwidth: "",
  charset: "", dependencies: "", teamSize: "3", refactorLow: "", refactorHigh: "", target: "",
};
const AUTO_TARGET = "";

function optionName(recommendation: Recommendation): string {
  return recommendation.components.map((component) => component.service_name).join(" + ");
}

function balancedPrice(recommendation: Recommendation): string {
  const balanced = recommendation.cost_tiers.balanced;
  if (!balanced || !balanced.lines.length) return "not priced";
  return `$${Math.round(balanced.monthly_usd).toLocaleString("en-US")} / month${balanced.complete ? "" : "*"}`;
}

/** The assessment's recommendations as migration targets; the primary database is what gets planned. */
function TargetPicker({
  recommendations, value, onChange, busy,
}: { recommendations: Recommendation[]; value: string; onChange: (serviceId: string) => void; busy?: boolean }) {
  if (!recommendations.length) return null;
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4" role="radiogroup" aria-label="Migration target">
      {recommendations.map((recommendation) => {
        const serviceId = recommendation.components[0].service_id;
        const selected = value === serviceId;
        const delta = recommendation.versus_baseline?.delta_usd;
        return (
          <button
            key={`${serviceId}-${recommendation.rank}`}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={busy}
            onClick={() => onChange(serviceId)}
            className={`rounded-xl border p-3 text-left text-sm transition hover:-translate-y-0.5 hover:shadow-soft ${selected ? "border-coral-400 bg-coral-50/60 ring-2 ring-coral-100" : "border-sand-200 bg-white hover:border-coral-200"}`}
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">#{recommendation.rank} · {CSP_LABELS[recommendation.csp]}</p>
            <p className="font-semibold text-slate-900">{optionName(recommendation)}</p>
            <p className="text-xs text-slate-600">Score {recommendation.total_score.toFixed(1)} · {balancedPrice(recommendation)}</p>
            {typeof delta === "number" && !recommendation.versus_baseline?.same_service && (
              <p className={`mt-1 text-xs font-semibold ${delta < 0 ? "text-emerald-700" : "text-rose-700"}`}>
                {delta < 0 ? "−" : "+"}${Math.round(Math.abs(delta)).toLocaleString("en-US")} / month vs staying on {recommendation.versus_baseline?.engine_label}
              </p>
            )}
          </button>
        );
      })}
      <button
        type="button"
        role="radio"
        aria-checked={value === AUTO_TARGET}
        disabled={busy}
        onClick={() => onChange(AUTO_TARGET)}
        className={`rounded-xl border border-dashed p-3 text-left text-sm transition ${value === AUTO_TARGET ? "border-coral-400 bg-coral-50/60 ring-2 ring-coral-100" : "border-sand-300 bg-sand-50/60 hover:border-coral-200"}`}
      >
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Let DBCompass decide</p>
        <p className="font-semibold text-slate-900">Best strategy</p>
        <p className="text-xs text-slate-600">Compares rehost, replatform and refactor and plans the cheapest that meets the deadline.</p>
      </button>
    </div>
  );
}

function text(value: unknown): string {
  return value === undefined || value === null ? "" : String(value);
}

type EngineAnswer = { engine?: string; version?: string | null } | undefined;

/** The engine being migrated: the migration answer, else the app's existing database. */
function sourceOf(answers: Answers): EngineAnswer {
  for (const key of ["mig.source_engine", "app.existing_db"]) {
    const value = answers[key] as EngineAnswer;
    if (value?.engine && value.engine !== "none") return value;
  }
  return undefined;
}

function fromAnswers(assessmentId: string, answers: Answers, target: string): FormState {
  const source = sourceOf(answers);
  return {
    ...EMPTY,
    assessmentId,
    target,
    sourceEngine: source?.engine ?? "",
    sourceVersion: source?.version ?? "",
    platform: text(answers["mig.source_platform"]) || "on_prem",
    sizeGb: text(answers["mig.size_gb"] ?? answers["vol.current_gb"]),
    changeRate: text(answers["mig.change_rate_gb_day"]),
    downtime: text(answers["mig.downtime_minutes"]),
    bandwidth: text(answers["mig.bandwidth_mbps"]),
    charset: text(answers["mig.charset"]),
    dependencies: Array.isArray(answers["mig.dependencies"]) ? (answers["mig.dependencies"] as string[]).join(", ") : "",
  };
}

function numberOrSkip(answers: Answers, key: string, value: string) {
  if (value.trim() !== "" && !Number.isNaN(Number(value))) {
    answers[key] = Number(value);
  }
}

function toRequest(form: FormState, targetServiceId: string | null): MigrationPlanRequest {
  const answers: Answers = { "mig.source_platform": form.platform };
  if (form.sourceEngine) {
    answers["mig.source_engine"] = { engine: form.sourceEngine, version: form.sourceVersion.trim() || null };
  }
  numberOrSkip(answers, "mig.size_gb", form.sizeGb);
  numberOrSkip(answers, "mig.change_rate_gb_day", form.changeRate);
  numberOrSkip(answers, "mig.downtime_minutes", form.downtime);
  numberOrSkip(answers, "mig.bandwidth_mbps", form.bandwidth);
  if (form.charset.trim()) answers["mig.charset"] = form.charset.trim();
  const dependencies = form.dependencies.split(",").map((item) => item.trim()).filter(Boolean);
  if (dependencies.length) answers["mig.dependencies"] = dependencies;
  const low = Number(form.refactorLow);
  const high = Number(form.refactorHigh);
  const hasRange = form.refactorLow !== "" && form.refactorHigh !== "" && low >= 0 && high >= low;
  return {
    assessment_id: form.assessmentId,
    answers,
    target_service_id: targetServiceId,
    team_size: Number(form.teamSize) || null,
    refactor_person_days: hasRange ? [low, high] : null,
  };
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="text-slate-600">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

export default function MigrationPlanPage() {
  const { id } = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const { getAccessToken } = useAuth();
  const [plan, setPlan] = useState<MigrationPlan | null>(null);
  const [form, setForm] = useState<FormState>(() => (search.get("assessment") ? EMPTY : readDraft<FormState>(PLAN_DRAFT_KEY) ?? EMPTY));
  const [history, setHistory] = useState<AssessmentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [engines, setEngines] = useState<QuestionOption[]>([]);
  const [assessment, setAssessment] = useState<AssessmentResult | null>(null);
  useDraft(PLAN_DRAFT_KEY, form, !id);

  useEffect(() => {
    fetchQuestions("expert", getAccessToken)
      .then((schema) => {
        const question = schema.sections.flatMap((section) => section.questions).find((item) => item.id === "app.requested_engine");
        setEngines((question?.options ?? []).filter((option) => option.value !== "none"));
      })
      .catch(() => setEngines([]));
  }, [getAccessToken]);

  useEffect(() => {
    setError(null);
    if (id) {
      fetchPlan(id, getAccessToken)
        .then((loaded) => {
          setPlan(loaded);
          const assessmentId = loaded.request.assessment_id;
          if (assessmentId) fetchAssessment(assessmentId, getAccessToken).then(setAssessment).catch(() => setAssessment(null));
          else setAssessment(null);
        })
        .catch((loadError: Error) => setError(loadError.message));
      return;
    }
    setPlan(null);
    fetchHistory(getAccessToken).then(setHistory).catch(() => setHistory([]));
    const assessmentId = search.get("assessment");
    if (assessmentId) {
      fetchAssessment(assessmentId, getAccessToken)
        .then((loaded) => {
          setAssessment(loaded);
          const firstTarget = loaded.recommendations[0]?.components[0]?.service_id ?? AUTO_TARGET;
          setForm(fromAnswers(assessmentId, loaded.input.answers, search.get("target") ?? firstTarget));
        })
        .catch((loadError: Error) => setError(loadError.message));
    } else {
      setAssessment(null);
    }
  }, [id, search, getAccessToken]);

  const run = async (request: MigrationPlanRequest) => {
    setBusy(true);
    setError(null);
    try {
      const created = await createPlan(request, getAccessToken);
      clearDraft(PLAN_DRAFT_KEY);
      navigate(`/migrations/${created.id}`);
    } catch (caught) {
      setError(caught instanceof ApiError && caught.detail ? caught.detail : (caught as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const chooseTarget = (option: StrategyOption) => {
    if (plan) run({ ...plan.request, target_service_id: option.target_service_id, start_date: null });
  };
  const replanFor = (serviceId: string) => {
    if (plan && serviceId !== plan.target_service_id) run({ ...plan.request, target_service_id: serviceId || null, start_date: null });
  };

  if (id) {
    if (error) return <p className="text-rose-600">Could not load this plan: {error}</p>;
    if (!plan) return <PageLoader label="Loading migration plan" steps={["Fetching the plan", "Pricing strategies", "Building the runbook"]} />;
    const recommendations = assessment?.recommendations ?? [];
    return (
      <>
        {recommendations.length > 0 && (
          <section className="card mb-6 p-4">
            <p className="eyebrow">Recommendations from {(assessment?.input.answers["app.name"] as string | undefined) ?? "this assessment"}</p>
            <p className="mb-3 mt-1 text-sm text-slate-600">This plan targets {plan.target_name}. Pick another recommendation to plan its migration instead.</p>
            <TargetPicker recommendations={recommendations} value={plan.request.target_service_id ?? AUTO_TARGET} onChange={replanFor} busy={busy} />
          </section>
        )}
        <PlanView plan={plan} onChooseTarget={chooseTarget} />
        {busy && <BusyOverlay label="Re-planning the migration" steps={["Pricing the new target", "Checking the deadline", "Rebuilding the runbook"]} />}
      </>
    );
  }

  const set = (key: keyof FormState) => (event: { target: { value: string } }) => setForm({ ...form, [key]: event.target.value });
  const resetForm = () => {
    clearDraft(PLAN_DRAFT_KEY);
    setForm(EMPTY);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (form.assessmentId) run(toRequest(form, form.target || null));
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Plan a migration</h1>
        <p className="mt-1 text-sm text-slate-600">
          Pick an assessment of the application. DBCompass compares Rehost, Replatform and Refactor over three years
          (including database licences) and builds the method, tools, runbook, risks and rollback for the best one.
        </p>
      </div>
      <form onSubmit={submit} className="grid gap-4 card p-4 md:grid-cols-3">
        <div className="md:col-span-3">
          <Field label="Assessment">
            <select
              className={inputClass}
              value={form.assessmentId}
              onChange={(event) => {
                const assessmentId = event.target.value;
                setForm({ ...form, assessmentId });
                if (assessmentId) navigate(`/migrations/new?assessment=${assessmentId}`, { replace: true });
              }}
            >
              <option value="">Choose an assessment…</option>
              {form.assessmentId && !history.some((row) => row.id === form.assessmentId) && <option value={form.assessmentId}>{form.assessmentId}</option>}
              {history.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.app_name ?? "Unnamed application"} · {new Date(row.created_at).toLocaleDateString()} · {row.top_recommendation ?? "no recommendation"}
                </option>
              ))}
            </select>
          </Field>
        </div>
        {assessment && assessment.id === form.assessmentId && assessment.recommendations.length > 0 && (
          <div className="md:col-span-3">
            <p className="mb-2 text-sm text-slate-600">Migrate to which recommendation?</p>
            <TargetPicker recommendations={assessment.recommendations} value={form.target} onChange={(target) => setForm({ ...form, target })} busy={busy} />
          </div>
        )}
        <Field label="Source database engine (required)">
          <select className={inputClass} value={form.sourceEngine} onChange={set("sourceEngine")} aria-invalid={!form.sourceEngine}>
            <option value="">Choose the engine you are migrating from…</option>
            {engines.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Source version">
          <input className={inputClass} placeholder="e.g. 19c, 2019" value={form.sourceVersion} onChange={set("sourceVersion")} />
        </Field>
        <Field label="Source platform">
          <select className={inputClass} value={form.platform} onChange={set("platform")}>
            <option value="on_prem">On-prem</option>
            <option value="aws">AWS</option>
            <option value="gcp">GCP</option>
            <option value="azure">Azure</option>
          </select>
        </Field>
        <Field label="Database size (GB)"><input className={inputClass} type="number" min={0} value={form.sizeGb} onChange={set("sizeGb")} /></Field>
        <Field label="Change rate (GB / day)"><input className={inputClass} type="number" min={0} value={form.changeRate} onChange={set("changeRate")} /></Field>
        <Field label="Allowed downtime (minutes)"><input className={inputClass} type="number" min={0} value={form.downtime} onChange={set("downtime")} /></Field>
        <Field label="Bandwidth to the cloud (Mbps)"><input className={inputClass} type="number" min={0} value={form.bandwidth} onChange={set("bandwidth")} /></Field>
        <Field label="Character set"><input className={inputClass} placeholder="e.g. AL32UTF8" value={form.charset} onChange={set("charset")} /></Field>
        <div className="md:col-span-2">
          <Field label="Dependencies (comma separated: DB links, ETL jobs, consumers)">
            <input className={inputClass} value={form.dependencies} onChange={set("dependencies")} />
          </Field>
        </div>
        <Field label="Team size"><input className={inputClass} type="number" min={1} value={form.teamSize} onChange={set("teamSize")} /></Field>
        <Field label="Code refactor estimate, low (person-days)"><input className={inputClass} type="number" min={0} value={form.refactorLow} onChange={set("refactorLow")} /></Field>
        <Field label="Code refactor estimate, high (person-days)"><input className={inputClass} type="number" min={0} value={form.refactorHigh} onChange={set("refactorHigh")} /></Field>
        <div className="flex items-end">
          <button type="submit" disabled={busy || !form.assessmentId || !form.sourceEngine} className="w-full btn-primary">
            {busy ? <><Spinner /> Planning…</> : "Create plan"}
          </button>
        </div>
        <p className="text-xs text-slate-500 md:col-span-3">
          Your entries are kept in this browser until the plan is created.{" "}
          <button type="button" onClick={resetForm} className="link-underline font-semibold text-slate-500 hover:text-coral-700">Clear the form</button>
        </p>
        <p className="text-xs text-slate-500 md:col-span-3">
          Enter your team's code refactor estimate from a code review; leave it empty to use DBCompass's estimate from stored-procedure use.
        </p>
      </form>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {busy && <BusyOverlay label="Building the migration plan" steps={["Comparing rehost, replatform and refactor", "Estimating transfer time", "Choosing tools", "Writing the runbook", "Checking risks"]} />}
    </div>
  );
}

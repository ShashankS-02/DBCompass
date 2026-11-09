import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fetchAssessment, fetchHistory, type AssessmentSummary } from "../api/assessments";
import { ApiError } from "../api/client";
import { createPlan, fetchPlan, type MigrationPlan, type MigrationPlanRequest, type StrategyOption } from "../api/migrations";
import type { Answers } from "../api/questions";
import { useAuth } from "../auth/AuthProvider";
import PlanView from "../components/PlanView";

const inputClass = "w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none";

interface FormState {
  assessmentId: string;
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
}

const EMPTY: FormState = {
  assessmentId: "", platform: "on_prem", sizeGb: "", changeRate: "", downtime: "", bandwidth: "",
  charset: "", dependencies: "", teamSize: "3", refactorLow: "", refactorHigh: "",
};

function text(value: unknown): string {
  return value === undefined || value === null ? "" : String(value);
}

function fromAnswers(assessmentId: string, answers: Answers): FormState {
  return {
    ...EMPTY,
    assessmentId,
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
  const [form, setForm] = useState<FormState>(EMPTY);
  const [history, setHistory] = useState<AssessmentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setError(null);
    if (id) {
      fetchPlan(id, getAccessToken).then(setPlan).catch((loadError: Error) => setError(loadError.message));
      return;
    }
    setPlan(null);
    fetchHistory(getAccessToken).then(setHistory).catch(() => setHistory([]));
    const assessmentId = search.get("assessment");
    if (assessmentId) {
      fetchAssessment(assessmentId, getAccessToken)
        .then((assessment) => setForm(fromAnswers(assessmentId, assessment.input.answers)))
        .catch((loadError: Error) => setError(loadError.message));
    }
  }, [id, search, getAccessToken]);

  const run = async (request: MigrationPlanRequest) => {
    setBusy(true);
    setError(null);
    try {
      const created = await createPlan(request, getAccessToken);
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

  if (id) {
    if (error) return <p className="text-rose-600">Could not load this plan: {error}</p>;
    if (!plan) return <p className="text-slate-500">Loading plan…</p>;
    return (
      <>
        <PlanView plan={plan} onChooseTarget={chooseTarget} />
        {busy && <p className="mt-2 text-sm text-slate-500">Re-planning…</p>}
      </>
    );
  }

  const set = (key: keyof FormState) => (event: { target: { value: string } }) => setForm({ ...form, [key]: event.target.value });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (form.assessmentId) run(toRequest(form, null));
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Plan a migration</h1>
        <p className="mt-1 text-sm text-slate-600">
          Pick an assessment of the application. DBCompass compares Rehost, Replatform and Refactor over three years
          (including database licences) and builds the method, tools, runbook, risks and rollback for the best one.
        </p>
      </div>
      <form onSubmit={submit} className="grid gap-4 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-3">
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
                  {new Date(row.created_at).toLocaleString()} · {row.top_recommendation ?? "no recommendation"}
                </option>
              ))}
            </select>
          </Field>
        </div>
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
          <button type="submit" disabled={busy || !form.assessmentId} className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50">
            {busy ? "Planning…" : "Create plan"}
          </button>
        </div>
        <p className="text-xs text-slate-500 md:col-span-3">
          The repo analyzer's Oracle report gives a code refactor estimate; leave it empty to use DBCompass's estimate from stored-procedure use.
        </p>
      </form>
      {error && <p className="text-sm text-rose-600">{error}</p>}
    </div>
  );
}

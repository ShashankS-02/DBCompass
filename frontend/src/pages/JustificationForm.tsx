import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fetchHistory, type AssessmentSummary } from "../api/assessments";
import { ApiError } from "../api/client";
import { fetchQuestions, type QuestionOption } from "../api/questions";
import {
  COMMERCIAL_ENGINES,
  createRequest,
  fetchReasons,
  fetchRequest,
  previewJustification,
  updateRequest,
  type JustificationConfig,
  type JustificationEvaluation,
  type JustificationInput,
  type RequestKind,
} from "../api/requests";
import { useAuth } from "../auth/AuthProvider";
import VerdictPanel from "../components/VerdictPanel";

const inputClass = "w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none";
const PREVIEW_DELAY_MS = 500;

function emptyInput(search: URLSearchParams): JustificationInput {
  return {
    kind: (search.get("kind") as RequestKind) || "new_database",
    application_name: "",
    requested_engine: search.get("engine") || "oracle",
    assessment_id: search.get("assessment") || "",
    migration_plan_id: search.get("plan"),
    reasons: [],
    justification_text: "",
    alternatives_considered: "",
  };
}

function ReasonPicker({ config, input, onChange }: { config: JustificationConfig; input: JustificationInput; onChange: (next: JustificationInput) => void }) {
  const selected = new Map(input.reasons.map((reason) => [reason.reason_id, reason.evidence ?? ""]));
  const toggle = (reasonId: string) => {
    const reasons = selected.has(reasonId)
      ? input.reasons.filter((reason) => reason.reason_id !== reasonId)
      : [...input.reasons, { reason_id: reasonId, evidence: "" }];
    onChange({ ...input, reasons });
  };
  const setEvidence = (reasonId: string, evidence: string) =>
    onChange({ ...input, reasons: input.reasons.map((reason) => (reason.reason_id === reasonId ? { ...reason, evidence } : reason)) });

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium text-slate-900">Why this database?</legend>
      {Object.entries(config.reasons).map(([reasonId, spec]) => (
        <div key={reasonId} className="rounded border border-slate-100 p-2">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={selected.has(reasonId)} onChange={() => toggle(reasonId)} />
            <span>{spec.label}</span>
          </label>
          {selected.has(reasonId) && spec.evidence_prompt && (
            <input
              className={`${inputClass} mt-2`}
              placeholder={spec.evidence_prompt}
              value={selected.get(reasonId)}
              onChange={(event) => setEvidence(reasonId, event.target.value)}
            />
          )}
        </div>
      ))}
    </fieldset>
  );
}

export default function JustificationForm() {
  const { id } = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const { getAccessToken } = useAuth();
  const [input, setInput] = useState<JustificationInput>(() => emptyInput(search));
  const [config, setConfig] = useState<JustificationConfig | null>(null);
  const [engines, setEngines] = useState<QuestionOption[]>([]);
  const [history, setHistory] = useState<AssessmentSummary[]>([]);
  const [evaluation, setEvaluation] = useState<JustificationEvaluation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchReasons(getAccessToken).then(setConfig).catch((loadError: Error) => setError(loadError.message));
    fetchHistory(getAccessToken).then(setHistory).catch(() => setHistory([]));
    fetchQuestions("expert", getAccessToken)
      .then((schema) => {
        const question = schema.sections.flatMap((section) => section.questions).find((item) => item.id === "app.requested_engine");
        setEngines((question?.options ?? []).filter((option) => option.value !== "none"));
      })
      .catch(() => setEngines([]));
    if (id) {
      fetchRequest(id, getAccessToken).then((request) => setInput(request.input)).catch((loadError: Error) => setError(loadError.message));
    }
  }, [id, getAccessToken]);

  useEffect(() => {
    if (!input.assessment_id) return;
    const timer = window.setTimeout(() => {
      // The preview needs a name to validate; the real save still requires one.
      const draft = { ...input, application_name: input.application_name.trim() || "Unnamed application" };
      previewJustification(draft, getAccessToken)
        .then((result) => {
          setEvaluation(result);
          setError(null);
        })
        .catch((caught) => setError(caught instanceof ApiError && caught.detail ? caught.detail : (caught as Error).message));
    }, PREVIEW_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [input, getAccessToken]);

  const licensed = useMemo(() => COMMERCIAL_ENGINES.includes(input.requested_engine), [input.requested_engine]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const saved = id ? await updateRequest(id, input, getAccessToken) : await createRequest(input, getAccessToken);
      navigate(`/requests/${saved.id}`);
    } catch (caught) {
      setError(caught instanceof ApiError && caught.detail ? caught.detail : (caught as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const set = (patch: Partial<JustificationInput>) => setInput({ ...input, ...patch });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{id ? "Edit database request" : "New database request"}</h1>
        <p className="mt-1 text-sm text-slate-600">
          Commercially licensed engines (Oracle, SQL Server, Db2) need a reason before they are approved. DBCompass checks
          what it can against the assessment and shows what a licence-free option would cost.
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
          <label className="block text-sm">
            <span className="text-slate-600">Application</span>
            <input className={`${inputClass} mt-1`} value={input.application_name} onChange={(event) => set({ application_name: event.target.value })} />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-slate-600">Request type</span>
              <select className={`${inputClass} mt-1`} value={input.kind} onChange={(event) => set({ kind: event.target.value as RequestKind })}>
                <option value="new_database">New database</option>
                <option value="migration">Migration (keep the current engine)</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-slate-600">Requested engine</span>
              <select className={`${inputClass} mt-1`} value={input.requested_engine} onChange={(event) => set({ requested_engine: event.target.value })}>
                {engines.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="block text-sm">
            <span className="text-slate-600">Assessment of this application</span>
            <select className={`${inputClass} mt-1`} value={input.assessment_id} onChange={(event) => set({ assessment_id: event.target.value })}>
              <option value="">Choose an assessment…</option>
              {input.assessment_id && !history.some((row) => row.id === input.assessment_id) && <option value={input.assessment_id}>{input.assessment_id}</option>}
              {history.map((row) => (
                <option key={row.id} value={row.id}>
                  {new Date(row.created_at).toLocaleString()} · {row.top_recommendation ?? "no recommendation"}
                </option>
              ))}
            </select>
          </label>
          {licensed && config && <ReasonPicker config={config} input={input} onChange={setInput} />}
          {licensed && (
            <>
              <label className="block text-sm">
                <span className="text-slate-600">Justification ({input.justification_text.trim().length}/{config?.min_justification_chars ?? 0}+ characters)</span>
                <textarea className={`${inputClass} mt-1`} rows={4} value={input.justification_text} onChange={(event) => set({ justification_text: event.target.value })} />
              </label>
              <label className="block text-sm">
                <span className="text-slate-600">Alternatives considered</span>
                <textarea className={`${inputClass} mt-1`} rows={2} value={input.alternatives_considered} onChange={(event) => set({ alternatives_considered: event.target.value })} />
              </label>
            </>
          )}
          <button
            type="button"
            onClick={save}
            disabled={busy || !input.assessment_id || !input.application_name.trim()}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save draft"}
          </button>
          {error && <p className="text-sm text-rose-600">{error}</p>}
        </div>
        <div>{evaluation ? <VerdictPanel evaluation={evaluation} /> : <p className="text-sm text-slate-500">Choose an assessment to see the verdict.</p>}</div>
      </div>
    </div>
  );
}

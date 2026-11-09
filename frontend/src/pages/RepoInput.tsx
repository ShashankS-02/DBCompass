import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { describeValue, fetchQuestions, type Question } from "../api/questions";
import { analyzeRepo, listSamples, type InferredRequirements, type RepoPrefill } from "../api/repo";
import { useAuth } from "../auth/AuthProvider";
import { BusyOverlay, Spinner } from "../components/Loader";

const SOURCE_LABELS: Record<string, string> = { static: "code", readme: "README", llm: "LLM" };
const inputClass = "w-full btn-ghost px-3 py-1.5 focus:border-slate-500 focus:outline-none";

function ConfidenceBar({ value }: { value: number }) {
  const colour = value >= 0.75 ? "bg-emerald-500" : value >= 0.5 ? "bg-amber-400" : "bg-slate-300";
  return (
    <div className="flex items-center gap-2" title={`Confidence ${Math.round(value * 100)}%`}>
      <div className="h-1.5 w-16 rounded bg-slate-100">
        <div className={`h-1.5 rounded ${colour}`} style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="text-xs tabular-nums text-slate-500">{Math.round(value * 100)}%</span>
    </div>
  );
}

function OracleReportView({ report }: { report: NonNullable<InferredRequirements["oracle_report"]> }) {
  return (
    <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
      <h2 className="font-medium text-amber-950">Oracle → PostgreSQL compatibility</h2>
      <p className="mt-1 text-sm text-amber-900">{report.summary}</p>
      <table className="mt-3 w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-amber-800">
            <th className="py-1">Feature</th>
            <th className="px-3 py-1 text-right">Count</th>
            <th className="px-3 py-1">Effort</th>
            <th className="py-1 text-right">Person-days</th>
          </tr>
        </thead>
        <tbody>
          {report.features.map((feature) => (
            <tr key={feature.feature} className="border-t border-amber-200 align-top" title={feature.evidence.join("\n")}>
              <td className="py-1">{feature.label}</td>
              <td className="px-3 py-1 text-right tabular-nums">{feature.count}</td>
              <td className="px-3 py-1">{feature.effort.replace(/_/g, "–")}</td>
              <td className="py-1 text-right tabular-nums">
                {feature.person_days_low}–{feature.person_days_high}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function RepoInput() {
  const { getAccessToken } = useAuth();
  const navigate = useNavigate();
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [token, setToken] = useState("");
  const [samples, setSamples] = useState<string[]>([]);
  const [questions, setQuestions] = useState<Map<string, Question>>(new Map());
  const [result, setResult] = useState<InferredRequirements | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listSamples(getAccessToken).then(setSamples).catch(() => setSamples([]));
    fetchQuestions("expert", getAccessToken)
      .then((schema) => {
        const index = new Map<string, Question>();
        schema.sections.forEach((section) => section.questions.forEach((question) => index.set(question.id, question)));
        setQuestions(index);
      })
      .catch(() => setQuestions(new Map()));
  }, [getAccessToken]);

  const run = async (url: string) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body = { repo_url: url, ...(branch ? { branch } : {}), ...(token ? { token } : {}) };
      setResult(await analyzeRepo(body, getAccessToken));
      setToken(""); // never kept around after use
    } catch (caught) {
      setError(caught instanceof ApiError && caught.status === 400 ? "That repository could not be analysed (check the URL, branch or token)." : (caught as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const rows = useMemo(() => {
    if (!result) return [];
    return Object.entries(result.fields).sort(([a], [b]) => {
      const quickA = questions.get(a)?.quick ? 0 : 1;
      const quickB = questions.get(b)?.quick ? 0 : 1;
      return quickA - quickB || a.localeCompare(b);
    });
  }, [result, questions]);

  const useAnswers = () => {
    if (!result) return;
    const evidence: RepoPrefill["evidence"] = {};
    for (const fieldId of Object.keys(result.prefill)) {
      evidence[fieldId] = { confidence: result.fields[fieldId].confidence, evidence: result.fields[fieldId].evidence };
    }
    const prefill: RepoPrefill = { answers: result.prefill, evidence, repoUrl: result.repo_url };
    navigate("/assessments/new", { state: { repoPrefill: prefill } });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Analyze a repository</h1>
        <p className="mt-1 text-sm text-slate-600">
          DBCompass reads the code (it never runs it), masks secrets, and pre-fills the requirements form with evidence. Private
          repos need a token; it is used once and never stored.
        </p>
      </div>

      {busy && <BusyOverlay label="Analysing the repository" steps={["Fetching the file tree", "Reading drivers and ORMs", "Scanning schema and SQL", "Redacting secrets", "Asking the model for signals", "Pre-filling the form"]} />}
      <form
        className="grid gap-3 card p-4 sm:grid-cols-[minmax(0,1fr)_160px_200px_auto]"
        onSubmit={(event) => {
          event.preventDefault();
          if (repoUrl.trim()) run(repoUrl.trim());
        }}
      >
        <input className={inputClass} placeholder="https://github.com/owner/repo" value={repoUrl} onChange={(event) => setRepoUrl(event.target.value)} aria-label="Repository URL" />
        <input className={inputClass} placeholder="Branch (optional)" value={branch} onChange={(event) => setBranch(event.target.value)} aria-label="Branch" />
        <input className={inputClass} type="password" autoComplete="off" placeholder="Token (private repos)" value={token} onChange={(event) => setToken(event.target.value)} aria-label="GitHub token" />
        <button type="submit" disabled={busy || !repoUrl.trim()} className="btn-primary">
          {busy ? <><Spinner /> Analysing…</> : "Analyze"}
        </button>
      </form>

      {samples.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-slate-500">Or try a demo repo:</span>
          {samples.map((sample) => (
            <button key={sample} type="button" disabled={busy} onClick={() => run(`sample:${sample}`)} className="rounded-full border border-sand-200 bg-white px-3 py-1 font-medium text-slate-700 shadow-soft transition hover:-translate-y-0.5 hover:border-coral-300 hover:text-coral-700 disabled:opacity-50">
              {sample}
            </button>
          ))}
        </div>
      )}

      {error && <p className="text-sm text-rose-600">{error}</p>}

      {result && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="text-sm text-slate-600">
              <span className="font-medium text-slate-900">{result.repo_url}</span>
              {result.commit_sha && <span> @ {result.commit_sha.slice(0, 12)}</span>} · {result.summary.files_scanned} files read ·{" "}
              {Object.keys(result.prefill).length} answers ready
              {result.warnings.map((warning) => (
                <p key={warning} className="text-xs text-slate-500">{warning}</p>
              ))}
            </div>
            <button type="button" onClick={useAnswers} className="btn-primary">
              Use these answers →
            </button>
          </div>

          {result.summary.detected.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {result.summary.detected.map((item) => (
                <span key={item} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700">{item}</span>
              ))}
            </div>
          )}

          {result.oracle_report && <OracleReportView report={result.oracle_report} />}

          <section className="overflow-x-auto card">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500">
                  <th className="px-3 py-2">Requirement</th>
                  <th className="px-3 py-2">Inferred value</th>
                  <th className="px-3 py-2">Confidence</th>
                  <th className="px-3 py-2">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([fieldId, field]) => {
                  const question = questions.get(fieldId);
                  const used = fieldId in result.prefill;
                  return (
                    <tr key={fieldId} className={`border-t border-slate-100 align-top ${used ? "" : "text-slate-400"}`}>
                      <td className="px-3 py-2">
                        {question?.label ?? fieldId}
                        {question?.quick && <span className="ml-1 rounded bg-slate-100 px-1 text-[10px] text-slate-500">Quick</span>}
                      </td>
                      <td className="px-3 py-2 font-medium">{field.value == null ? "—" : describeValue(question, field.value)}</td>
                      <td className="px-3 py-2">
                        <ConfidenceBar value={field.confidence} />
                        {field.source && <span className="text-[11px] text-slate-500">from {SOURCE_LABELS[field.source]}</span>}
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {field.hint && <p className="text-slate-500">{field.hint}</p>}
                        {field.evidence.slice(0, 3).map((item) => (
                          <p key={item} className="break-all font-mono text-[11px] text-slate-600">{item}</p>
                        ))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </div>
  );
}

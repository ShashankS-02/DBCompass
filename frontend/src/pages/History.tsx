import { useEffect, useState } from "react";
import { PageLoader } from "../components/Loader";
import { Link } from "react-router-dom";
import { CSP_LABELS, fetchHistory, type AssessmentSummary } from "../api/assessments";
import { useAuth } from "../auth/AuthProvider";

export default function History() {
  const { getAccessToken } = useAuth();
  const [rows, setRows] = useState<AssessmentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHistory(getAccessToken)
      .then(setRows)
      .catch((loadError: Error) => setError(loadError.message));
  }, [getAccessToken]);

  if (error) {
    return <p className="text-rose-600">Could not load history: {error}</p>;
  }
  if (!rows) {
    return <PageLoader label="Loading history" steps={["Fetching your assessments", "Sorting by date"]} />;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold text-slate-900">History</h1>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-600">
          No assessments yet.{" "}
          <Link to="/assessments/new" className="underline">
            Start one
          </Link>
          .
        </p>
      ) : (
        <ul className="stagger divide-y divide-sand-100 card overflow-hidden">
          {rows.map((row) => (
            <li key={row.id}>
              <Link to={`/assessments/${row.id}`} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3 transition-all duration-200 hover:bg-sand-50 hover:pl-5">
                <span className="text-sm tabular-nums text-slate-500">{new Date(row.created_at).toLocaleString()}</span>
                <span className="text-sm text-slate-500">{row.app_type ?? "unspecified app type"}</span>
                <span className="text-sm font-medium text-slate-900">{row.top_recommendation ?? "No recommendation"}</span>
                {row.top_csp && <span className="text-xs text-slate-500">{CSP_LABELS[row.top_csp]}</span>}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

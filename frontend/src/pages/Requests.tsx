import { useEffect, useState } from "react";
import { PageLoader } from "../components/Loader";
import { Link } from "react-router-dom";
import { listRequests, STATUS_LABELS, type DbRequestSummary } from "../api/requests";
import { engineLabel } from "../api/labels";
import { useAuth } from "../auth/AuthProvider";
import { useMe } from "../auth/useMe";
import { VerdictBadge } from "../components/VerdictPanel";

type Scope = "mine" | "review" | "all";

const SCOPE_LABELS: Record<Scope, string> = { mine: "My requests", review: "Awaiting my approval", all: "All requests" };

export default function Requests() {
  const { getAccessToken } = useAuth();
  const me = useMe();
  const isApprover = me?.roles.includes("db_approver") ?? false;
  const [scope, setScope] = useState<Scope>("mine");
  const [rows, setRows] = useState<DbRequestSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRows(null);
    listRequests(scope, getAccessToken).then(setRows).catch((loadError: Error) => setError(loadError.message));
  }, [scope, getAccessToken]);

  const scopes: Scope[] = isApprover ? ["mine", "review", "all"] : ["mine"];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-3xl font-bold text-slate-900">Database requests</h1>
        <Link to="/requests/new" className="btn-primary">
          New request
        </Link>
      </div>
      <div className="inline-flex rounded-xl border border-sand-200 bg-white p-1 shadow-soft" role="tablist">
        {scopes.map((option) => (
          <button
            key={option}
            type="button"
            role="tab"
            aria-selected={scope === option}
            onClick={() => setScope(option)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${scope === option ? "bg-coral-500 text-white shadow-soft" : "text-slate-600 hover:bg-sand-50 hover:text-slate-900"}`}
          >
            {SCOPE_LABELS[option]}
          </button>
        ))}
      </div>
      {error && <p className="text-rose-600">{error}</p>}
      {!rows && !error && <PageLoader label="Loading requests" steps={["Fetching requests", "Checking verdicts"]} />}
      {rows && rows.length === 0 && <p className="text-sm text-slate-600">Nothing here yet.</p>}
      {rows && rows.length > 0 && (
        <ul className="stagger divide-y divide-sand-100 card overflow-hidden">
          {rows.map((row) => (
            <li key={row.id}>
              <Link to={`/requests/${row.id}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 transition-all duration-200 hover:bg-sand-50 hover:pl-5">
                <span className="font-medium text-slate-900">{row.application_name}</span>
                <span className="text-sm text-slate-500">{row.kind === "migration" ? "Migration" : "New database"} · {engineLabel(row.requested_engine)}</span>
                <VerdictBadge verdict={row.verdict} />
                <span className="text-sm text-slate-700">{STATUS_LABELS[row.status]}</span>
                <span className="ml-auto text-xs text-slate-500">{row.created_by_name} · {new Date(row.updated_at).toLocaleString()}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

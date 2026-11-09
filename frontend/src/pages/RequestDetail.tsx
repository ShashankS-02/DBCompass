import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { decideRequest, exportRequest, fetchRequest, STATUS_LABELS, submitRequest, type DbRequest } from "../api/requests";
import { engineLabel } from "../api/labels";
import { useAuth } from "../auth/AuthProvider";
import { useMe } from "../auth/useMe";
import VerdictPanel from "../components/VerdictPanel";

const EDITABLE = ["draft", "sent_back"];

function download(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/markdown" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function DecisionBox({ onDecide, busy }: { onDecide: (decision: "approve" | "reject" | "send_back", note: string) => void; busy: boolean }) {
  const [note, setNote] = useState("");
  return (
    <section className="space-y-2 rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="font-medium text-slate-900">Your decision</h2>
      <textarea
        className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        rows={3}
        placeholder="Note (required to reject, send back, or approve against the verdict)"
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={busy} onClick={() => onDecide("approve", note)} className="rounded-md bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">Approve</button>
        <button type="button" disabled={busy} onClick={() => onDecide("send_back", note)} className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm disabled:opacity-50">Send back</button>
        <button type="button" disabled={busy} onClick={() => onDecide("reject", note)} className="rounded-md bg-rose-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">Reject</button>
      </div>
    </section>
  );
}

export default function RequestDetail() {
  const { id = "" } = useParams();
  const { getAccessToken } = useAuth();
  const me = useMe();
  const [request, setRequest] = useState<DbRequest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchRequest(id, getAccessToken).then(setRequest).catch((loadError: Error) => setError(loadError.message));
  }, [id, getAccessToken]);

  const act = async (action: () => Promise<DbRequest>) => {
    setBusy(true);
    setError(null);
    try {
      setRequest(await action());
    } catch (caught) {
      setError(caught instanceof ApiError && caught.detail ? caught.detail : (caught as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!request) {
    return error ? <p className="text-rose-600">{error}</p> : <p className="text-slate-500">Loading…</p>;
  }

  const isOwner = me?.user_id === request.created_by;
  const canDecide = (me?.roles.includes("db_approver") ?? false) && request.status === "submitted" && (!isOwner || me?.auth_mode === "dev_bypass");
  const data = request.input;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{data.application_name}</h1>
          <p className="mt-1 text-sm text-slate-600">
            {data.kind === "migration" ? "Migration" : "New database"} · requested engine <span className="font-medium">{engineLabel(data.requested_engine)}</span> ·{" "}
            {STATUS_LABELS[request.status]} · raised by {request.created_by_name}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {isOwner && EDITABLE.includes(request.status) && (
            <>
              <Link to={`/requests/${request.id}/edit`} className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm">Edit</Link>
              <button type="button" disabled={busy} onClick={() => act(() => submitRequest(request.id, getAccessToken))} className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">
                Submit for approval
              </button>
            </>
          )}
          <button type="button" onClick={() => exportRequest(request.id, getAccessToken).then((text) => download(`db-request-${request.id.slice(0, 8)}.md`, text))} className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm">
            Export Markdown
          </button>
          <Link to={`/assessments/${data.assessment_id}`} className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm">Assessment</Link>
          {data.migration_plan_id && <Link to={`/migrations/${data.migration_plan_id}`} className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm">Migration plan</Link>}
        </div>
      </div>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <section className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm">
            <div>
              <h2 className="font-medium text-slate-900">Justification</h2>
              <p className="mt-1 whitespace-pre-wrap text-slate-700">{data.justification_text || "—"}</p>
            </div>
            <div>
              <h2 className="font-medium text-slate-900">Alternatives considered</h2>
              <p className="mt-1 whitespace-pre-wrap text-slate-700">{data.alternatives_considered || "—"}</p>
            </div>
            {data.reasons.some((reason) => reason.evidence) && (
              <div>
                <h2 className="font-medium text-slate-900">Evidence</h2>
                <ul className="mt-1 list-disc pl-5 text-slate-700">
                  {data.reasons.filter((reason) => reason.evidence).map((reason) => (
                    <li key={reason.reason_id} className="break-all">{reason.evidence}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
          {canDecide && <DecisionBox busy={busy} onDecide={(decision, note) => act(() => decideRequest(request.id, decision, note, getAccessToken))} />}
          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="font-medium text-slate-900">Audit trail</h2>
            <ol className="mt-2 space-y-1 text-sm">
              {request.events.map((event, index) => (
                <li key={index} className="text-slate-700">
                  <span className="text-xs text-slate-500">{new Date(event.at).toLocaleString()}</span> · {event.actor_name} {event.action.replace("_", " ")}
                  {event.note && <span className="text-slate-600">: {event.note}</span>}
                </li>
              ))}
            </ol>
          </section>
        </div>
        <VerdictPanel evaluation={request.evaluation} />
      </div>
    </div>
  );
}

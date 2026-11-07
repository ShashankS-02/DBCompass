import { useEffect, useState } from "react";
import { apiGet, type CurrentUser, type HealthResponse } from "../api/client";
import { useAuth } from "../auth/AuthProvider";

type LoadState<T> = { status: "loading" } | { status: "ok"; data: T } | { status: "error"; message: string };

function useApiResource<T>(path: string): LoadState<T> {
  const { getAccessToken, isAuthenticated } = useAuth();
  const [state, setState] = useState<LoadState<T>>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    apiGet<T>(path, getAccessToken)
      .then((data) => !cancelled && setState({ status: "ok", data }))
      .catch((error: Error) => !cancelled && setState({ status: "error", message: error.message }));
    return () => {
      cancelled = true;
    };
  }, [path, getAccessToken, isAuthenticated]);

  return state;
}

function StatusRow<T>({ label, state, render }: { label: string; state: LoadState<T>; render: (data: T) => string }) {
  let text = "Checking…";
  let colour = "bg-slate-300";
  if (state.status === "ok") {
    text = render(state.data);
    colour = "bg-emerald-500";
  } else if (state.status === "error") {
    text = state.message;
    colour = "bg-rose-500";
  }

  return (
    <div className="flex items-center gap-3 py-2">
      <span className={`h-2.5 w-2.5 rounded-full ${colour}`} />
      <span className="w-24 text-sm font-medium text-slate-600">{label}</span>
      <span className="text-sm text-slate-900">{text}</span>
    </div>
  );
}

export default function Home() {
  const health = useApiResource<HealthResponse>("/health");
  const me = useApiResource<CurrentUser>("/me");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">DBCompass</h1>
        <p className="mt-1 text-slate-600">
          Pick the right database, cloud and design for your application, and plan the migration.
        </p>
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">System status</h2>
        <StatusRow
          label="Backend"
          state={health}
          render={(data) => `v${data.version}, database ${data.database}`}
        />
        <StatusRow
          label="Signed in"
          state={me}
          render={(data) => `${data.name} (${data.auth_mode})`}
        />
      </section>
    </div>
  );
}

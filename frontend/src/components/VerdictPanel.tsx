import { CSP_LABELS } from "../api/assessments";
import { engineLabel } from "../api/labels";
import { VERDICT_STYLES, type CostedOption, type JustificationEvaluation } from "../api/requests";

const STATUS_STYLES: Record<string, string> = {
  verified: "text-emerald-700",
  evidenced: "text-sky-700",
  claimed: "text-slate-500",
  contradicted: "text-rose-700",
};

function usd(value: number | null): string {
  return value == null ? "n/a" : `$${Math.round(value).toLocaleString("en-US")}`;
}

export function VerdictBadge({ verdict }: { verdict: JustificationEvaluation["verdict"] }) {
  const style = VERDICT_STYLES[verdict];
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${style.className}`}>{style.label}</span>;
}

function OptionColumn({ title, option, months }: { title: string; option: CostedOption | null; months: number }) {
  if (!option) {
    return (
      <div className="rounded bg-slate-50 p-3 text-sm text-slate-500">
        <p className="text-xs font-medium uppercase tracking-wide">{title}</p>
        <p className="mt-1">No option passed the filters.</p>
      </div>
    );
  }
  return (
    <div className="rounded bg-slate-50 p-3 text-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-1 font-medium text-slate-900">{option.service_name}</p>
      <p className="text-xs text-slate-500">{CSP_LABELS[option.csp]} · {engineLabel(option.engine)}</p>
      <p className="mt-2 tabular-nums">{usd(option.monthly_usd)}{!option.cost_complete && "*"} / month</p>
      {option.licence_monthly_usd > 0 && <p className="text-xs text-rose-700">incl. {usd(option.licence_monthly_usd)} licence</p>}
      <p className="mt-1 text-xs text-slate-500">{usd(option.period_cost_usd)} over {months} months</p>
    </div>
  );
}

export default function VerdictPanel({ evaluation }: { evaluation: JustificationEvaluation }) {
  return (
    <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-medium text-slate-900">DBCompass verdict (advisory)</h2>
        <VerdictBadge verdict={evaluation.verdict} />
      </div>
      {evaluation.applies && (
        <>
          <ul className="space-y-1 text-sm">
            {evaluation.reasons.map((reason) => (
              <li key={reason.reason_id} className="flex justify-between gap-3">
                <span>
                  {reason.label}
                  <span className={`ml-2 text-xs ${STATUS_STYLES[reason.status]}`}>{reason.status}</span>
                  <span className="block text-xs text-slate-500">{reason.note}</span>
                </span>
                <span className="tabular-nums text-slate-600">{reason.points}</span>
              </li>
            ))}
            <li className="flex justify-between border-t border-slate-100 pt-1 font-medium">
              <span>Points</span>
              <span className="tabular-nums">{evaluation.points}</span>
            </li>
          </ul>
          <div className="grid gap-3 sm:grid-cols-2">
            <OptionColumn title="Requested" option={evaluation.requested_option} months={evaluation.months_compared} />
            <OptionColumn title="Best licence-free" option={evaluation.alternative_option} months={evaluation.months_compared} />
          </div>
          <dl className="grid grid-cols-3 gap-2 text-sm">
            <div>
              <dt className="text-xs text-slate-500">Refactor cost</dt>
              <dd className="tabular-nums">{usd(evaluation.refactor_cost_usd)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Net saving if licence-free</dt>
              <dd className={`font-medium tabular-nums ${(evaluation.period_saving_usd ?? 0) > 0 ? "text-emerald-700" : ""}`}>
                {usd(evaluation.period_saving_usd)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Break-even</dt>
              <dd className="tabular-nums">{evaluation.break_even_months == null ? "n/a" : `${evaluation.break_even_months} months`}</dd>
            </div>
          </dl>
        </>
      )}
      <ul className="list-disc space-y-1 pl-4 text-sm text-slate-700">
        {evaluation.messages.map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
      {evaluation.problems.length > 0 && (
        <ul className="list-disc space-y-1 rounded bg-amber-50 p-2 pl-6 text-sm text-amber-900">
          {evaluation.problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
      <p className="text-xs text-slate-500">
        List prices; licences use the org discount in licensing.yaml. A database approver makes the decision.
      </p>
    </section>
  );
}

import { Link } from "react-router-dom";
import { CSP_LABELS } from "../api/assessments";
import type { MigrationPlan, StrategyOption, ToolRef } from "../api/migrations";
import { engineLabel, PLATFORM_LABELS } from "../api/labels";
import { COMMERCIAL_ENGINES } from "../api/requests";

const RISK_STYLES: Record<string, string> = {
  high: "bg-rose-100 text-rose-800",
  medium: "bg-amber-100 text-amber-900",
  low: "bg-emerald-100 text-emerald-800",
};

function usd(value: number): string {
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function Badge({ ok, yes, no }: { ok: boolean; yes: string; no: string }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${ok ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>
      {ok ? yes : no}
    </span>
  );
}

function StrategyTable({ plan, onChooseTarget }: { plan: MigrationPlan; onChooseTarget?: (option: StrategyOption) => void }) {
  return (
    <section className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <h2 className="px-4 pt-4 font-medium text-slate-900">Strategies compared (3-year view, list prices incl. licences)</h2>
      <table className="mt-2 w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-slate-500">
            <th className="px-4 py-2">Strategy</th>
            <th className="px-3 py-2">Target</th>
            <th className="px-3 py-2 text-right">Monthly</th>
            <th className="px-3 py-2 text-right">One-off effort</th>
            <th className="px-3 py-2 text-right">3-year total</th>
            <th className="px-3 py-2">Finish</th>
            <th className="px-3 py-2">Risk</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {plan.strategies.map((option) => (
            <tr key={option.strategy} className={`border-t border-slate-100 align-top ${option.strategy === plan.strategy ? "bg-slate-50" : ""}`}>
              <td className="px-4 py-2 font-medium">
                {option.label}
                {option.recommended && <span className="ml-2 rounded bg-slate-900 px-1.5 py-0.5 text-[10px] text-white">Recommended</span>}
              </td>
              <td className="px-3 py-2">
                {option.target_name}
                <div className="text-xs text-slate-500">{CSP_LABELS[option.csp]} · {engineLabel(option.engine)}</div>
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {usd(option.monthly_usd)}{!option.cost_complete && "*"}
                {option.licence_monthly_usd > 0 && <div className="text-xs text-rose-700">incl. {usd(option.licence_monthly_usd)} licence</div>}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {usd(option.one_off_cost_usd)}
                <div className="text-xs text-slate-500">{option.effort_person_days[0]}–{option.effort_person_days[1]} person-days</div>
              </td>
              <td className="px-3 py-2 text-right font-medium tabular-nums">{usd(option.total_cost_usd)}</td>
              <td className="px-3 py-2">
                {formatDate(option.finish_date)}
                <div className="text-xs text-slate-500">{option.duration_weeks} weeks</div>
                {!option.fits_deadline && <div className="text-xs font-medium text-rose-700">misses deadline</div>}
              </td>
              <td className="px-3 py-2">
                <span className={`rounded px-1.5 py-0.5 text-xs ${RISK_STYLES[option.risk_level]}`}>{option.risk_level}</span>
              </td>
              <td className="px-3 py-2">
                {onChooseTarget && option.strategy !== plan.strategy && (
                  <button type="button" onClick={() => onChooseTarget(option)} className="text-xs text-slate-600 underline hover:text-slate-900">
                    Plan this
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="space-y-1 px-4 py-3 text-xs text-slate-500">
        {plan.considered.map((item) => (
          <li key={item.strategy}>
            <span className="font-medium text-slate-700">{item.label}:</span> {item.reason}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ToolList({ title, tools }: { title: string; tools: ToolRef[] }) {
  if (tools.length === 0) {
    return null;
  }
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <ul className="mt-1 space-y-0.5 text-sm">
        {tools.map((tool) => (
          <li key={tool.id}>
            <a href={tool.url} target="_blank" rel="noreferrer" className="text-slate-800 underline decoration-slate-300 hover:decoration-slate-800">
              {tool.name}
            </a>
            {tool.review && <span className="ml-1 text-xs text-amber-700">({tool.review})</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function MethodAndTools({ plan }: { plan: MigrationPlan }) {
  const method = plan.method;
  return (
    <section className="grid gap-4 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-2">
      <div>
        <h2 className="font-medium text-slate-900">Method: {method.label}</h2>
        <p className="mt-1 text-sm text-slate-700">{method.reason}</p>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
          <dt className="text-slate-500">Network copy</dt>
          <dd>{method.transfer_hours == null ? "unknown" : `${method.transfer_hours.toLocaleString()} hours`}</dd>
          <dt className="text-slate-500">Link capacity</dt>
          <dd>{method.daily_capacity_gb == null ? "unknown" : `${method.daily_capacity_gb.toLocaleString()} GB/day`}</dd>
          <dt className="text-slate-500">CDC keeps up</dt>
          <dd>{method.cdc_feasible == null ? "unknown" : method.cdc_feasible ? "yes" : "no"}</dd>
        </dl>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <ToolList title="Assessment" tools={plan.tools.assessment} />
        <ToolList title="Schema conversion" tools={plan.tools.schema_conversion} />
        <ToolList title="Data movement" tools={plan.tools.data_movement} />
        <ToolList title="Validation" tools={plan.tools.validation} />
        <ToolList title="Supporting" tools={plan.tools.supporting} />
      </div>
    </section>
  );
}

function Runbook({ plan }: { plan: MigrationPlan }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="font-medium text-slate-900">Runbook ({plan.total_duration_weeks} weeks)</h2>
      <ol className="mt-3 space-y-2">
        {plan.phases.map((phase) => (
          <li key={phase.id}>
            <details className="rounded border border-slate-100 px-3 py-2">
              <summary className="cursor-pointer text-sm">
                <span className="font-medium">{phase.order}. {phase.name}</span>
                <span className="ml-2 text-xs text-slate-500">{phase.duration_days} days · {phase.owner_role}</span>
              </summary>
              <ul className="mt-2 list-disc pl-5 text-sm text-slate-700">
                {phase.tasks.map((task) => (
                  <li key={task}>{task}</li>
                ))}
              </ul>
              <p className="mt-2 text-xs font-medium text-slate-500">Go / no-go</p>
              <ul className="list-disc pl-5 text-xs text-slate-600">
                {phase.go_no_go.map((check) => (
                  <li key={check}>{check}</li>
                ))}
              </ul>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}

function RisksAndRollback({ plan }: { plan: MigrationPlan }) {
  return (
    <section className="grid gap-4 md:grid-cols-2">
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="font-medium text-slate-900">Risks ({plan.risks.length})</h2>
        <ul className="mt-2 space-y-3 text-sm">
          {plan.risks.map((risk) => (
            <li key={risk.id}>
              <span className={`mr-2 rounded px-1.5 py-0.5 text-xs ${RISK_STYLES[risk.severity]}`}>{risk.severity}</span>
              <span className="font-medium">{risk.title}</span>
              <p className="text-slate-600">{risk.impact}</p>
              <p className="text-slate-800">Mitigation: {risk.mitigation}</p>
            </li>
          ))}
          {plan.risks.length === 0 && <li className="text-slate-500">No risk rules matched.</li>}
        </ul>
      </div>
      <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 text-sm">
        <div>
          <h2 className="font-medium text-slate-900">Rollback</h2>
          <p className="mt-1 text-slate-700">{plan.rollback.approach}</p>
          <ul className="mt-1 list-disc pl-5 text-slate-600">
            {plan.rollback.triggers.map((trigger) => (
              <li key={trigger}>{trigger}</li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="font-medium text-slate-900">Validation</h2>
          <ul className="mt-1 list-disc pl-5 text-slate-600">
            {plan.validation.map((check) => (
              <li key={check}>{check}</li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="font-medium text-slate-900">Assumptions</h2>
          <ul className="mt-1 list-disc pl-5 text-xs text-slate-500">
            {plan.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

export default function PlanView({ plan, onChooseTarget }: { plan: MigrationPlan; onChooseTarget?: (option: StrategyOption) => void }) {
  const chosen = plan.strategies.find((option) => option.target_service_id === plan.target_service_id);
  const keepsLicensedEngine = chosen ? COMMERCIAL_ENGINES.includes(chosen.engine) : false;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            {engineLabel(plan.source.engine)} {plan.source.version ?? ""} → {plan.target_name}
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            {plan.strategies.find((option) => option.strategy === plan.strategy)?.label ?? plan.strategy} · from{" "}
            {PLATFORM_LABELS[plan.source.platform ?? ""] ?? "unknown platform"} · {plan.source.size_gb ? `${plan.source.size_gb.toLocaleString()} GB` : "size unknown"} ·{" "}
            starts {formatDate(plan.start_date)} · deadline {formatDate(plan.deadline)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge ok={plan.fits_deadline} yes="Meets deadline" no="Misses deadline" />
          {keepsLicensedEngine && plan.request.assessment_id && (
            <Link
              to={`/requests/new?assessment=${plan.request.assessment_id}&engine=${chosen?.engine}&kind=migration&plan=${plan.id}`}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
            >
              Justify keeping {engineLabel(chosen?.engine)} →
            </Link>
          )}
        </div>
      </div>
      {plan.two_step && <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Two-step option: {plan.two_step}</p>}
      <StrategyTable plan={plan} onChooseTarget={onChooseTarget} />
      <MethodAndTools plan={plan} />
      <Runbook plan={plan} />
      <RisksAndRollback plan={plan} />
    </div>
  );
}

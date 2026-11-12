import { useState } from "react";
import type { ComponentStatus, CostEstimate } from "../api/assessments";

const STATUS_STYLES: Record<ComponentStatus, { label: string; className: string }> = {
  priced: { label: "Priced", className: "bg-emerald-100 text-emerald-800" },
  estimated: { label: "Estimated", className: "bg-gold-100 text-gold-800" },
  included: { label: "Included", className: "bg-teal-100 text-teal-800" },
  not_priced: { label: "Not priced", className: "bg-amber-100 text-amber-800" },
  not_applicable: { label: "Not needed", className: "bg-sand-100 text-slate-600" },
};

/** What the bill is made of and which parts this estimate covers (M9). */
export function ComponentSummary({ estimate, currency, inrPerUsd }: { estimate: CostEstimate; currency: Currency; inrPerUsd: number | null }) {
  if (!estimate.components.length) return null;
  return (
    <table className="w-full table-fixed text-xs">
      <thead>
        <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
          <th className="w-1/2 py-1 font-medium">Component</th>
          <th className="py-1 font-medium">Status</th>
          <th className="py-1 text-right font-medium">Monthly</th>
        </tr>
      </thead>
      <tbody>
        {estimate.components.map((component, index) => {
          const style = STATUS_STYLES[component.status];
          return (
            <tr key={`${component.service ?? ""}-${component.id}-${index}`} className="border-t border-slate-100 align-top">
              <td className="py-1 pr-2">
                <div className="font-medium text-slate-800">
                  {component.label}
                  {component.service && <span className="font-normal text-slate-500"> · {component.service}</span>}
                </div>
                <div className="text-slate-500">{component.note}</div>
              </td>
              <td className="py-1">
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${style.className}`}>{style.label}</span>
              </td>
              <td className="py-1 text-right tabular-nums text-slate-800">
                {component.monthly_usd !== null ? formatMoney(component.monthly_usd, currency, inrPerUsd) : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export type Currency = "usd" | "inr";

const TIER_ORDER = ["budget", "balanced", "performance"];
const TERM_LABELS: Record<string, string> = { on_demand: "on-demand", "1yr": "1-year", "3yr": "3-year" };

export function formatMoney(usd: number, currency: Currency, inrPerUsd: number | null): string {
  if (currency === "inr" && inrPerUsd) {
    return `₹${Math.round(usd * inrPerUsd).toLocaleString("en-IN")}`;
  }
  return `$${usd.toLocaleString("en-US", { maximumFractionDigits: usd < 100 ? 2 : 0 })}`;
}

function licenceShare(estimate: CostEstimate): number {
  return estimate.lines.filter((line) => line.component.endsWith("licence")).reduce((total, line) => total + line.monthly_usd, 0);
}

function termsUsed(estimate: CostEstimate): string {
  const terms = new Set(estimate.lines.filter((line) => line.component.endsWith("compute")).map((line) => line.term));
  return [...terms].map((term) => TERM_LABELS[term] ?? term).join(", ");
}

function Breakdown({ estimate, currency, inrPerUsd }: { estimate: CostEstimate; currency: Currency; inrPerUsd: number | null }) {
  return (
    <div className="mt-2 space-y-2 text-xs text-slate-700">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">What this estimate covers</p>
      <ComponentSummary estimate={estimate} currency={currency} inrPerUsd={inrPerUsd} />
      <p className="pt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Line items</p>
      <table className="w-full table-fixed">
        <tbody>
          {estimate.lines.map((line, index) => (
            <tr key={`${line.sku}-${index}`} className="border-t border-slate-100 align-top">
              <td className="w-2/3 py-1 pr-2">
                <div className="font-medium">{line.component}</div>
                <div className="text-slate-500">{line.description}</div>
                <div className="text-slate-400">
                  {line.quantity.toLocaleString("en-US", { maximumFractionDigits: 0 })} {line.unit} × $
                  {line.unit_usd.toPrecision(4)} · {line.region} · {TERM_LABELS[line.term] ?? line.term}
                </div>
              </td>
              <td className="py-1 text-right tabular-nums">{formatMoney(line.monthly_usd, currency, inrPerUsd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {estimate.environment_multiplier !== 1 && <p>Environments multiplier: × {estimate.environment_multiplier}</p>}
      {estimate.missing.length > 0 && (
        <ul className="list-disc pl-4 text-amber-700">
          {estimate.missing.map((item) => (
            <li key={item}>Not priced: {item}</li>
          ))}
        </ul>
      )}
      {estimate.notes.length > 0 && (
        <ul className="list-disc pl-4 text-slate-500">
          {[...new Set(estimate.notes)].map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface CostTiersProps {
  tiers: Record<string, CostEstimate>;
  currency: Currency;
  inrPerUsd: number | null;
}

export default function CostTiers({ tiers, currency, inrPerUsd }: CostTiersProps) {
  const [openTier, setOpenTier] = useState<string | null>(null);
  const ordered = TIER_ORDER.filter((tier) => tiers[tier]);
  const anyPriced = ordered.some((tier) => tiers[tier].lines.length > 0);

  if (!anyPriced) {
    const reasons = ordered.length ? tiers[ordered[0]].missing : [];
    return (
      <div className="rounded bg-amber-50 p-2 text-xs text-amber-900">
        <p className="font-medium">Price not available</p>
        {reasons.map((reason) => (
          <p key={reason}>{reason}</p>
        ))}
      </div>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-3 gap-2">
        {ordered.map((tierName) => {
          const estimate = tiers[tierName];
          return (
            <button
              key={tierName}
              type="button"
              onClick={() => setOpenTier(openTier === tierName ? null : tierName)}
              aria-expanded={openTier === tierName}
              className={`rounded-xl border p-2.5 text-left transition duration-200 hover:-translate-y-0.5 hover:shadow-soft ${openTier === tierName ? "border-coral-400 bg-coral-50/60 ring-2 ring-coral-100" : "border-sand-200 bg-white hover:border-coral-200"}`}
            >
              <div className="text-xs text-slate-500">{estimate.label}</div>
              <div className="font-semibold tabular-nums text-slate-900">
                {formatMoney(estimate.monthly_usd, currency, inrPerUsd)}
                {!estimate.complete && <span title="Some parts are not priced">*</span>}
              </div>
              <div className="text-[11px] text-slate-500">/month · {termsUsed(estimate) || "—"}</div>
              {licenceShare(estimate) > 0 && (
                <div className="text-[11px] text-rose-700">incl. {formatMoney(licenceShare(estimate), currency, inrPerUsd)} licence</div>
              )}
            </button>
          );
        })}
      </div>
      {openTier && <Breakdown estimate={tiers[openTier]} currency={currency} inrPerUsd={inrPerUsd} />}
      {ordered.some((tier) => !tiers[tier].complete) && (
        <p className="mt-1 text-[11px] text-amber-700">* Partial: some components are not priced (open a tier for details).</p>
      )}
    </div>
  );
}

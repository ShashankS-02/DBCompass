import { useMemo, useState } from "react";
import type { FilterReason, ServiceScore } from "../api/assessments";

interface WhyNotPanelProps {
  filteredOut: FilterReason[];
  scores: ServiceScore[];
  recommendedIds: Set<string>;
}

/** "Why not X?": removal reasons for filtered services, or the score gap for ones that scored lower. */
export default function WhyNotPanel({ filteredOut, scores, recommendedIds }: WhyNotPanelProps) {
  const reasonsByService = useMemo(() => {
    const grouped = new Map<string, FilterReason[]>();
    for (const reason of filteredOut) {
      grouped.set(reason.service_id, [...(grouped.get(reason.service_id) ?? []), reason]);
    }
    return grouped;
  }, [filteredOut]);

  const outscored = scores.filter((score) => !recommendedIds.has(score.service_id));
  const options = [...reasonsByService.keys(), ...outscored.map((score) => score.service_id)].sort();
  const [selected, setSelected] = useState("");
  const topScore = scores[0]?.total_score ?? 0;
  const selectedScore = scores.find((score) => score.service_id === selected);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="font-medium text-slate-900">Why not…?</h2>
      <p className="mt-1 text-sm text-slate-600">Pick any service that was not recommended to see why.</p>
      <select
        className="mt-3 w-full max-w-md rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
        value={selected}
        onChange={(event) => setSelected(event.target.value)}
        aria-label="Service to explain"
      >
        <option value="">Choose a service…</option>
        {options.map((serviceId) => (
          <option key={serviceId} value={serviceId}>
            {serviceId}
          </option>
        ))}
      </select>

      {selected && reasonsByService.has(selected) && (
        <ul className="mt-3 space-y-1 text-sm text-slate-700">
          {reasonsByService.get(selected)!.map((reason) => (
            <li key={reason.rule_id}>
              <span className="mr-2 rounded bg-rose-50 px-1.5 py-0.5 font-mono text-xs text-rose-700">{reason.rule_id}</span>
              {reason.message}
            </li>
          ))}
        </ul>
      )}

      {selected && selectedScore && (
        <div className="mt-3 text-sm text-slate-700">
          <p>
            Passed every hard filter but scored <span className="font-medium">{selectedScore.total_score}</span> as a primary
            database; the best primary scored {topScore} (before adding any cache, search or analytics components).
          </p>
          {selectedScore.adjustments.length > 0 && (
            <ul className="mt-2 space-y-1">
              {selectedScore.adjustments.map((adjustment) => (
                <li key={adjustment.rule_id}>
                  <span className="mr-2 font-mono text-xs">
                    {adjustment.points > 0 ? "+" : ""}
                    {adjustment.points} {adjustment.rule_id}
                  </span>
                  {adjustment.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

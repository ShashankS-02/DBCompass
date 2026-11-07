import { computeDimensionWeights, type PrioritySlider } from "../api/questions";

interface PrioritySlidersProps {
  sliders: PrioritySlider[];
  fixedWeights: Record<string, number>;
  priorities: Record<string, number>;
  onChange: (priorities: Record<string, number>) => void;
}

function formatPercent(weight: number): string {
  return `${Math.round(weight * 100)}%`;
}

export default function PrioritySliders({ sliders, fixedWeights, priorities, onChange }: PrioritySlidersProps) {
  const weights = computeDimensionWeights(priorities, sliders, fixedWeights);

  return (
    <div className="space-y-4">
      {sliders.map((slider) => {
        const sliderValue = priorities[slider.id] ?? slider.default;
        return (
          <div key={slider.id}>
            <div className="flex items-baseline justify-between">
              <label htmlFor={`priority-${slider.id}`} className="text-sm font-medium text-slate-900">
                {slider.label}
              </label>
              <span className="text-xs tabular-nums text-slate-500">
                weight {formatPercent(weights[slider.dimension] ?? 0)}
              </span>
            </div>
            <input
              id={`priority-${slider.id}`}
              type="range"
              min={0}
              max={100}
              step={5}
              value={sliderValue}
              onChange={(event) => onChange({ ...priorities, [slider.id]: Number(event.target.value) })}
              className="w-full accent-slate-900"
            />
            <p className="text-xs text-slate-500">{slider.description}</p>
          </div>
        );
      })}
      <p className="text-xs text-slate-500">
        Fixed weights:{" "}
        {Object.entries(fixedWeights)
          .map(([dimension, weight]) => `${dimension} ${formatPercent(weight)}`)
          .join(", ")}
        .
      </p>
    </div>
  );
}

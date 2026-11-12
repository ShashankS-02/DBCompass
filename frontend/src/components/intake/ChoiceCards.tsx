import type { ReactNode } from "react";

export interface Choice {
  value: string;
  title: string;
  text?: string;
  icon?: ReactNode;
}

interface Props {
  choices: Choice[];
  value: string | null | undefined;
  onChange: (value: string) => void;
  columns?: 2 | 3;
}

/** Large tappable cards for the one-of-few decisions in the intake. */
export default function ChoiceCards({ choices, value, onChange, columns = 2 }: Props) {
  return (
    <div className={`grid gap-3 ${columns === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`} role="radiogroup">
      {choices.map((choice) => {
        const selected = value === choice.value;
        return (
          <button
            key={choice.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(choice.value)}
            className={`group flex items-start gap-3 rounded-2xl border p-4 text-left transition duration-200 ${
              selected
                ? "border-teal-600 bg-teal-600 text-white shadow-lift"
                : "border-sand-200 bg-white text-slate-800 hover:-translate-y-0.5 hover:border-coral-300 hover:shadow-soft"
            }`}
          >
            {choice.icon && <span className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl ${selected ? "bg-white/15" : "bg-sand-50 text-coral-600"}`}>{choice.icon}</span>}
            <span>
              <span className="block font-semibold">{choice.title}</span>
              {choice.text && <span className={`mt-0.5 block text-sm ${selected ? "text-teal-50" : "text-slate-500"}`}>{choice.text}</span>}
            </span>
          </button>
        );
      })}
    </div>
  );
}

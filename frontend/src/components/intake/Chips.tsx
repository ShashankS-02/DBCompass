interface Option {
  value: string;
  label: string;
}

interface SingleProps {
  options: Option[];
  value: string | undefined;
  onChange: (value: string | undefined) => void;
}

export function SingleChips({ options, value, onChange }: SingleProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const selected = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(selected ? undefined : option.value)}
            className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition duration-200 ${
              selected
                ? "scale-[1.03] border-teal-600 bg-teal-600 text-white shadow-soft"
                : "border-sand-200 bg-white text-slate-700 hover:-translate-y-0.5 hover:border-coral-300 hover:text-coral-700 hover:shadow-soft"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

interface MultiProps {
  options: Option[];
  value: string[];
  onChange: (value: string[]) => void;
}

export function MultiChips({ options, value, onChange }: MultiProps) {
  const toggle = (item: string) => onChange(value.includes(item) ? value.filter((existing) => existing !== item) : [...value, item]);
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const selected = value.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            onClick={() => toggle(option.value)}
            className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition duration-200 ${
              selected
                ? "scale-[1.03] border-teal-600 bg-teal-600 text-white shadow-soft"
                : "border-sand-200 bg-white text-slate-700 hover:-translate-y-0.5 hover:border-coral-300 hover:text-coral-700 hover:shadow-soft"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

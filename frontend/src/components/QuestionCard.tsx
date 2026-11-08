import { useState } from "react";
import type { Question, QuestionOption } from "../api/questions";

interface QuestionCardProps {
  question: Question;
  value: unknown;
  onChange: (value: unknown) => void;
  error?: string;
  defaultHint?: string;
  repoEvidence?: { confidence: number; evidence: string[] };
}

const inputClass =
  "rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900 focus:border-slate-500 focus:outline-none";

function Chip({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`rounded-full border px-3 py-1 text-sm transition-colors ${
        selected
          ? "border-slate-900 bg-slate-900 text-white"
          : "border-slate-300 bg-white text-slate-700 hover:border-slate-500"
      }`}
    >
      {children}
    </button>
  );
}

function SingleSelectInput({ question, value, onChange }: QuestionCardProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {question.options.map((option) => (
        <Chip
          key={option.value}
          selected={value === option.value}
          onClick={() => onChange(value === option.value ? undefined : option.value)}
        >
          {option.label}
        </Chip>
      ))}
    </div>
  );
}

function toggleMultiValue(current: string[], option: QuestionOption, options: QuestionOption[]): string[] {
  if (current.includes(option.value)) {
    return current.filter((item) => item !== option.value);
  }
  if (option.exclusive) {
    return [option.value];
  }
  const exclusiveValues = options.filter((item) => item.exclusive).map((item) => item.value);
  return [...current.filter((item) => !exclusiveValues.includes(item)), option.value];
}

function MultiSelectInput({ question, value, onChange }: QuestionCardProps) {
  const selectedValues = Array.isArray(value) ? (value as string[]) : [];
  return (
    <div className="flex flex-wrap gap-2">
      {question.options.map((option) => (
        <Chip
          key={option.value}
          selected={selectedValues.includes(option.value)}
          onClick={() => {
            const nextValues = toggleMultiValue(selectedValues, option, question.options);
            onChange(nextValues.length ? nextValues : undefined);
          }}
        >
          {option.label}
        </Chip>
      ))}
    </div>
  );
}

function parseNumber(text: string): number | undefined {
  if (text.trim() === "") {
    return undefined;
  }
  const parsed = Number(text);
  return Number.isNaN(parsed) ? undefined : parsed;
}

function NumberInput({ question, value, onChange }: QuestionCardProps) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="number"
        className={`${inputClass} w-40`}
        value={typeof value === "number" ? value : ""}
        min={question.min ?? undefined}
        max={question.max ?? undefined}
        step={question.integer ? 1 : "any"}
        onChange={(event) => onChange(parseNumber(event.target.value))}
      />
      {question.unit && <span className="text-sm text-slate-500">{question.unit}</span>}
    </div>
  );
}

function BooleanInput({ value, onChange }: QuestionCardProps) {
  return (
    <div className="flex gap-2">
      <Chip selected={value === true} onClick={() => onChange(value === true ? undefined : true)}>
        Yes
      </Chip>
      <Chip selected={value === false} onClick={() => onChange(value === false ? undefined : false)}>
        No
      </Chip>
    </div>
  );
}

function TextInput({ question, value, onChange }: QuestionCardProps) {
  return (
    <input
      type="text"
      className={`${inputClass} w-full max-w-sm`}
      placeholder={question.placeholder ?? ""}
      value={typeof value === "string" ? value : ""}
      maxLength={200}
      onChange={(event) => onChange(event.target.value === "" ? undefined : event.target.value)}
    />
  );
}

function ListInput({ value, onChange }: QuestionCardProps) {
  const items = Array.isArray(value) ? (value as string[]) : [];
  const [draft, setDraft] = useState("");

  const addDraft = () => {
    const trimmed = draft.trim();
    if (trimmed && !items.includes(trimmed)) {
      onChange([...items, trimmed]);
    }
    setDraft("");
  };

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          type="text"
          className={`${inputClass} w-full max-w-sm`}
          value={draft}
          placeholder="Type and press Enter"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addDraft();
            }
          }}
        />
        <button type="button" onClick={addDraft} className="rounded-md border border-slate-300 px-3 text-sm">
          Add
        </button>
      </div>
      {items.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <span key={item} className="flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-sm">
              {item}
              <button
                type="button"
                aria-label={`Remove ${item}`}
                className="text-slate-500 hover:text-slate-900"
                onClick={() => {
                  const remaining = items.filter((existing) => existing !== item);
                  onChange(remaining.length ? remaining : undefined);
                }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function MoneyInput({ value, onChange }: QuestionCardProps) {
  const money = (value ?? {}) as { amount?: number; currency?: string };
  const currency = money.currency ?? "usd";
  return (
    <div className="flex items-center gap-2">
      <input
        type="number"
        min={0}
        className={`${inputClass} w-40`}
        value={money.amount ?? ""}
        placeholder="Unknown"
        onChange={(event) => {
          const amount = parseNumber(event.target.value);
          onChange(amount === undefined ? undefined : { amount, currency });
        }}
      />
      <select
        className={inputClass}
        value={currency}
        onChange={(event) => {
          if (money.amount !== undefined) {
            onChange({ amount: money.amount, currency: event.target.value });
          }
        }}
      >
        <option value="usd">USD / month</option>
        <option value="inr">INR / month</option>
      </select>
    </div>
  );
}

function EngineVersionInput({ question, value, onChange }: QuestionCardProps) {
  const engineVersion = (value ?? {}) as { engine?: string; version?: string | null };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        className={inputClass}
        value={engineVersion.engine ?? ""}
        onChange={(event) =>
          onChange(
            event.target.value === ""
              ? undefined
              : { engine: event.target.value, version: engineVersion.version ?? null },
          )
        }
      >
        <option value="">Not specified</option>
        {question.options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <input
        type="text"
        className={`${inputClass} w-32`}
        placeholder="Version"
        maxLength={40}
        disabled={!engineVersion.engine || engineVersion.engine === "none"}
        value={engineVersion.version ?? ""}
        onChange={(event) =>
          onChange({ engine: engineVersion.engine, version: event.target.value === "" ? null : event.target.value })
        }
      />
    </div>
  );
}

const INPUTS = {
  single_select: SingleSelectInput,
  multi_select: MultiSelectInput,
  number: NumberInput,
  boolean: BooleanInput,
  text: TextInput,
  list: ListInput,
  money: MoneyInput,
  engine_version: EngineVersionInput,
};

export default function QuestionCard(props: QuestionCardProps) {
  const { question, error, defaultHint, repoEvidence } = props;
  const [showWhy, setShowWhy] = useState(false);
  const Input = INPUTS[question.type];

  return (
    <div className="border-t border-slate-100 py-4 first:border-t-0">
      <div className="mb-2 flex items-start gap-2">
        <label className="text-sm font-medium text-slate-900">{question.label}</label>
        <button
          type="button"
          onClick={() => setShowWhy(!showWhy)}
          aria-expanded={showWhy}
          aria-label={`Why we ask: ${question.label}`}
          title={question.why}
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-slate-300 text-xs text-slate-500 hover:border-slate-500"
        >
          ?
        </button>
      </div>
      {showWhy && <p className="mb-2 text-xs text-slate-500">Why it matters: {question.why}</p>}
      <Input {...props} />
      {defaultHint && <p className="mt-2 text-xs text-slate-500">{defaultHint}</p>}
      {repoEvidence && (
        <p className="mt-2 text-xs text-indigo-700" title={repoEvidence.evidence.join("\n")}>
          From repo ({Math.round(repoEvidence.confidence * 100)}% confidence): <span className="font-mono">{repoEvidence.evidence[0] ?? ""}</span>
        </p>
      )}
      {error && <p className="mt-2 text-xs font-medium text-rose-600">{error}</p>}
    </div>
  );
}

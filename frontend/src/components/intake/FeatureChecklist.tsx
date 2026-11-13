import { useState } from "react";
import type { EngineFeature } from "../../api/intake";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  return (
    <button type="button" onClick={() => void copy()} className="rounded-md border border-sand-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-600 hover:border-coral-300 hover:text-coral-700">
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function FeatureRow({ feature, checked, onToggle }: { feature: EngineFeature; checked: boolean; onToggle: () => void }) {
  const [showHow, setShowHow] = useState(false);
  return (
    <li className={`rounded-xl border transition ${checked ? "border-coral-300 bg-coral-50/60" : "border-sand-200 bg-white hover:border-coral-200"}`}>
      <div className="flex items-start gap-3 p-3">
        <input type="checkbox" className="mt-1 h-4 w-4 accent-coral-500" checked={checked} onChange={onToggle} id={`feature-${feature.feature}`} />
        <label htmlFor={`feature-${feature.feature}`} className="flex-1 cursor-pointer text-sm font-medium text-slate-800">
          {feature.label}
        </label>
        <button
          type="button"
          onClick={() => setShowHow(!showHow)}
          aria-expanded={showHow}
          className="shrink-0 text-xs font-semibold text-coral-700 link-underline"
        >
          {showHow ? "Hide" : "How to check"}
        </button>
      </div>
      {showHow && (
        <div className="animate-fade-up border-t border-sand-100 px-3 py-2">
          <div className="flex items-start gap-2">
            <code className="min-w-0 flex-1 whitespace-pre-wrap break-words rounded-lg bg-ink-900 px-3 py-2 font-mono text-[12px] leading-relaxed text-sand-100">{feature.how_to_check}</code>
            <CopyButton text={feature.how_to_check} />
          </div>
          <p className="mt-1.5 text-[11px] text-slate-500">Returns object names and settings only; no table rows.</p>
        </div>
      )}
    </li>
  );
}

interface Props {
  engineLabel: string;
  discoveryNote: string | null;
  features: EngineFeature[];
  selected: string[];
  onChange: (selected: string[]) => void;
}

/** Engine-specific checklist with a metadata-only query behind each item. */
export default function FeatureChecklist({ engineLabel, discoveryNote, features, selected, onChange }: Props) {
  const toggle = (feature: string) => {
    onChange(selected.includes(feature) ? selected.filter((item) => item !== feature) : [...selected, feature]);
  };
  return (
    <div>
      <p className="text-sm text-slate-600">
        Tick what the application relies on in {engineLabel}. Not sure? Open <span className="font-semibold text-slate-800">How to check</span> for a
        query your DBA can run; it reads only the catalog, never your data.
      </p>
      {discoveryNote && <p className="mt-1 text-xs text-slate-500">{discoveryNote}</p>}
      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {features.map((feature) => (
          <FeatureRow key={feature.feature} feature={feature} checked={selected.includes(feature.feature)} onToggle={() => toggle(feature.feature)} />
        ))}
      </ul>
      <p className="mt-2 text-xs text-slate-500">{selected.length === 0 ? "Nothing ticked means none of these are used." : `${selected.length} selected.`}</p>
    </div>
  );
}

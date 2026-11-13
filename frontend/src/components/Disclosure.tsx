import { useId, useState, type ReactNode } from "react";

interface DisclosureProps {
  title: string;
  hint?: string; // one line under the title, e.g. "6 reasons"
  defaultOpen?: boolean;
  children: ReactNode;
}

/** A closed-by-default section styled like the monthly cost tier buttons: click to open the details. */
export default function Disclosure({ title, hint, defaultOpen = false, children }: DisclosureProps) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        className={`flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-2.5 text-left transition duration-200 hover:-translate-y-0.5 hover:shadow-soft ${
          open ? "border-coral-400 bg-coral-50/60 ring-2 ring-coral-100" : "border-sand-200 bg-white hover:border-coral-200"
        }`}
      >
        <span>
          <span className="block text-sm font-semibold text-slate-900">{title}</span>
          {hint && <span className="block text-[11px] text-slate-500">{hint}</span>}
        </span>
        <svg
          viewBox="0 0 24 24"
          aria-hidden="true"
          className={`h-4 w-4 shrink-0 text-coral-500 transition-transform duration-300 ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div id={panelId} className="mt-2 animate-fade-up rounded-xl border border-sand-200 bg-white p-3 text-sm">
          {children}
        </div>
      )}
    </div>
  );
}

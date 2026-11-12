import { useEffect, useRef, useState } from "react";
import { downloadDesignDocument, type ExportFormat } from "../api/explain";
import { useAuth } from "../auth/AuthProvider";
import { Spinner } from "./Loader";

const OPTIONS: { format: ExportFormat; label: string; hint: string }[] = [
  { format: "pdf", label: "PDF design document", hint: "For review boards and email" },
  { format: "md", label: "Markdown", hint: "For wikis and repositories" },
];

/** Export button with a small menu; downloads the design document of the saved assessment. */
export default function ExportMenu({ assessmentId }: { assessmentId: string }) {
  const { getAccessToken } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (container.current && !container.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const download = async (format: ExportFormat) => {
    setBusy(format);
    setError(null);
    try {
      await downloadDesignDocument(assessmentId, format, getAccessToken);
      setOpen(false);
    } catch (caught) {
      setError((caught as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div ref={container} className="relative">
      <button type="button" className="btn-dark px-3 py-1.5" aria-expanded={open} onClick={() => setOpen(!open)}>
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M12 4v11m0 0l-4-4m4 4l4-4M5 20h14" />
        </svg>
        Export
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-64 origin-top-right animate-fade-up rounded-2xl border border-sand-200 bg-white p-1.5 shadow-lift">
          {OPTIONS.map((option) => (
            <button
              key={option.format}
              type="button"
              disabled={busy !== null}
              onClick={() => void download(option.format)}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition hover:bg-sand-50"
            >
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-coral-50 text-[10px] font-bold uppercase text-coral-700">
                {busy === option.format ? <Spinner className="h-3.5 w-3.5" /> : option.format}
              </span>
              <span>
                <span className="block text-sm font-semibold text-slate-800">{option.label}</span>
                <span className="block text-xs text-slate-500">{option.hint}</span>
              </span>
            </button>
          ))}
          {error && <p className="px-3 py-1 text-xs text-rose-600">{error}</p>}
        </div>
      )}
    </div>
  );
}

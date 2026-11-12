import { useEffect, useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { askQuestion, createExplanation, fetchExplanation, type AnswerOut, type Explanation } from "../api/explain";
import { useAuth } from "../auth/AuthProvider";
import { Spinner } from "./Loader";

const SUGGESTED_QUESTIONS = ["Why is the top option ranked first?", "How do the top options compare on cost?", "Which answers were assumed?"];

function SourceBadge({ explanation }: { explanation: Explanation }) {
  if (explanation.source === "llm") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-gold-300 bg-gold-50 px-2.5 py-0.5 text-xs font-semibold text-gold-800">
        <span className="h-1.5 w-1.5 rounded-full bg-gold-500" /> AI-written · fact-checked against this result
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-teal-200 bg-teal-50 px-2.5 py-0.5 text-xs font-semibold text-teal-700">
      <span className="h-1.5 w-1.5 rounded-full bg-teal-500" /> Built from the rule trace
    </span>
  );
}

function WritingSkeleton() {
  return (
    <div className="space-y-2.5 py-1" aria-label="Writing the explanation">
      <div className="skeleton h-3.5 w-11/12" />
      <div className="skeleton h-3.5 w-full [animation-delay:0.1s]" />
      <div className="skeleton h-3.5 w-4/5 [animation-delay:0.2s]" />
      <div className="skeleton mt-4 h-3.5 w-full [animation-delay:0.3s]" />
      <div className="skeleton h-3.5 w-3/4 [animation-delay:0.4s]" />
    </div>
  );
}

function errorText(caught: unknown): string {
  return caught instanceof ApiError && caught.detail ? caught.detail : (caught as Error).message;
}

function AskBox({ assessmentId }: { assessmentId: string }) {
  const { getAccessToken } = useAuth();
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<AnswerOut[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async (text: string) => {
    if (text.trim().length < 3 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const answer = await askQuestion(assessmentId, text.trim(), getAccessToken);
      setAnswers((current) => [answer, ...current]);
      setQuestion("");
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void ask(question);
  };

  return (
    <div className="mt-5 border-t border-sand-100 pt-4">
      <h3 className="text-sm font-semibold text-slate-900">Ask about this result</h3>
      <form onSubmit={onSubmit} className="mt-2 flex gap-2">
        <input
          className="min-w-0 flex-1 border px-3 py-2 text-sm"
          placeholder="e.g. Why was Spanner ruled out?"
          value={question}
          maxLength={500}
          onChange={(event) => setQuestion(event.target.value)}
          aria-label="Question about this result"
        />
        <button type="submit" disabled={busy || question.trim().length < 3} className="btn-dark px-3 py-2">
          {busy ? <Spinner /> : "Ask"}
        </button>
      </form>
      {answers.length === 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {SUGGESTED_QUESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={busy}
              onClick={() => void ask(suggestion)}
              className="rounded-full border border-sand-200 bg-sand-50 px-2.5 py-1 text-xs text-slate-600 transition hover:-translate-y-0.5 hover:border-coral-300 hover:text-coral-700"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}
      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
      {busy && (
        <p className="mt-3 flex items-center gap-2 text-sm text-slate-500">
          <Spinner className="h-3.5 w-3.5" /> Checking the answer against the result…
        </p>
      )}
      <ul className="mt-3 space-y-3">
        {answers.map((item, index) => (
          <li key={`${item.question}-${answers.length - index}`} className="animate-fade-up rounded-xl bg-sand-50 p-3 text-sm">
            <p className="font-semibold text-slate-800">{item.question}</p>
            <p className={`mt-1 ${item.answerable ? "text-slate-700" : "text-slate-500"}`}>{item.answer}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** "Explain this result": saved AI explanation, or generate one on request; plus grounded Q&A. */
export default function ExplanationPanel({ assessmentId, scenarioActive }: { assessmentId: string; scenarioActive: boolean }) {
  const { getAccessToken } = useAuth();
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState(true);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    fetchExplanation(assessmentId, getAccessToken)
      .then(setExplanation)
      .catch(() => setExplanation(null))
      .finally(() => setLoading(false));
  }, [assessmentId, getAccessToken]);

  const write = async (refresh: boolean) => {
    setWriting(true);
    setError(null);
    try {
      setExplanation(await createExplanation(assessmentId, refresh, getAccessToken));
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setWriting(false);
    }
  };

  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Explanation</h2>
          {scenarioActive && <p className="text-xs text-slate-500">Describes the saved result, not the what-if scenario.</p>}
        </div>
        {explanation && <SourceBadge explanation={explanation} />}
      </div>

      <div className="mt-3">
        {(loading || writing) && <WritingSkeleton />}
        {!loading && !writing && !explanation && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-dashed border-sand-300 bg-sand-50/60 p-4">
            <p className="mr-auto text-sm text-slate-600">
              Get a plain-English summary of why these options rank where they do. Every number and service name is checked against this result.
            </p>
            <button type="button" className="btn-primary" onClick={() => void write(false)}>
              Explain this result
            </button>
          </div>
        )}
        {!writing && explanation && (
          <div className="stagger space-y-3 text-[15px] leading-relaxed text-slate-700">
            {explanation.paragraphs.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
        )}
        {explanation && explanation.notes.length > 0 && !writing && (
          <p className="mt-3 text-xs text-slate-500">{explanation.notes.join(" ")}</p>
        )}
        {explanation && !writing && (
          <button type="button" onClick={() => void write(true)} className="link-underline mt-3 text-xs font-semibold text-coral-700">
            {explanation.source === "llm" ? "Rewrite" : "Try again"}
          </button>
        )}
        {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
      </div>

      <AskBox assessmentId={assessmentId} />
    </section>
  );
}

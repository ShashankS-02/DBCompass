import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createAssessment } from "../api/assessments";
import {
  describeValue,
  fetchQuestions,
  validateRequirements,
  type Answers,
  type FormMode,
  type Question,
  type QuestionSchema,
  type Section,
  type ValidationReport,
} from "../api/questions";
import { useAuth } from "../auth/AuthProvider";
import PrioritySliders from "../components/PrioritySliders";
import QuestionCard from "../components/QuestionCard";

function indexQuestions(schema: QuestionSchema | null): Map<string, Question> {
  const index = new Map<string, Question>();
  for (const section of schema?.sections ?? []) {
    for (const question of section.questions) {
      index.set(question.id, question);
    }
  }
  return index;
}

function defaultPriorities(schema: QuestionSchema): Record<string, number> {
  const priorities: Record<string, number> = {};
  for (const slider of schema.priority_sliders) {
    priorities[slider.id] = slider.default;
  }
  return priorities;
}

function ModeToggle({ mode, onChange }: { mode: FormMode; onChange: (mode: FormMode) => void }) {
  const modes: { value: FormMode; label: string }[] = [
    { value: "quick", label: "Quick" },
    { value: "expert", label: "Expert" },
  ];
  return (
    <div className="inline-flex rounded-md border border-slate-300 bg-white p-0.5" role="group">
      {modes.map((item) => (
        <button
          key={item.value}
          type="button"
          aria-pressed={mode === item.value}
          onClick={() => onChange(item.value)}
          className={`rounded px-3 py-1 text-sm ${
            mode === item.value ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

interface SectionCardProps {
  section: Section;
  open: boolean;
  onToggle: () => void;
  answers: Answers;
  onAnswer: (fieldId: string, value: unknown) => void;
  errors: Map<string, string>;
  defaultHintFor: (question: Question) => string | undefined;
}

function SectionCard({ section, open, onToggle, answers, onAnswer, errors, defaultHintFor }: SectionCardProps) {
  const answeredCount = section.questions.filter((question) => answers[question.id] !== undefined).length;
  const hasError = section.questions.some((question) => errors.has(question.id));

  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span>
          <span className="font-medium text-slate-900">{section.title}</span>
          {section.description && <span className="ml-2 text-xs text-slate-500">{section.description}</span>}
        </span>
        <span className={`text-xs ${hasError ? "font-medium text-rose-600" : "text-slate-500"}`}>
          {hasError ? "Needs attention · " : ""}
          {answeredCount}/{section.questions.length} answered {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (
        <div className="px-4 pb-2">
          {section.questions.map((question) => (
            <QuestionCard
              key={question.id}
              question={question}
              value={answers[question.id]}
              onChange={(value) => onAnswer(question.id, value)}
              error={errors.get(question.id)}
              defaultHint={defaultHintFor(question)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function ReportPanel({
  report,
  stale,
  labelFor,
  questionFor,
}: {
  report: ValidationReport;
  stale: boolean;
  labelFor: (fieldId: string) => string;
  questionFor: (fieldId: string) => Question | undefined;
}) {
  return (
    <div className={`space-y-4 rounded-lg border bg-white p-4 ${stale ? "opacity-60" : ""}`}>
      <div className="flex items-center justify-between">
        <h2 className="font-medium text-slate-900">Validation</h2>
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            report.valid ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"
          }`}
        >
          {report.valid ? "Valid" : `${report.errors.length} problem(s)`}
        </span>
      </div>
      {stale && <p className="text-xs text-slate-500">Answers changed since this check. Validate again.</p>}

      {report.errors.length > 0 && (
        <ul className="space-y-1 text-sm text-rose-700">
          {report.errors.map((error) => (
            <li key={error.field_id}>
              <span className="font-medium">{labelFor(error.field_id)}</span>: {error.message}
            </li>
          ))}
        </ul>
      )}

      {report.assumed_fields.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Will be assumed</h3>
          <ul className="space-y-1 text-sm text-slate-700">
            {report.assumed_fields.map((field) => (
              <li key={field.field_id}>
                {labelFor(field.field_id)}:{" "}
                <span className="font-medium">{describeValue(questionFor(field.field_id), field.value)}</span>
                <span className="text-xs text-slate-500"> ({field.reason})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.unanswered_quick_fields.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Quick questions not answered ({report.unanswered_quick_fields.length})
          </h3>
          <p className="text-sm text-slate-700">{report.unanswered_quick_fields.map(labelFor).join(", ")}</p>
        </div>
      )}

      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Scoring weights</h3>
        <p className="text-sm tabular-nums text-slate-700">
          {Object.entries(report.dimension_weights)
            .map(([dimension, weight]) => `${dimension} ${Math.round(weight * 100)}%`)
            .join(" · ")}
        </p>
      </div>

      <details>
        <summary className="cursor-pointer text-xs text-slate-500">Normalised input (JSON)</summary>
        <pre className="mt-2 max-h-64 overflow-auto rounded bg-slate-50 p-2 text-xs">
          {JSON.stringify(report.normalised, null, 2)}
        </pre>
      </details>
    </div>
  );
}

export default function NewAssessment() {
  const { getAccessToken } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<FormMode>("quick");
  const [schema, setSchema] = useState<QuestionSchema | null>(null);
  const [expertSchema, setExpertSchema] = useState<QuestionSchema | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [priorities, setPriorities] = useState<Record<string, number>>({});
  const [migrating, setMigrating] = useState(false);
  const [closedSections, setClosedSections] = useState<Set<string>>(new Set());
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [reportStale, setReportStale] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    fetchQuestions(mode, getAccessToken)
      .then((loaded) => {
        if (cancelled) return;
        setSchema(loaded);
        setPriorities((current) => (Object.keys(current).length ? current : defaultPriorities(loaded)));
        if (mode === "expert") {
          setClosedSections(new Set(loaded.sections.slice(1).map((section) => section.id)));
        } else {
          setClosedSections(new Set());
        }
      })
      .catch((error: Error) => !cancelled && setLoadError(error.message));
    return () => {
      cancelled = true;
    };
  }, [mode, getAccessToken]);

  useEffect(() => {
    fetchQuestions("expert", getAccessToken)
      .then(setExpertSchema)
      .catch(() => setExpertSchema(null));
  }, [getAccessToken]);

  const allQuestions = useMemo(() => indexQuestions(expertSchema), [expertSchema]);
  const labelFor = (fieldId: string) => {
    if (fieldId.startsWith("priority.")) {
      return `${fieldId.slice("priority.".length)} priority`;
    }
    return allQuestions.get(fieldId)?.label ?? fieldId;
  };

  const errors = useMemo(() => {
    const errorMap = new Map<string, string>();
    for (const error of report?.errors ?? []) {
      errorMap.set(error.field_id, error.message);
    }
    return errorMap;
  }, [report]);

  if (loadError) {
    return <p className="text-rose-600">Could not load questions: {loadError}</p>;
  }
  if (!schema) {
    return <p className="text-slate-500">Loading questions…</p>;
  }

  const tier = (answers["app.tier"] as string | undefined) ?? schema.default_tier;
  const tierLabel = allQuestions.get("app.tier")?.options.find((option) => option.value === tier)?.label ?? tier;
  const defaultHintFor = (question: Question) => {
    if (answers[question.id] !== undefined || !question.tier_defaults || !(tier in question.tier_defaults)) {
      return undefined;
    }
    return `If left empty: ${describeValue(question, question.tier_defaults[tier])} (default for ${tierLabel})`;
  };

  const onAnswer = (fieldId: string, value: unknown) => {
    setAnswers((current) => {
      const next = { ...current };
      if (value === undefined) {
        delete next[fieldId];
      } else {
        next[fieldId] = value;
      }
      return next;
    });
    setReportStale(true);
  };

  const toggleSection = (sectionId: string) => {
    setClosedSections((current) => {
      const next = new Set(current);
      if (next.has(sectionId)) {
        next.delete(sectionId);
      } else {
        next.add(sectionId);
      }
      return next;
    });
  };

  const submit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const input = { mode, migrating, answers, priorities };
      const result = await validateRequirements(input, getAccessToken);
      setReport(result);
      setReportStale(false);
      if (result.valid) {
        const assessment = await createAssessment(input, getAccessToken);
        navigate(`/assessments/${assessment.id}`);
      }
    } catch (error) {
      setSubmitError((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const hasMigrationSection = schema.sections.some((section) => section.migration_only);
  const visibleSections = schema.sections.filter((section) => !section.migration_only || migrating);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">New assessment</h1>
          <p className="mt-1 text-sm text-slate-600">
            Answer what you know. Anything left empty is filled from defaults for your criticality tier and
            marked as assumed.
          </p>
        </div>
        <ModeToggle mode={mode} onChange={setMode} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-4">
          {hasMigrationSection && (
            <label className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm">
              <input
                type="checkbox"
                checked={migrating}
                onChange={(event) => {
                  setMigrating(event.target.checked);
                  setReportStale(true);
                }}
                className="accent-slate-900"
              />
              Planning a migration from an existing database?
            </label>
          )}
          {visibleSections.map((section) => (
            <SectionCard
              key={section.id}
              section={section}
              open={!closedSections.has(section.id)}
              onToggle={() => toggleSection(section.id)}
              answers={answers}
              onAnswer={onAnswer}
              errors={errors}
              defaultHintFor={defaultHintFor}
            />
          ))}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 font-medium text-slate-900">Priorities</h2>
            <PrioritySliders
              sliders={schema.priority_sliders}
              fixedWeights={schema.fixed_dimension_weights}
              priorities={priorities}
              onChange={(next) => {
                setPriorities(next);
                setReportStale(true);
              }}
            />
          </div>
          <button
            type="button"
            onClick={submit}
            disabled={submitting}
            className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {submitting ? "Working…" : "Get recommendations"}
          </button>
          {submitError && <p className="text-sm text-rose-600">Could not validate: {submitError}</p>}
          {report && (
            <ReportPanel
              report={report}
              stale={reportStale}
              labelFor={labelFor}
              questionFor={(fieldId) => allQuestions.get(fieldId)}
            />
          )}
        </aside>
      </div>
    </div>
  );
}

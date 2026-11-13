import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createAssessment } from "../api/assessments";
import { ApiError } from "../api/client";
import { fetchIntake, type IntakeConfig } from "../api/intake";
import { describeValue, fetchQuestions, validateRequirements, type Answers, type Question, type QuestionSchema, type ValidationReport } from "../api/questions";
import { useAuth } from "../auth/AuthProvider";
import { clearDraft, readDraft, useDraft } from "../hooks/useDraft";
import ChoiceCards from "../components/intake/ChoiceCards";
import { MultiChips, SingleChips } from "../components/intake/Chips";
import FeatureChecklist from "../components/intake/FeatureChecklist";
import StepFrame, { type StepMeta } from "../components/intake/StepFrame";
import { BusyOverlay, PageLoader } from "../components/Loader";
import PrioritySliders from "../components/PrioritySliders";
import QuestionCard from "../components/QuestionCard";

type AppKind = "existing" | "new";

const DRAFT_KEY = "dbcompass.intake.v1";
const NOT_A_SOURCE = new Set(["none"]);
const SIZE_BUCKETS = [
  { label: "Under 100 GB", gb: 50 },
  { label: "100 GB – 500 GB", gb: 300 },
  { label: "500 GB – 5 TB", gb: 2000 },
  { label: "5 – 50 TB", gb: 20000 },
  { label: "Over 50 TB", gb: 100000 },
];
const TRAFFIC_BUCKETS = [
  { label: "Light (under 100/s)", tps: 50 },
  { label: "Moderate (100 – 1,000/s)", tps: 500 },
  { label: "Busy (1,000 – 10,000/s)", tps: 5000 },
  { label: "Very busy (over 10,000/s)", tps: 25000 },
];

/** Fields the wizard asks itself; the optional expert survey hides them so nothing is asked twice. */
const WIZARD_FIELDS = new Set([
  "app.name", "app.origin", "app.vendor_name", "app.vendor_certified_db", "app.vendor_migration_support", "app.notes", "app.tier", "app.type",
  "app.existing_db", "app.requested_engine", "data.shape", "data.proc_code", "data.special_features", "vol.current_gb", "geo.user_regions",
  "pref.csp", "pref.licence_status", "team.source_skills", "team.target_skills", "team.capacity", "mig.source_platform", "mig.source_engine",
  "mig.size_gb", "wl.peak_tps", "eco.languages", "sec.personal_data", "sec.compliance", "sec.network", "app.env", "cost.egress_gb_month",
  "cost.connection_proxy",
]);
const YES_NO = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];

interface Draft {
  kind: AppKind | null;
  answers: Answers;
  priorities: Record<string, number>;
  step: number;
}

/** The draft survives tab switches, navigation inside the app, reloads and sign-in redirects. */
function loadDraft(): Draft | null {
  const parsed = readDraft<Partial<Draft>>(DRAFT_KEY);
  if (!parsed || typeof parsed !== "object" || !parsed.answers) return null;
  return { kind: parsed.kind ?? null, answers: parsed.answers, priorities: parsed.priorities ?? {}, step: parsed.step ?? 0 };
}

function engineOf(value: unknown): string | undefined {
  const engine = (value as { engine?: string } | undefined)?.engine;
  return engine && !NOT_A_SOURCE.has(engine) ? engine : undefined;
}

function versionOf(value: unknown): string {
  return ((value as { version?: string | null } | undefined)?.version as string | undefined) ?? "";
}

function indexQuestions(schema: QuestionSchema): Map<string, Question> {
  const index = new Map<string, Question>();
  schema.sections.forEach((section) => section.questions.forEach((question) => index.set(question.id, question)));
  return index;
}

function stepsFor(kind: AppKind | null): StepMeta[] {
  const start: StepMeta = { id: "start", title: "About the application", short: "Start" };
  const finish: StepMeta[] = [
    { id: "priorities", title: "What matters most", short: "Priorities" },
    { id: "review", title: "Review and run", short: "Review" },
  ];
  if (kind === "existing") {
    return [
      start,
      { id: "current_db", title: "The current database", short: "Database" },
      { id: "features", title: "What it uses today", short: "Features" },
      { id: "ownership", title: "Who owns it", short: "Team" },
      { id: "application", title: "The application", short: "Application" },
      { id: "preference", title: "Database in mind", short: "Preference" },
      ...finish,
    ];
  }
  if (kind === "new") {
    return [
      start,
      { id: "origin", title: "Who built it", short: "Origin" },
      { id: "essentials", title: "The essentials", short: "Essentials" },
      { id: "application", title: "The application", short: "Application" },
      ...finish,
    ];
  }
  return [start, ...finish];
}

function Block({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
      {hint && <p className="mb-2 text-xs text-slate-500">{hint}</p>}
      <div className={hint ? "" : "mt-2"}>{children}</div>
    </div>
  );
}

function EngineVersionPicker({
  options, value, onChange, versionPlaceholder = "Version (optional)",
}: { options: { value: string; label: string }[]; value: unknown; onChange: (value: { engine: string; version: string | null } | undefined) => void; versionPlaceholder?: string }) {
  const engine = engineOf(value);
  return (
    <div className="space-y-3">
      <SingleChips options={options} value={engine} onChange={(next) => onChange(next ? { engine: next, version: versionOf(value) || null } : undefined)} />
      {engine && (
        <input
          className="btn-ghost w-48 px-3 py-1.5 animate-fade-up"
          placeholder={versionPlaceholder}
          value={versionOf(value)}
          maxLength={40}
          onChange={(event) => onChange({ engine, version: event.target.value || null })}
        />
      )}
    </div>
  );
}

function SizePicker({ value, onChange }: { value: number | undefined; onChange: (gb: number | undefined) => void }) {
  const bucket = SIZE_BUCKETS.find((item) => item.gb === value);
  const custom = value !== undefined && !bucket;
  return (
    <div className="space-y-2">
      <SingleChips options={SIZE_BUCKETS.map((item) => ({ value: String(item.gb), label: item.label }))} value={bucket ? String(bucket.gb) : undefined} onChange={(next) => onChange(next ? Number(next) : undefined)} />
      <label className="flex items-center gap-2 text-sm text-slate-600">
        or exactly
        <input type="number" min={1} className="btn-ghost w-32 px-3 py-1" placeholder="GB" value={custom ? value : ""} onChange={(event) => onChange(event.target.value ? Number(event.target.value) : undefined)} />
        GB
      </label>
    </div>
  );
}

function ExpertSurvey({ schema, answers, onAnswer, migrating }: { schema: QuestionSchema; answers: Answers; onAnswer: (id: string, value: unknown) => void; migrating: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  const sections = schema.sections
    .filter((section) => !section.migration_only || migrating)
    .map((section) => ({ ...section, questions: section.questions.filter((question) => !WIZARD_FIELDS.has(question.id)) }))
    .filter((section) => section.questions.length > 0);
  return (
    <div className="space-y-2">
      {sections.map((section) => {
        const answered = section.questions.filter((question) => answers[question.id] !== undefined).length;
        const isOpen = open === section.id;
        return (
          <section key={section.id} className="rounded-xl border border-sand-200 bg-white">
            <button type="button" onClick={() => setOpen(isOpen ? null : section.id)} aria-expanded={isOpen} className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm">
              <span className="font-medium text-slate-800">{section.title}</span>
              <span className="text-xs text-slate-500">
                {answered}/{section.questions.length} {isOpen ? "▴" : "▾"}
              </span>
            </button>
            {isOpen && (
              <div className="animate-fade-up px-4 pb-2">
                {section.questions.map((question) => (
                  <QuestionCard key={question.id} question={question} value={answers[question.id]} onChange={(value) => onAnswer(question.id, value)} />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

export default function Intake() {
  const { getAccessToken } = useAuth();
  const navigate = useNavigate();
  const [schema, setSchema] = useState<QuestionSchema | null>(null);
  const [intake, setIntake] = useState<IntakeConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(() => loadDraft() ?? { kind: null, answers: {}, priorities: {}, step: 0 });
  const [resumed] = useState(() => loadDraft() !== null);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [checking, setChecking] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchQuestions("expert", getAccessToken), fetchIntake(getAccessToken)])
      .then(([loadedSchema, loadedIntake]) => {
        setSchema(loadedSchema);
        setIntake(loadedIntake);
        setDraft((current) => {
          if (Object.keys(current.priorities).length) return current;
          const priorities: Record<string, number> = {};
          loadedSchema.priority_sliders.forEach((slider) => (priorities[slider.id] = slider.default));
          return { ...current, priorities };
        });
      })
      .catch((error: Error) => setLoadError(error.message));
  }, [getAccessToken]);

  useDraft(DRAFT_KEY, draft);

  const questions = useMemo(() => (schema ? indexQuestions(schema) : new Map<string, Question>()), [schema]);
  const steps = useMemo(() => stepsFor(draft.kind), [draft.kind]);
  const step = steps[Math.min(draft.step, steps.length - 1)];
  const { kind, answers, priorities } = draft;
  const migrating = kind === "existing";

  const setAnswers = useCallback((patch: Record<string, unknown>) => {
    setDraft((current) => {
      const next = { ...current.answers };
      for (const [fieldId, value] of Object.entries(patch)) {
        if (value === undefined || value === null || (Array.isArray(value) && value.length === 0)) delete next[fieldId];
        else next[fieldId] = value;
      }
      return { ...current, answers: next };
    });
    setReport(null);
    setSubmitError(null);
  }, []);
  const setAnswer = (fieldId: string, value: unknown) => setAnswers({ [fieldId]: value });
  const go = (delta: number) => {
    setDraft((current) => ({ ...current, step: Math.max(0, Math.min(stepsFor(current.kind).length - 1, current.step + delta)) }));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const startOver = () => {
    clearDraft(DRAFT_KEY);
    setDraft({ kind: null, answers: {}, priorities: {}, step: 0 });
    setReport(null);
  };

  const engineOptions = useMemo(
    () => (questions.get("app.requested_engine")?.options ?? []).filter((option) => option.value !== "none").map((option) => ({ value: option.value, label: option.label })),
    [questions],
  );
  const optionsOf = (fieldId: string) => (questions.get(fieldId)?.options ?? []).map((option) => ({ value: option.value, label: option.label }));
  const commercial = intake?.commercial_engines ?? [];
  const sourceEngine = engineOf(answers["mig.source_engine"]);
  const requestedEngine = engineOf(answers["app.requested_engine"]);
  const supportOf = (engine: string | undefined) => (engine ? intake?.org_support.engines[engine] : undefined);

  const input = useMemo(() => ({ mode: "expert" as const, migrating, answers, priorities }), [migrating, answers, priorities]);

  const check = async () => {
    setChecking(true);
    setSubmitError(null);
    try {
      setReport(await validateRequirements(input, getAccessToken));
    } catch (caught) {
      setSubmitError(caught instanceof ApiError && caught.detail ? caught.detail : (caught as Error).message);
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    // Also re-runs once the questions load, so a draft resumed straight on Review is checked.
    if (step?.id === "review" && !report && !checking && !submitError && schema) void check();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step?.id, schema, report, submitError]);

  const submit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const assessment = await createAssessment(input, getAccessToken);
      clearDraft(DRAFT_KEY);
      navigate(`/assessments/${assessment.id}`);
    } catch (caught) {
      setSubmitError(caught instanceof ApiError && caught.detail ? caught.detail : (caught as Error).message);
      setSubmitting(false);
    }
  };

  if (loadError) return <p className="text-rose-600">Could not load the questionnaire: {loadError}</p>;
  if (!schema || !intake || !step) return <PageLoader label="Preparing the questionnaire" steps={["Loading questions", "Loading the supported-database list"]} />;

  const frame = (props: { title: string; lead?: string; canContinue?: boolean; skip?: boolean; continueLabel?: string; children: React.ReactNode; aside?: React.ReactNode; onNext?: () => void; busy?: boolean }) => (
    <StepFrame
      steps={steps}
      index={steps.indexOf(step)}
      title={props.title}
      lead={props.lead}
      canContinue={props.canContinue ?? true}
      continueLabel={props.continueLabel}
      onBack={() => go(-1)}
      onNext={props.onNext ?? (() => go(1))}
      onSkip={props.skip === false ? undefined : () => go(1)}
      busy={props.busy}
      aside={props.aside}
    >
      {props.children}
    </StepFrame>
  );

  const header = (
    <div className="mx-auto mb-4 flex max-w-4xl flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
      <span>About 5 minutes. Every question has an “I don't know”; skipped answers are assumed from the criticality tier and shown as such.</span>
      <span className="flex items-center gap-3">
        {resumed && draft.step > 0 && <span className="rounded-full bg-gold-50 px-2 py-0.5 font-semibold text-gold-800">Resumed your draft</span>}
        <button type="button" onClick={startOver} className="link-underline font-semibold text-slate-500 hover:text-coral-700">Start over</button>
      </span>
    </div>
  );

  let body: React.ReactNode = null;

  if (step.id === "start") {
    body = frame({
      title: "Tell us about the application",
      lead: "Two answers to begin with.",
      canContinue: kind !== null,
      skip: false,
      children: (
        <>
          <Block title="Application name">
            <input className="btn-ghost w-full max-w-md px-3 py-2" placeholder="e.g. Order Management" maxLength={200} value={(answers["app.name"] as string) ?? ""} onChange={(event) => setAnswer("app.name", event.target.value || undefined)} />
          </Block>
          <Block title="Is this an existing application or a new one?">
            <ChoiceCards
              value={kind}
              onChange={(value) => setDraft((current) => ({ ...current, kind: value as AppKind }))}
              choices={[
                { value: "existing", title: "Existing application", text: "It already runs on a database that must move to the cloud.", icon: <span className="text-lg">🗄️</span> },
                { value: "new", title: "New application", text: "Nothing is built yet; we need the right database to start with.", icon: <span className="text-lg">✨</span> },
              ]}
            />
          </Block>
        </>
      ),
    });
  }

  if (step.id === "current_db") {
    const source = supportOf(sourceEngine);
    body = frame({
      title: "The current database",
      lead: "Which database does the application run on today, and how big is it?",
      canContinue: Boolean(sourceEngine),
      skip: false,
      children: (
        <>
          <Block title="Database engine and version">
            <EngineVersionPicker
              options={engineOptions}
              value={answers["mig.source_engine"]}
              onChange={(value) => setAnswers({ "mig.source_engine": value, "app.existing_db": value })}
              versionPlaceholder="Version, e.g. 19c or 2019"
            />
            {source?.status === "sunset" && (
              <p className="mt-2 animate-fade-up rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                {source.label} is being retired in the organisation. {source.note}
              </p>
            )}
          </Block>
          <Block title="Where does it run?">
            <SingleChips options={optionsOf("mig.source_platform")} value={answers["mig.source_platform"] as string | undefined} onChange={(value) => setAnswer("mig.source_platform", value)} />
          </Block>
          <Block title="How much data is in it?" hint="A rough bucket is fine; the plan uses it for transfer time and sizing.">
            <SizePicker value={answers["mig.size_gb"] as number | undefined} onChange={(gb) => setAnswers({ "mig.size_gb": gb, "vol.current_gb": gb })} />
          </Block>
          <Block title="How critical is the application?">
            <SingleChips options={optionsOf("app.tier")} value={answers["app.tier"] as string | undefined} onChange={(value) => setAnswer("app.tier", value)} />
          </Block>
          <Block title="What kind of application is it?">
            <SingleChips options={optionsOf("app.type")} value={answers["app.type"] as string | undefined} onChange={(value) => setAnswer("app.type", value)} />
          </Block>
        </>
      ),
    });
  }

  if (step.id === "features") {
    const checklist = sourceEngine ? intake.engine_features.engines[sourceEngine] : undefined;
    const sourceLabel = engineOptions.find((option) => option.value === sourceEngine)?.label ?? "the database";
    const selected = (answers["data.special_features"] as string[] | undefined) ?? [];
    body = frame({
      title: `What the application uses in ${sourceLabel}`,
      lead: "Only metadata is needed here. Each item has a catalog query your DBA can run; none of them read table rows.",
      children: (
        <>
          <Block title="Engine features in use">
            {checklist ? (
              <FeatureChecklist engineLabel={sourceLabel} discoveryNote={checklist.discovery_note} features={checklist.features} selected={selected} onChange={(next) => setAnswer("data.special_features", next)} />
            ) : (
              <MultiChips options={optionsOf("data.special_features")} value={selected} onChange={(next) => setAnswer("data.special_features", next)} />
            )}
          </Block>
          <Block title="Stored procedures and in-database code" hint="PL/SQL, T-SQL, PL/pgSQL, SQL PL… how much business logic lives in the database?">
            <SingleChips options={optionsOf("data.proc_code")} value={answers["data.proc_code"] as string | undefined} onChange={(value) => setAnswer("data.proc_code", value)} />
          </Block>
          <Block title="Data shape" hint="Most existing databases are relational; tick more if the application also stores documents, time series or search indexes.">
            <MultiChips options={optionsOf("data.shape")} value={(answers["data.shape"] as string[] | undefined) ?? []} onChange={(next) => setAnswer("data.shape", next)} />
          </Block>
          <Block title="Anything else the reviewer should know" hint="Exceptions, special expectations, batch windows, downstream feeds. Metadata only, never customer data.">
            <textarea className="btn-ghost w-full px-3 py-2" rows={3} maxLength={2000} placeholder="e.g. nightly batch 01:00–04:00; three ETL feeds read directly from tables" value={(answers["app.notes"] as string) ?? ""} onChange={(event) => setAnswer("app.notes", event.target.value || undefined)} />
          </Block>
        </>
      ),
    });
  }

  if (step.id === "ownership") {
    const origin = answers["app.origin"] as string | undefined;
    const vendorSupport = answers["app.vendor_migration_support"] as string | undefined;
    // Team readiness is asked only when a vendor will not (or may not) help; internal teams are not asked (M11).
    const askTeam = origin === "vendor" && vendorSupport === "no_support";
    const vendorNamed = origin !== "vendor" || Boolean((answers["app.vendor_name"] as string | undefined)?.trim());
    body = frame({
      title: "Who owns and supports it",
      lead: "This decides whether the migration can be done in-house.",
      canContinue: vendorNamed,
      skip: origin !== "vendor",
      children: (
        <>
          <Block title="Who builds and supports the application?">
            <ChoiceCards
              value={origin}
              onChange={(value) => setAnswers({ "app.origin": value, ...(value === "internal" ? { "app.vendor_name": undefined, "app.vendor_migration_support": undefined, "team.source_skills": undefined, "team.target_skills": undefined, "team.capacity": undefined } : {}) })}
              choices={[
                { value: "internal", title: "Internal team", text: "We own the code and the schema." },
                { value: "vendor", title: "A vendor", text: "Bought or built for us; the vendor owns the code." },
              ]}
            />
          </Block>
          {origin === "vendor" && (
            <div className="animate-fade-up space-y-6">
              <Block title="Vendor name" hint="Required for a vendor application; it goes in the plan and the justification packet.">
                <input className="btn-ghost w-full max-w-sm px-3 py-2" maxLength={200} placeholder="e.g. Acme Software" value={(answers["app.vendor_name"] as string) ?? ""} onChange={(event) => setAnswer("app.vendor_name", event.target.value || undefined)} />
              </Block>
              <Block title="Will the vendor support the migration?">
                <SingleChips options={optionsOf("app.vendor_migration_support")} value={vendorSupport} onChange={(value) => setAnswer("app.vendor_migration_support", value)} />
                {vendorSupport === "yes_supported" && <p className="mt-2 text-xs text-emerald-800">Good: the team readiness check is not needed. Ask the vendor for the certified target platforms in writing.</p>}
                {vendorSupport === "unknown" && <p className="mt-2 text-xs text-slate-500">Ask them; until then DBCompass checks the in-house team as if the answer were no.</p>}
              </Block>
            </div>
          )}
          {(askTeam || vendorSupport === "unknown") && (
            <div className="animate-fade-up space-y-6 rounded-2xl border border-sand-200 bg-sand-50/60 p-4">
              <p className="text-sm font-semibold text-slate-800">Can the team do it? Three quick questions.</p>
              {["team.source_skills", "team.target_skills", "team.capacity"].map((fieldId) => (
                <Block key={fieldId} title={questions.get(fieldId)?.label ?? fieldId}>
                  <SingleChips options={optionsOf(fieldId)} value={answers[fieldId] as string | undefined} onChange={(value) => setAnswer(fieldId, value)} />
                </Block>
              ))}
            </div>
          )}
        </>
      ),
    });
  }

  if (step.id === "preference") {
    const requested = supportOf(requestedEngine);
    const licensed = requestedEngine ? commercial.includes(requestedEngine) : false;
    body = frame({
      title: "Do you already have a database in mind?",
      lead: "Optional. DBCompass compares your choice with its own ranking and tells you if it disagrees.",
      children: (
        <>
          <Block title="Database you have in mind">
            <EngineVersionPicker options={engineOptions} value={answers["app.requested_engine"]} onChange={(value) => setAnswers({ "app.requested_engine": value, ...(value ? {} : { "pref.licence_status": undefined }) })} />
            {requested?.status === "sunset" && <p className="mt-2 animate-fade-up text-xs text-amber-800">{requested.label} is being retired in the organisation and is not offered as a target.</p>}
          </Block>
          {licensed && (
            <Block title="Licences" hint="This engine needs a commercial licence; a short justification is required before a request is approved.">
              <SingleChips options={optionsOf("pref.licence_status")} value={answers["pref.licence_status"] as string | undefined} onChange={(value) => setAnswer("pref.licence_status", value)} />
            </Block>
          )}
          <Block title="Preferred cloud provider">
            <SingleChips options={optionsOf("pref.csp")} value={answers["pref.csp"] as string | undefined} onChange={(value) => setAnswer("pref.csp", value)} />
          </Block>
          <Block title="Where are the users?">
            <MultiChips options={optionsOf("geo.user_regions")} value={(answers["geo.user_regions"] as string[] | undefined) ?? []} onChange={(next) => setAnswer("geo.user_regions", next)} />
          </Block>
        </>
      ),
    });
  }

  if (step.id === "origin") {
    const origin = answers["app.origin"] as string | undefined;
    const certified = engineOf(answers["app.vendor_certified_db"]);
    const certifiedSupport = supportOf(certified);
    const vendorNamed = origin !== "vendor" || Boolean((answers["app.vendor_name"] as string | undefined)?.trim());
    body = frame({
      title: "Who is building it?",
      canContinue: vendorNamed,
      skip: origin !== "vendor",
      children: (
        <>
          <Block title="Is the application built by a vendor or by an internal team?">
            <ChoiceCards
              value={origin}
              onChange={(value) => setAnswers({ "app.origin": value, ...(value === "internal" ? { "app.vendor_name": undefined, "app.vendor_certified_db": undefined } : {}) })}
              choices={[
                { value: "internal", title: "Internal team", text: "We choose the database freely." },
                { value: "vendor", title: "A vendor", text: "Built or bought; the vendor may dictate the database." },
              ]}
            />
          </Block>
          {origin === "vendor" && (
            <div className="animate-fade-up space-y-6">
              <Block title="Vendor name" hint="Required for a vendor application; it goes in the plan and the justification packet.">
                <input className="btn-ghost w-full max-w-sm px-3 py-2" maxLength={200} placeholder="e.g. Acme Software" value={(answers["app.vendor_name"] as string) ?? ""} onChange={(event) => setAnswer("app.vendor_name", event.target.value || undefined)} />
              </Block>
              <Block title="Has the vendor said which database the application is built for?" hint="Leave empty if they have not. A certified engine is strongly favoured and counts as evidence in the justification.">
                <EngineVersionPicker
                  options={engineOptions}
                  value={answers["app.vendor_certified_db"]}
                  onChange={(value) => setAnswers({ "app.vendor_certified_db": value, "app.requested_engine": value, ...(value && commercial.includes(value.engine) ? {} : { "pref.licence_status": undefined }) })}
                />
                {certifiedSupport?.status === "sunset" && <p className="mt-2 animate-fade-up text-xs text-amber-800">{certifiedSupport.label} is being retired in the organisation and is not offered as a target.</p>}
                {certified && commercial.includes(certified) && (
                  <div className="mt-3 animate-fade-up">
                    <p className="mb-1 text-xs text-slate-500">This engine needs a commercial licence.</p>
                    <SingleChips options={optionsOf("pref.licence_status")} value={answers["pref.licence_status"] as string | undefined} onChange={(value) => setAnswer("pref.licence_status", value)} />
                  </div>
                )}
              </Block>
            </div>
          )}
        </>
      ),
    });
  }

  if (step.id === "essentials") {
    const tps = answers["wl.peak_tps"] as number | undefined;
    const requested = supportOf(requestedEngine);
    const vendorChoseEngine = Boolean(engineOf(answers["app.vendor_certified_db"]));
    body = frame({
      title: "The essentials",
      lead: "Rough answers are fine. Anything you skip is assumed from the criticality tier and listed with the results.",
      children: (
        <>
          <Block title="How critical will the application be?">
            <SingleChips options={optionsOf("app.tier")} value={answers["app.tier"] as string | undefined} onChange={(value) => setAnswer("app.tier", value)} />
          </Block>
          <Block title="What kind of application is it?">
            <SingleChips options={optionsOf("app.type")} value={answers["app.type"] as string | undefined} onChange={(value) => setAnswer("app.type", value)} />
          </Block>
          <Block title="What shape is the data?" hint="Tick every shape the application needs; DBCompass combines databases when one is not enough.">
            <MultiChips options={optionsOf("data.shape")} value={(answers["data.shape"] as string[] | undefined) ?? []} onChange={(next) => setAnswer("data.shape", next)} />
          </Block>
          <Block title="Expected data size in year one">
            <SizePicker value={answers["vol.current_gb"] as number | undefined} onChange={(gb) => setAnswer("vol.current_gb", gb)} />
          </Block>
          <Block title="Expected peak traffic">
            <SingleChips options={TRAFFIC_BUCKETS.map((item) => ({ value: String(item.tps), label: item.label }))} value={tps !== undefined ? String(tps) : undefined} onChange={(value) => setAnswer("wl.peak_tps", value ? Number(value) : undefined)} />
          </Block>
          <Block title="Where are the users?">
            <MultiChips options={optionsOf("geo.user_regions")} value={(answers["geo.user_regions"] as string[] | undefined) ?? []} onChange={(next) => setAnswer("geo.user_regions", next)} />
          </Block>
          <Block title="Preferred cloud provider">
            <SingleChips options={optionsOf("pref.csp")} value={answers["pref.csp"] as string | undefined} onChange={(value) => setAnswer("pref.csp", value)} />
          </Block>
          {!vendorChoseEngine && (
            <Block title="Do you already have a database in mind? (optional)">
              <EngineVersionPicker options={engineOptions} value={answers["app.requested_engine"]} onChange={(value) => setAnswers({ "app.requested_engine": value, ...(value ? {} : { "pref.licence_status": undefined }) })} />
              {requested?.status === "sunset" && <p className="mt-2 text-xs text-amber-800">{requested.label} is being retired in the organisation and is not offered as a target.</p>}
              {requestedEngine && commercial.includes(requestedEngine) && (
                <div className="mt-3 animate-fade-up">
                  <p className="mb-1 text-xs text-slate-500">This engine needs a commercial licence. Do we already own enough?</p>
                  <SingleChips options={optionsOf("pref.licence_status")} value={answers["pref.licence_status"] as string | undefined} onChange={(value) => setAnswer("pref.licence_status", value)} />
                </div>
              )}
            </Block>
          )}
        </>
      ),
    });
  }

  if (step.id === "application") {
    const personal = answers["sec.personal_data"] as string | undefined;
    const proxy = answers["cost.connection_proxy"] as boolean | undefined;
    const egress = answers["cost.egress_gb_month"] as number | undefined;
    body = frame({
      title: "The application around the database",
      lead: "Languages, data sensitivity and the environment it runs in. These change the design and the price.",
      children: (
        <>
          <Block title="Languages and frameworks used" hint="Tick everything that talks to the database; it decides drivers, ORMs and how much code a migration touches.">
            <MultiChips options={optionsOf("eco.languages")} value={(answers["eco.languages"] as string[] | undefined) ?? []} onChange={(next) => setAnswer("eco.languages", next)} />
          </Block>
          <Block title="Does the application hold personal data?" hint="Customer or employee data turns on customer-managed keys, auditing and masking by default.">
            <SingleChips options={optionsOf("sec.personal_data")} value={personal} onChange={(value) => setAnswer("sec.personal_data", value)} />
            {personal && personal !== "none" && <p className="mt-2 animate-fade-up text-xs text-teal-800">Encryption with your own keys, database auditing and data masking will be assumed on. Change them in the expert survey if that is wrong.</p>}
          </Block>
          <Block title="Compliance regimes that apply">
            <MultiChips options={optionsOf("sec.compliance")} value={(answers["sec.compliance"] as string[] | undefined) ?? []} onChange={(next) => setAnswer("sec.compliance", next)} />
          </Block>
          <Block title="Environments needed" hint="Each environment adds to the monthly cost (UAT at half, Dev at a quarter of production).">
            <MultiChips options={optionsOf("app.env")} value={(answers["app.env"] as string[] | undefined) ?? []} onChange={(next) => setAnswer("app.env", next)} />
          </Block>
          <Block title="How is the database reached?" hint="Private access adds private endpoints to the bill.">
            <SingleChips options={optionsOf("sec.network")} value={answers["sec.network"] as string | undefined} onChange={(value) => setAnswer("sec.network", value)} />
          </Block>
          <Block title="Connection pooling proxy in front of the database?" hint="RDS Proxy, PgBouncer or the service's own pooler. Recommended for tier 0 and 1 applications with many connections.">
            <SingleChips options={YES_NO} value={proxy === undefined ? undefined : proxy ? "yes" : "no"} onChange={(value) => setAnswer("cost.connection_proxy", value === undefined ? undefined : value === "yes")} />
          </Block>
          <Block title="Data leaving the cloud each month" hint="Internet or cross-cloud egress in GB (reports, feeds, API responses). Leave empty for the tier default.">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input type="number" min={0} className="btn-ghost w-36 px-3 py-1" placeholder="GB" value={egress ?? ""} onChange={(event) => setAnswer("cost.egress_gb_month", event.target.value ? Number(event.target.value) : undefined)} />
              GB a month
            </label>
          </Block>
        </>
      ),
    });
  }

  if (step.id === "priorities") {
    body = frame({
      title: "What matters most?",
      lead: "Drag the sliders, or leave them. The expert survey below is optional and can be skipped entirely.",
      skip: false,
      children: (
        <>
          <PrioritySliders sliders={schema.priority_sliders} fixedWeights={schema.fixed_dimension_weights} priorities={priorities} onChange={(next) => setDraft((current) => ({ ...current, priorities: next }))} />
          <details className="rounded-2xl border border-dashed border-sand-300 bg-sand-50/50 p-4">
            <summary className="cursor-pointer text-sm font-semibold text-slate-800">Expert survey (optional) — availability, security, operations, budget and more</summary>
            <p className="mb-3 mt-1 text-xs text-slate-500">Anything you leave empty is assumed from the criticality tier.</p>
            <ExpertSurvey schema={schema} answers={answers} onAnswer={setAnswer} migrating={migrating} />
          </details>
        </>
      ),
    });
  }

  if (step.id === "review") {
    const answered = Object.entries(answers).filter(([fieldId]) => questions.has(fieldId));
    const errors = report?.errors ?? [];
    body = frame({
      title: "Review and run",
      lead: "Check what you told us. Anything else is assumed and listed below.",
      canContinue: Boolean(report?.valid) && !submitting,
      continueLabel: "Get recommendations",
      skip: false,
      busy: submitting || checking,
      onNext: () => void submit(),
      children: (
        <>
          <div className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            {answered.map(([fieldId, value]) => (
              <div key={fieldId} className="flex justify-between gap-3 border-b border-sand-100 py-1.5">
                <span className="text-slate-500">{questions.get(fieldId)?.label}</span>
                <span className="text-right font-medium text-slate-800">{describeValue(questions.get(fieldId), value)}</span>
              </div>
            ))}
          </div>
          {errors.length > 0 && (
            <ul className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
              {errors.map((error) => (
                <li key={error.field_id}>
                  <span className="font-semibold">{questions.get(error.field_id)?.label ?? error.field_id}</span>: {error.message}
                </li>
              ))}
            </ul>
          )}
          {report && report.assumed_fields.length > 0 && (
            <details className="rounded-xl border border-sand-200 bg-white p-3 text-sm">
              <summary className="cursor-pointer font-semibold text-slate-800">{report.assumed_fields.length} answers will be assumed</summary>
              <ul className="mt-2 space-y-1 text-slate-700">
                {report.assumed_fields.map((field) => (
                  <li key={field.field_id}>
                    {questions.get(field.field_id)?.label ?? field.field_id}: <span className="font-medium">{describeValue(questions.get(field.field_id), field.value)}</span>
                    <span className="text-xs text-slate-500"> ({field.reason})</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {submitError && <p className="text-sm text-rose-600">{submitError}</p>}
          {submitting && <BusyOverlay label="Finding your database" steps={["Validating answers", "Filtering services", "Scoring seven dimensions", "Sizing and pricing", "Checking the supported list"]} />}
        </>
      ),
    });
  }

  return (
    <div>
      {header}
      {body}
    </div>
  );
}

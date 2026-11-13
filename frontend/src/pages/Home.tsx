import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { apiGet, type CurrentUser, type HealthResponse } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { CompassMark, DialBackdrop } from "../components/Brand";
import LogoMarquee from "../components/DatabaseLogos";
import Reveal from "../components/Reveal";

interface PricingStatus {
  snapshots: { csp: string; fetched_at: string | null; price_count: number }[];
  priced_services: number;
  not_priced_services: number;
}

type LoadState<T> = { status: "loading" } | { status: "ok"; data: T } | { status: "error"; message: string };

function useApiResource<T>(path: string): LoadState<T> {
  const { getAccessToken, isAuthenticated } = useAuth();
  const [state, setState] = useState<LoadState<T>>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    apiGet<T>(path, getAccessToken)
      .then((data) => !cancelled && setState({ status: "ok", data }))
      .catch((error: Error) => !cancelled && setState({ status: "error", message: error.message }));
    return () => {
      cancelled = true;
    };
  }, [path, getAccessToken, isAuthenticated]);

  return state;
}

/* ----------------------------------------------------------------- icons */

const ICON_PATHS: Record<string, ReactNode> = {
  rank: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  cost: <path d="M12 2v20M17 6.5C17 4.6 14.8 3.5 12 3.5S7 4.6 7 6.8c0 4.9 10 2.6 10 7.6 0 2.3-2.2 3.6-5 3.6s-5-1.2-5-3.4" />,
  design: <path d="M4 6h16M4 12h10M4 18h7M17 14l4 4-4 4" />,
  intake: <path d="M9 4h6v3H9zM7 5.5H5V21h14V5.5h-2M8.5 12l2 2 4-4M8.5 17.5h7" />,
  migrate: <path d="M3 7h13l-3-3M21 17H8l3 3M16 7l-3 3M8 17l3-3" />,
  shield: <path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3zM8.5 12l2.5 2.5 4.5-5" />,
  trace: <path d="M3 12h4l3-8 4 16 3-8h4" />,
  source: <path d="M4 4h12l4 4v12H4zM8 12h8M8 16h5M15 4v5h5" />,
  lock: <path d="M6 11h12v10H6zM8 11V7a4 4 0 0 1 8 0v4" />,
};

function Icon({ name, className = "h-5 w-5" }: { name: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICON_PATHS[name]}
    </svg>
  );
}

/* ----------------------------------------------------------------- hero */

interface RunRow {
  name: string;
  cloud: string;
  score: number;
  cut?: string; // filter that removes it in the example run
}

// An illustrative run, not live data: every name is a service in the knowledge base.
const RUN_ROWS: RunRow[] = [
  { name: "Amazon DocumentDB", cloud: "AWS", score: 0, cut: "Data shape" },
  { name: "Amazon RDS for PostgreSQL", cloud: "AWS", score: 86 },
  { name: "Oracle on Amazon EC2", cloud: "AWS", score: 0, cut: "Budget" },
  { name: "AlloyDB for PostgreSQL", cloud: "GCP", score: 83 },
  { name: "Azure Managed Redis", cloud: "Azure", score: 0, cut: "Add-on only" },
  { name: "Aurora PostgreSQL", cloud: "AWS", score: 91 },
  { name: "Azure Database for PostgreSQL", cloud: "Azure", score: 78 },
];

const PHASES = ["Candidates", "Filter", "Score", "Rank"] as const;
const PHASE_MS = 2200;
const ROW_HEIGHT = 46;

function useRunPhase(): number {
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setPhase((current) => (current + 1) % PHASES.length), PHASE_MS);
    return () => window.clearInterval(timer);
  }, []);
  return phase;
}

/** Row order for a phase: catalog order until ranking, then survivors by score and the removed ones below. */
function rowSlots(phase: number): number[] {
  const order = RUN_ROWS.map((_, index) => index);
  if (phase < 3) {
    return order;
  }
  const ranked = [...order].sort((left, right) => {
    const leftRow = RUN_ROWS[left];
    const rightRow = RUN_ROWS[right];
    if (Boolean(leftRow.cut) !== Boolean(rightRow.cut)) return leftRow.cut ? 1 : -1;
    return rightRow.score - leftRow.score;
  });
  const slots: number[] = [];
  ranked.forEach((rowIndex, slot) => {
    slots[rowIndex] = slot;
  });
  return slots;
}

function RunRowView({ row, slot, phase, rank }: { row: RunRow; slot: number; phase: number; rank: number | null }) {
  const removed = Boolean(row.cut) && phase >= 1;
  const scored = !row.cut && phase >= 2;
  const winner = rank === 1;
  return (
    <div
      className="absolute inset-x-0 px-3 transition-transform duration-700 [transition-timing-function:cubic-bezier(0.22,1,0.36,1)]"
      style={{ transform: `translateY(${slot * ROW_HEIGHT}px)`, height: ROW_HEIGHT }}
    >
      <div
        className={`flex h-[40px] items-center gap-3 rounded-xl px-3 transition-all duration-500 ${
          winner ? "bg-coral-500 text-white shadow-glow" : removed ? "bg-transparent opacity-45" : "bg-sand-50"
        }`}
      >
        <span
          className={`grid h-6 w-6 shrink-0 place-items-center rounded-full font-display text-[11px] font-bold transition-all duration-500 ${
            rank ? (winner ? "bg-white text-coral-600" : "bg-ink-900 text-white") : "bg-sand-200 text-transparent"
          }`}
        >
          {rank ?? "·"}
        </span>
        <span className={`min-w-0 flex-1 truncate text-[13px] font-semibold ${removed ? "line-through decoration-coral-500 decoration-2" : ""}`}>{row.name}</span>
        {removed ? (
          <span className="shrink-0 animate-fade-in rounded-full border border-coral-300 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-coral-700">{row.cut}</span>
        ) : (
          <>
            <span className={`hidden w-20 overflow-hidden rounded-full sm:block ${winner ? "bg-white/30" : "bg-sand-200"}`}>
              <span
                className={`block h-1.5 rounded-full transition-[width] duration-700 ${winner ? "bg-white" : "bg-coral-400"}`}
                style={{ width: scored ? `${row.score}%` : "0%" }}
              />
            </span>
            <span className={`w-7 shrink-0 text-right font-display text-sm font-bold tabular-nums transition-opacity duration-500 ${scored ? "opacity-100" : "opacity-0"}`}>
              {row.score}
            </span>
          </>
        )}
        <span className={`w-11 shrink-0 text-right text-[10px] font-bold uppercase tracking-wider ${winner ? "text-coral-50" : "text-slate-400"}`}>{row.cloud}</span>
      </div>
    </div>
  );
}

function EngineRun() {
  const phase = useRunPhase();
  const slots = rowSlots(phase);
  return (
    <div className="relative rounded-[1.75rem] bg-snow p-2 shadow-[0_40px_80px_-30px_rgba(37,31,28,0.55)] ring-1 ring-black/5">
      <div className="flex items-center justify-between px-3 pb-2 pt-2">
        <ol className="flex items-center gap-1" aria-label="Engine phases">
          {PHASES.map((label, index) => (
            <li
              key={label}
              className={`rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider transition-colors duration-300 ${
                index === phase ? "bg-ink-900 text-white" : index < phase ? "text-coral-600" : "text-slate-400"
              }`}
            >
              {label}
            </li>
          ))}
        </ol>
        <span className="hidden text-[10px] font-semibold uppercase tracking-widest text-slate-400 sm:block">Example run</span>
      </div>
      <div className="relative" style={{ height: RUN_ROWS.length * ROW_HEIGHT }}>
        {RUN_ROWS.map((row, index) => {
          const slot = slots[index];
          const rank = phase === 3 && !row.cut ? slot + 1 : null;
          return <RunRowView key={row.name} row={row} slot={slot} phase={phase} rank={rank} />;
        })}
      </div>
      <div className="mt-1 flex items-center justify-between rounded-2xl bg-ink-900 px-4 py-3 text-white">
        <span className="text-xs text-sand-200">Same answers in, same ranking out. Every step is in the trace.</span>
        <span className="flex items-center gap-1.5 text-[11px] font-semibold text-mist">
          <span className="h-1.5 w-1.5 rounded-full bg-teal-400" /> Deterministic
        </span>
      </div>
    </div>
  );
}

function Hero({ name }: { name: string | null }) {
  return (
    <section className="relative overflow-hidden bg-coral-500">
      <DialBackdrop />
      <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 pb-24 pt-14 lg:grid-cols-[1.05fr_1fr] lg:pb-28 lg:pt-20">
        <div className="stagger">
          <p className="inline-flex items-center gap-2 text-sm font-semibold text-ink-900/80">
            <span className="h-px w-8 bg-ink-900/50" />
            {name ? `Welcome back, ${name.split(" ")[0]}` : "Database advisory for AWS, Google Cloud and Azure"}
          </p>
          <h1 className="mt-5 font-display text-[2.4rem] font-extrabold leading-[1.04] tracking-[-0.03em] text-ink-950 sm:text-5xl lg:text-[3.35rem]">
            Answer a few questions.
            <span className="mt-1 block text-white">Get a database decision you can defend.</span>
          </h1>
          <p className="mt-6 max-w-lg text-base leading-relaxed text-ink-900/85 sm:text-lg">
            DBCompass filters the org's supported databases against your requirements, scores what is left,
            prices it on your cloud and plans the migration. No application code is ever read.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/assessments/new" className="btn-dark group px-5 py-3 text-base">
              Start an assessment
              <span aria-hidden="true" className="transition group-hover:translate-x-1">→</span>
            </Link>
            <Link to="/migrations/new" className="btn border-2 border-ink-900/80 px-5 py-3 text-base text-ink-950 hover:-translate-y-0.5 hover:bg-ink-900 hover:text-white">
              <Icon name="migrate" /> Plan a migration
            </Link>
          </div>
        </div>
        <div className="animate-fade-up [animation-delay:200ms]">
          <EngineRun />
        </div>
      </div>
    </section>
  );
}

/* ----------------------------------------------------------------- stats */

function StatsStrip({ pricing }: { pricing: LoadState<PricingStatus> }) {
  const serviceCount = pricing.status === "ok" ? pricing.data.priced_services + pricing.data.not_priced_services : null;
  const stats = [
    { value: serviceCount === null ? "40" : String(serviceCount), label: "database services in the catalog" },
    { value: "11", label: "engines on the org support list" },
    { value: "7", label: "scoring dimensions, fully traced" },
    { value: "2028", label: "on-prem exit deadline built in" },
  ];
  return (
    <section className="relative z-10 mx-auto -mt-10 max-w-6xl px-4">
      <div className="card grid grid-cols-2 divide-sand-200/70 overflow-hidden lg:grid-cols-4 lg:divide-x">
        {stats.map((stat, index) => (
          <Reveal key={stat.label} delayMs={index * 90} className="px-6 py-6">
            <p className="font-display text-4xl font-extrabold tracking-tight text-coral-600">{stat.value}</p>
            <p className="mt-1 text-sm text-slate-500">{stat.label}</p>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ----------------------------------------------------------------- features */

const FEATURES = [
  { icon: "rank", title: "Ranked recommendations", text: "Single databases or polyglot combinations, filtered by hard limits and scored on seven dimensions." },
  { icon: "cost", title: "Three cost tiers", text: "Budget, Balanced and Performance estimates from official price lists, licences included." },
  { icon: "design", title: "Design guidance", text: "Indexing, partitioning, caching, read replicas and connection pooling for the chosen engine." },
  { icon: "intake", title: "Guided intake", text: "One topic per screen, engine-specific feature checklists with metadata-only queries, and an \"I don't know\" on every step." },
  { icon: "migrate", title: "Migration planner", text: "Rehost, replatform or refactor compared over three years, with runbook, tools, risks and rollback." },
  { icon: "shield", title: "Justification gate", text: "Licensed engines need a reason. Claims are checked against the assessment before an approver decides." },
];

function Features() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-20">
      <Reveal className="max-w-2xl">
        <p className="eyebrow">What it does</p>
        <h2 className="mt-2 text-3xl font-bold text-slate-900 sm:text-4xl">From requirements to an approved plan</h2>
        <p className="mt-3 text-slate-600">Everything an application team needs to choose a database and defend the choice.</p>
      </Reveal>
      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((feature, index) => (
          <Reveal key={feature.title} delayMs={(index % 3) * 100}>
            <article className="card card-hover group h-full p-6">
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-coral-50 text-coral-600 transition duration-300 group-hover:rotate-6 group-hover:scale-110 group-hover:bg-coral-500 group-hover:text-white">
                <Icon name={feature.icon} />
              </span>
              <h3 className="mt-4 text-lg font-semibold text-slate-900">{feature.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{feature.text}</p>
            </article>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ----------------------------------------------------------------- how it works */

const STEPS = [
  { title: "Describe the app", text: "A five-minute guided intake: existing or new app, what it uses today, who owns it. Metadata only, never code.", to: "/assessments/new", cta: "Start" },
  { title: "Engine decides", text: "Filters remove what can't work, then deterministic scoring ranks the rest. Same input, same answer.", to: null, cta: null },
  { title: "Review the why", text: "See ranked options, cost tiers, the rule trace and why any service was left out.", to: "/history", cta: "History" },
  { title: "Plan and approve", text: "Build the migration plan, raise a request, and get a database approver's decision.", to: "/requests", cta: "Requests" },
];

function HowItWorks() {
  return (
    <section className="relative overflow-hidden bg-sand-200/50 py-20">
      <div className="mx-auto max-w-6xl px-4">
        <Reveal className="max-w-2xl">
          <p className="eyebrow">How to use it</p>
          <h2 className="mt-2 text-3xl font-bold text-slate-900 sm:text-4xl">Four steps, one source of truth</h2>
        </Reveal>
        <div className="relative mt-12 grid gap-8 lg:grid-cols-4">
          <div className="absolute left-0 right-0 top-6 hidden h-0.5 bg-gradient-to-r from-coral-500 via-coral-300 to-gold-300 lg:block" aria-hidden="true" />
          {STEPS.map((step, index) => (
            <Reveal key={step.title} delayMs={index * 120}>
              <div className="group relative">
                <span className="relative grid h-12 w-12 place-items-center rounded-full border-4 border-sand-100 bg-ink-900 font-display text-lg font-bold text-snow shadow-soft transition duration-300 group-hover:scale-110 group-hover:bg-coral-500">
                  {index + 1}
                </span>
                <h3 className="mt-4 text-lg font-semibold text-slate-900">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{step.text}</p>
                {step.to && (
                  <Link to={step.to} className="link-underline mt-3 inline-block text-sm font-semibold text-coral-700">
                    {step.cta} →
                  </Link>
                )}
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ----------------------------------------------------------------- databases and clouds */

const CLOUDS = [
  { name: "AWS", detail: "RDS, Aurora, DocumentDB, Keyspaces, ElastiCache, Oracle Database@AWS and self-managed EC2" },
  { name: "Google Cloud", detail: "Cloud SQL, AlloyDB, Memorystore, BigQuery, Oracle Database@Google Cloud and Compute Engine" },
  { name: "Azure", detail: "Azure SQL, SQL Managed Instance, PostgreSQL and MySQL Flexible Server, Cosmos DB for MongoDB and Oracle Database@Azure" },
];

function Databases() {
  return (
    <section className="py-20">
      <div className="mx-auto max-w-6xl px-4">
        <Reveal className="flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-2xl">
            <p className="eyebrow">Supported databases</p>
            <h2 className="mt-2 text-3xl font-bold text-slate-900 sm:text-4xl">Relational, document, key-value, wide-column and more</h2>
          </div>
          <p className="max-w-sm text-sm text-slate-500">A sample of the engines in the knowledge base. Every entry carries a source URL and a last-verified date.</p>
        </Reveal>
      </div>
      <Reveal className="mx-auto mt-10 max-w-7xl">
        <LogoMarquee />
      </Reveal>
      <div className="mx-auto mt-12 grid max-w-6xl gap-5 px-4 md:grid-cols-3">
        {CLOUDS.map((cloud, index) => (
          <Reveal key={cloud.name} delayMs={index * 100}>
            <div className="card card-hover group relative h-full overflow-hidden p-6">
              <span className="absolute -right-8 -top-8 h-24 w-24 rounded-full bg-sand-200/60 transition duration-500 group-hover:scale-[2.2] group-hover:bg-coral-50" />
              <p className="relative font-display text-xl font-bold text-slate-900">{cloud.name}</p>
              <p className="relative mt-2 text-sm leading-relaxed text-slate-600">{cloud.detail}</p>
            </div>
          </Reveal>
        ))}
      </div>
      <p className="mx-auto mt-4 max-w-6xl px-4 text-xs text-slate-500">On-prem is supported as a migration source, or as a "retain" option.</p>
    </section>
  );
}

/* ----------------------------------------------------------------- principles and status */

const PRINCIPLES = [
  { icon: "trace", title: "Deterministic and traced", text: "The engine, not the LLM, ranks. Every result shows which rules fired and why candidates were removed." },
  { icon: "source", title: "Every number has a source", text: "Prices, SLAs and limits come from the knowledge base and official price lists, never from the model." },
  { icon: "lock", title: "No code leaves the org", text: "DBCompass never reads application code. The LLM only sees your questionnaire answers and the engine's own trace." },
];

function StatusDot({ state }: { state: LoadState<unknown> }) {
  if (state.status === "ok") {
    return (
      <span className="relative flex h-2.5 w-2.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
      </span>
    );
  }
  return <span className={`h-2.5 w-2.5 rounded-full ${state.status === "error" ? "bg-rose-500" : "bg-slate-300 animate-pulse"}`} />;
}

function StatusRow<T>({ label, state, render }: { label: string; state: LoadState<T>; render: (data: T) => string }) {
  let text = "Checking…";
  if (state.status === "ok") {
    text = render(state.data);
  } else if (state.status === "error") {
    text = state.message;
  }
  return (
    <div className="flex items-center gap-3 py-2">
      <StatusDot state={state} />
      <span className="w-20 text-sm font-semibold text-slate-600">{label}</span>
      <span className="text-sm text-slate-800">{text}</span>
    </div>
  );
}

function PricesText(data: PricingStatus): string {
  const parts: string[] = [];
  for (const snapshot of data.snapshots) {
    const csp = snapshot.csp.toUpperCase();
    parts.push(snapshot.fetched_at ? `${csp} ${new Date(snapshot.fetched_at).toLocaleDateString()}` : `${csp} not priced`);
  }
  return `${parts.join(" · ")} (${data.priced_services} services priced)`;
}

function Principles({ health, me, pricing }: { health: LoadState<HealthResponse>; me: LoadState<CurrentUser>; pricing: LoadState<PricingStatus> }) {
  return (
    <section className="mx-auto grid max-w-6xl gap-10 px-4 pb-20 lg:grid-cols-[1.3fr_1fr]">
      <div>
        <Reveal>
          <p className="eyebrow">Built to be trusted</p>
          <h2 className="mt-2 text-3xl font-bold text-slate-900">Answers you can defend in review</h2>
        </Reveal>
        <div className="mt-8 space-y-4">
          {PRINCIPLES.map((principle, index) => (
            <Reveal key={principle.title} delayMs={index * 100}>
              <div className="group flex gap-4 rounded-2xl p-3 transition hover:bg-white hover:shadow-soft">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-coral-50 text-coral-600 transition group-hover:bg-coral-500 group-hover:text-white">
                  <Icon name={principle.icon} />
                </span>
                <div>
                  <h3 className="font-semibold text-slate-900">{principle.title}</h3>
                  <p className="mt-1 text-sm text-slate-600">{principle.text}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
      <Reveal delayMs={150}>
        <div className="card h-full p-6">
          <h2 className="text-sm font-bold uppercase tracking-[0.18em] text-slate-500">System status</h2>
          <div className="mt-3 divide-y divide-sand-100">
            <StatusRow label="Backend" state={health} render={(data) => `v${data.version}, database ${data.database}`} />
            <StatusRow label="Signed in" state={me} render={(data) => `${data.name} (${data.auth_mode})`} />
            <StatusRow label="Prices" state={pricing} render={PricesText} />
          </div>
        </div>
      </Reveal>
    </section>
  );
}

/* ----------------------------------------------------------------- final call to action */

function FinalCta() {
  return (
    <section className="mx-auto max-w-6xl px-4 pb-8">
      <Reveal>
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-coral-500 via-coral-600 to-sand-700 px-8 py-12 text-center shadow-glow sm:px-16">
          <div className="pointer-events-none absolute -right-10 -top-10 h-56 w-56 rounded-full bg-gold-300/30 blur-2xl animate-float" />
          <CompassMark className="relative mx-auto h-12 w-12" />
          <h2 className="relative mt-4 text-3xl font-bold text-snow">Ready to find your database?</h2>
          <p className="relative mx-auto mt-2 max-w-xl text-coral-50">A Quick assessment takes about five minutes. You can refine it in Expert mode later.</p>
          <div className="relative mt-6 flex flex-wrap justify-center gap-3">
            <Link to="/assessments/new" className="btn bg-snow px-5 py-3 text-base text-coral-700 hover:-translate-y-0.5 hover:shadow-lift">
              Start an assessment
            </Link>
            <Link to="/migrations/new" className="btn border border-white/40 px-5 py-3 text-base text-snow hover:-translate-y-0.5 hover:bg-white/10">
              Plan a migration
            </Link>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

export default function Home() {
  const health = useApiResource<HealthResponse>("/health");
  const me = useApiResource<CurrentUser>("/me");
  const pricing = useApiResource<PricingStatus>("/pricing/status");
  const name = me.status === "ok" ? me.data.name : null;

  return (
    <div>
      <Hero name={name} />
      <StatsStrip pricing={pricing} />
      <Features />
      <HowItWorks />
      <Databases />
      <Principles health={health} me={me} pricing={pricing} />
      <FinalCta />
    </div>
  );
}

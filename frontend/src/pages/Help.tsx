import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchGuide, fetchGuides, type Guide, type GuideSummary } from "../api/help";
import { fetchIntake, type DiscoveryQuery, type EngineFeature, type IntakeConfig } from "../api/intake";
import { useAuth } from "../auth/AuthProvider";
import MarkdownGuide from "../components/MarkdownGuide";
import { PageLoader } from "../components/Loader";

/* Help (M11): Guides, and Databases > features > queries/commands. Selection lives in the URL
   (?guide=… or ?db=…&feature=…) so a link to any query can be shared. */

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="shrink-0 rounded-lg border border-white/15 px-2 py-0.5 text-[11px] font-semibold text-sand-100 hover:bg-white/10"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function QueryBlock({ query }: { query: string }) {
  return (
    <div className="mt-2 flex items-start gap-2 rounded-xl bg-ink-900 p-3">
      <code className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed text-sand-100">{query}</code>
      <CopyButton text={query} />
    </div>
  );
}

function matches(text: string, search: string): boolean {
  return text.toLowerCase().includes(search.toLowerCase());
}

interface EngineEntry {
  id: string;
  label: string;
  status: string;
  note: string | null;
  discovery: DiscoveryQuery[];
  features: EngineFeature[];
}

function engineEntries(intake: IntakeConfig): EngineEntry[] {
  const entries: EngineEntry[] = [];
  Object.entries(intake.org_support.engines).forEach(([id, engine]) => {
    const list = intake.engine_features.engines[id];
    if (!list) return;
    entries.push({ id, label: engine.label, status: engine.status, note: list.discovery_note, discovery: list.discovery ?? [], features: list.features });
  });
  return entries;
}

function Breadcrumb({ items }: { items: { label: string; to?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-1 text-xs text-slate-500">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`} className="flex items-center gap-1">
          {index > 0 && <span aria-hidden="true">›</span>}
          {item.to ? (
            <Link to={item.to} className="hover:text-coral-700 hover:underline">
              {item.label}
            </Link>
          ) : (
            <span className="font-semibold text-slate-800">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

function EngineView({ engine, featureId }: { engine: EngineEntry; featureId: string | null }) {
  useEffect(() => {
    if (featureId) document.getElementById(`feature-${featureId}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [featureId]);
  const selected = engine.features.find((feature) => feature.feature === featureId);
  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Help", to: "/help" },
          { label: "Databases", to: "/help" },
          { label: engine.label, to: selected ? `/help?db=${engine.id}` : undefined },
          ...(selected ? [{ label: "Features" }, { label: selected.label }] : []),
        ]}
      />
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{engine.label}</h1>
        <p className="mt-1 text-sm text-slate-600">
          Queries and commands that return metadata only (names, counts, sizes, settings). They never read table rows, so the results are safe to
          paste into a ticket. Run them with a read-only DBA account; DBCompass never connects to a database.
        </p>
        {engine.note && <p className="mt-2 rounded-xl border border-gold-300 bg-gold-50 px-3 py-2 text-sm text-gold-900">{engine.note}</p>}
      </div>

      {engine.discovery.length > 0 && (
        <section>
          <h2 className="text-lg font-bold text-slate-900">General information</h2>
          <p className="text-xs text-slate-500">Version, size, load and code: the facts the assessment asks for.</p>
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            {engine.discovery.map((item) => (
              <article key={item.label} className="card p-4">
                <h3 className="font-semibold text-slate-900">{item.label}</h3>
                <QueryBlock query={item.query} />
                {item.note && <p className="mt-2 text-xs text-slate-500">{item.note}</p>}
              </article>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-lg font-bold text-slate-900">Features</h2>
        <p className="text-xs text-slate-500">How to check whether the database uses each engine-specific feature. These are the features the intake checklist asks about.</p>
        <div className="mt-3 space-y-3">
          {engine.features.map((feature) => (
            <article
              key={feature.feature}
              id={`feature-${feature.feature}`}
              className={`card scroll-mt-24 p-4 ${feature.feature === featureId ? "border-coral-400 ring-2 ring-coral-100" : ""}`}
            >
              <h3 className="font-semibold text-slate-900">{feature.label}</h3>
              <QueryBlock query={feature.how_to_check} />
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function GuideView({ slug, summaries }: { slug: string; summaries: GuideSummary[] }) {
  const { getAccessToken } = useAuth();
  const [guide, setGuide] = useState<Guide | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setGuide(null);
    setError(null);
    fetchGuide(slug, getAccessToken).then(setGuide).catch((loadError: Error) => setError(loadError.message));
  }, [slug, getAccessToken]);
  const title = summaries.find((item) => item.slug === slug)?.title ?? "Guide";
  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Help", to: "/help" }, { label: "Guides", to: "/help" }, { label: title }]} />
      {error && <p className="text-sm text-rose-700">Could not load this guide: {error}</p>}
      {!guide && !error && <div className="skeleton h-64 w-full" />}
      {guide && <MarkdownGuide markdown={guide.markdown} />}
    </div>
  );
}

function HelpHome({ engines, summaries }: { engines: EngineEntry[]; summaries: GuideSummary[] }) {
  return (
    <div className="space-y-6">
      <div>
        <p className="eyebrow">Help</p>
        <h1 className="mt-1 text-3xl font-bold text-slate-900">Everything you can look up directly</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          Guides to how DBCompass works, and for every supported database the queries and commands that answer the assessment's questions:
          size, version, load, and which engine-specific features are in use.
        </p>
      </div>
      <section>
        <h2 className="text-lg font-bold text-slate-900">Guides</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {summaries.map((guide) => (
            <Link key={guide.slug} to={`/help?guide=${guide.slug}`} className="card card-hover block p-4">
              <p className="font-semibold text-slate-900">{guide.title}</p>
              <p className="mt-1 text-sm text-slate-600">{guide.summary}</p>
            </Link>
          ))}
        </div>
      </section>
      <section>
        <h2 className="text-lg font-bold text-slate-900">Databases</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {engines.map((engine) => (
            <Link key={engine.id} to={`/help?db=${engine.id}`} className="card card-hover block p-4">
              <p className="font-semibold text-slate-900">{engine.label}</p>
              <p className="mt-1 text-xs text-slate-500">
                {engine.discovery.length} general queries · {engine.features.length} features
              </p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}

function Sidebar({ engines, summaries, guide, db, feature, search, onSearch }: {
  engines: EngineEntry[]; summaries: GuideSummary[]; guide: string | null; db: string | null; feature: string | null;
  search: string; onSearch: (value: string) => void;
}) {
  const [openEngines, setOpenEngines] = useState<Set<string>>(new Set(db ? [db] : []));
  useEffect(() => {
    if (db) setOpenEngines((current) => new Set(current).add(db));
  }, [db]);
  const toggle = (id: string) =>
    setOpenEngines((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const linkClass = (active: boolean) =>
    `block rounded-lg px-2 py-1 text-sm transition ${active ? "bg-coral-50 font-semibold text-coral-700" : "text-slate-700 hover:bg-sand-100"}`;

  return (
    <aside className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto">
      <input
        type="search"
        value={search}
        onChange={(event) => onSearch(event.target.value)}
        placeholder="Search features and queries"
        className="mb-3 w-full px-3 py-2 text-sm"
        aria-label="Search help"
      />
      <p className="px-2 text-[11px] font-bold uppercase tracking-wider text-slate-500">Guides</p>
      <ul className="mb-4 mt-1">
        {summaries.map((item) => (
          <li key={item.slug}>
            <Link to={`/help?guide=${item.slug}`} className={linkClass(guide === item.slug)}>
              {item.title}
            </Link>
          </li>
        ))}
      </ul>
      <p className="px-2 text-[11px] font-bold uppercase tracking-wider text-slate-500">Databases</p>
      <ul className="mt-1 space-y-0.5">
        {engines.map((engine) => {
          const featureHits = search ? engine.features.filter((item) => matches(item.label, search) || matches(item.how_to_check, search)) : engine.features;
          const discoveryHits = search ? engine.discovery.filter((item) => matches(item.label, search) || matches(item.query, search)) : engine.discovery;
          if (search && !featureHits.length && !discoveryHits.length && !matches(engine.label, search)) return null;
          const open = Boolean(search) || openEngines.has(engine.id);
          return (
            <li key={engine.id}>
              <div className="flex items-center">
                <button type="button" onClick={() => toggle(engine.id)} aria-expanded={open} aria-label={`${open ? "Collapse" : "Expand"} ${engine.label}`} className="grid h-6 w-6 place-items-center rounded text-coral-500 hover:bg-sand-100">
                  <svg viewBox="0 0 24 24" className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-90" : ""}`} fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M9 6l6 6-6 6" />
                  </svg>
                </button>
                <Link to={`/help?db=${engine.id}`} className={`flex-1 ${linkClass(db === engine.id && !feature)}`}>
                  {engine.label}
                </Link>
              </div>
              {open && (
                <ul className="ml-6 border-l border-sand-200 pl-2">
                  <li className="px-2 pt-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">Features</li>
                  {featureHits.map((item) => (
                    <li key={item.feature}>
                      <Link to={`/help?db=${engine.id}&feature=${item.feature}`} className={`${linkClass(db === engine.id && feature === item.feature)} !text-xs`}>
                        {item.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

export default function Help() {
  const { getAccessToken } = useAuth();
  const [params] = useSearchParams();
  const [intake, setIntake] = useState<IntakeConfig | null>(null);
  const [summaries, setSummaries] = useState<GuideSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const guide = params.get("guide");
  const db = params.get("db");
  const feature = params.get("feature");

  useEffect(() => {
    fetchIntake(getAccessToken).then(setIntake).catch((loadError: Error) => setError(loadError.message));
    fetchGuides(getAccessToken).then(setSummaries).catch(() => setSummaries([]));
  }, [getAccessToken]);

  const engines = useMemo(() => (intake ? engineEntries(intake) : []), [intake]);
  const engine = engines.find((item) => item.id === db) ?? null;

  if (error) return <p className="text-rose-700">Could not load Help: {error}</p>;
  if (!intake) return <PageLoader label="Loading Help" steps={["Fetching guides", "Fetching database queries"]} />;

  return (
    <div className="grid gap-8 lg:grid-cols-[16rem_1fr]">
      <Sidebar engines={engines} summaries={summaries} guide={guide} db={db} feature={feature} search={search} onSearch={setSearch} />
      <div className="min-w-0">
        {guide ? (
          <GuideView slug={guide} summaries={summaries} />
        ) : engine ? (
          <EngineView engine={engine} featureId={feature} />
        ) : (
          <HelpHome engines={engines} summaries={summaries} />
        )}
      </div>
    </div>
  );
}

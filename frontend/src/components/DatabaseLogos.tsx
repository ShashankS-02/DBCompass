import {
  siApachecassandra,
  siCouchbase,
  siGooglebigquery,
  siMongodb,
  siMysql,
  siOpensearch,
  siPostgresql,
  siRedis,
  type SimpleIcon,
} from "simple-icons";

/**
 * Engines and services DBCompass has in its knowledge base. Logos come from the
 * simple-icons package (CC0). Brands that simple-icons does not ship are shown as
 * monogram tiles in their brand colour instead.
 */
type LogoEntry = { name: string; icon: SimpleIcon } | { name: string; monogram: string; colour: string };

export const DATABASE_LOGOS: LogoEntry[] = [
  { name: "PostgreSQL", icon: siPostgresql },
  { name: "Oracle", monogram: "ORCL", colour: "#C74634" },
  { name: "MySQL", icon: siMysql },
  { name: "SQL Server", monogram: "SQL", colour: "#A91D22" },
  { name: "MongoDB", icon: siMongodb },
  { name: "Redis", icon: siRedis },
  { name: "Amazon Aurora", monogram: "AUR", colour: "#3B48CC" },
  { name: "Azure Cosmos DB", monogram: "COS", colour: "#0078D4" },
  { name: "AlloyDB", monogram: "ADB", colour: "#4285F4" },
  { name: "Apache Cassandra", icon: siApachecassandra },
  { name: "Couchbase", icon: siCouchbase },
  { name: "Db2", monogram: "Db2", colour: "#0F62FE" },
  { name: "BigQuery", icon: siGooglebigquery },
  { name: "OpenSearch", icon: siOpensearch },
];

function LogoGlyph({ entry }: { entry: LogoEntry }) {
  if ("icon" in entry) {
    return (
      <svg viewBox="0 0 24 24" className="h-9 w-9" role="img" aria-label={entry.name}>
        <path d={entry.icon.path} fill={`#${entry.icon.hex}`} />
      </svg>
    );
  }
  return (
    <span
      className="grid h-9 min-w-9 place-items-center rounded-lg px-1.5 font-display text-[11px] font-bold tracking-wide text-white"
      style={{ backgroundColor: entry.colour }}
      role="img"
      aria-label={entry.name}
    >
      {entry.monogram}
    </span>
  );
}

export function LogoTile({ entry }: { entry: LogoEntry }) {
  return (
    <div className="group flex w-40 shrink-0 flex-col items-center gap-2 rounded-2xl border border-sand-200/80 bg-white px-4 py-5 shadow-soft transition duration-300 hover:-translate-y-1.5 hover:border-coral-200 hover:shadow-lift">
      <span className="grayscale transition duration-300 group-hover:scale-110 group-hover:grayscale-0">
        <LogoGlyph entry={entry} />
      </span>
      <span className="text-center text-xs font-semibold text-slate-600 transition group-hover:text-slate-900">{entry.name}</span>
    </div>
  );
}

/** Two rows of logos scrolling in opposite directions; pauses while hovered. */
export default function LogoMarquee() {
  const half = Math.ceil(DATABASE_LOGOS.length / 2);
  const rows = [DATABASE_LOGOS.slice(0, half), DATABASE_LOGOS.slice(half)];
  return (
    <div className="space-y-4 [mask-image:linear-gradient(90deg,transparent,black_8%,black_92%,transparent)]">
      {rows.map((row, rowIndex) => (
        <div key={rowIndex} className="group/row overflow-hidden">
          <div
            className={`flex w-max py-2 animate-marquee group-hover/row:[animation-play-state:paused] ${rowIndex === 1 ? "[animation-direction:reverse]" : ""}`}
          >
            {[...row, ...row].map((entry, index) => (
              <div key={`${entry.name}-${index}`} className="pr-4" aria-hidden={index >= row.length}>
                <LogoTile entry={entry} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

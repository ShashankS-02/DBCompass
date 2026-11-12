/** Display names for engine and platform values used across the M6 pages. */
export const ENGINE_LABELS: Record<string, string> = {
  oracle: "Oracle",
  sql_server: "SQL Server",
  postgresql: "PostgreSQL",
  mysql: "MySQL",
  mariadb: "MariaDB",
  db2: "Db2",
  mongodb: "MongoDB",
  cassandra: "Cassandra",
  couchbase: "Couchbase",
  redis: "Redis",
  sybase: "Sybase ASE",
  informix: "Informix",
  vertica: "Vertica",
  proprietary: "proprietary engine",
};

export const PLATFORM_LABELS: Record<string, string> = { on_prem: "on-prem", aws: "AWS", gcp: "Google Cloud", azure: "Azure" };

export function engineLabel(engine: string | null | undefined): string {
  return engine ? ENGINE_LABELS[engine] ?? engine : "unknown engine";
}

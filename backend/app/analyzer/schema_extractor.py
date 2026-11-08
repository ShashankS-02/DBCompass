"""ORM models (SQLAlchemy, Django, JPA, Prisma, Mongoose) and migrations → join complexity and schema churn."""

import re
from dataclasses import dataclass, field

from app.analyzer.repo_fetch import SourceFile
from app.analyzer.scan_common import add_evidence, evidence, is_code_file, matching_lines
from app.models.repo import Signal

ENTITY = re.compile(
    # one marker per entity: SQLAlchemy __tablename__, Django models.Model, JPA @Entity, Prisma model, Mongoose model()
    r"(__tablename__\s*=|class\s+\w+\(\s*models\.Model\s*\)|@Entity\b|^\s*model\s+\w+\s*\{|mongoose\.model\s*\()"
)
RELATIONSHIP = re.compile(
    r"(\brelationship\s*\(|\bForeignKey\s*\(|models\.(ForeignKey|ManyToManyField|OneToOneField)\b|@(ManyToOne|OneToMany|ManyToMany|OneToOne)\b|@relation\b|\bref\s*:\s*['\"])"
)
JSON_COLUMN = re.compile(r"(\bJSONB?\b|JSONField|SqlTypes\.JSON|columnDefinition\s*=\s*\"jsonb\"|\bJson\b\s*[?@]?)")
VECTOR_COLUMN = re.compile(r"(\bVector\s*\(\d+\)|\bvector\(\d+\)|pgvector)")
MIGRATION_PATH = re.compile(
    r"(alembic/versions/[^/]+\.py$|/migrations/\d{4}_[^/]+\.py$|db/migration/V\d+[^/]*\.sql$|prisma/migrations/[^/]+/migration\.sql$|changelog[^/]*\.(xml|ya?ml|sql)$|migrations/\d+[^/]*\.(sql|js|ts)$)"
)
MIGRATION_SCHEMA = re.compile(r"(?i)\b(CREATE|ALTER|DROP)\s+TABLE\b|op\.(create_table|add_column|alter_column|drop_column)\b")


@dataclass
class OrmCounts:
    entities: int = 0
    relationships: int = 0
    json_columns: int = 0
    vector_columns: int = 0
    entity_evidence: list[str] = field(default_factory=list)
    relationship_evidence: list[str] = field(default_factory=list)
    vector_evidence: list[str] = field(default_factory=list)


def count_orm(files: list[SourceFile]) -> OrmCounts:
    """Entities, relationships, JSON and vector columns across ORM model code."""
    counts = OrmCounts()
    for source in files:
        if not (is_code_file(source) or source.path.endswith(".prisma")):
            continue
        for number, line, _ in matching_lines(source, ENTITY):
            counts.entities += 1
            add_evidence(counts.entity_evidence, evidence(source.path, number, line))
        for number, line, _ in matching_lines(source, RELATIONSHIP):
            counts.relationships += 1
            add_evidence(counts.relationship_evidence, evidence(source.path, number, line))
        for _ in matching_lines(source, JSON_COLUMN):
            counts.json_columns += 1
        for number, line, _ in matching_lines(source, VECTOR_COLUMN):
            counts.vector_columns += 1
            add_evidence(counts.vector_evidence, evidence(source.path, number, line))
    return counts


def join_signal(counts: OrmCounts) -> Signal | None:
    """data.joins from relationships per entity."""
    if counts.entities == 0:
        return None
    if counts.relationships == 0:
        value = "none"
    elif counts.relationships >= 6 or counts.relationships > counts.entities:
        value = "complex"
    else:
        value = "simple"
    proof = counts.relationship_evidence or counts.entity_evidence
    note = f"{counts.entities} entities, {counts.relationships} relationships"
    return Signal(field_id="data.joins", value=value, confidence=0.65, evidence=[note] + proof[:4])


def migration_signal(files: list[SourceFile]) -> Signal | None:
    """data.schema_volatility from how many schema migrations exist (no git history in a tarball)."""
    migrations = [source for source in files if MIGRATION_PATH.search(source.path) and MIGRATION_SCHEMA.search(source.text)]
    if not migrations:
        return None
    count = len(migrations)
    value = "rarely" if count < 5 else ("monthly" if count <= 30 else "constantly")
    proof = [f"{count} schema migration files"] + [f"{source.path}:1" for source in migrations[:4]]
    return Signal(field_id="data.schema_volatility", value=value, confidence=0.5, evidence=proof)


def scan_schema(files: list[SourceFile]) -> tuple[list[Signal], OrmCounts]:
    """Schema signals plus the raw counts (used by the LLM context)."""
    counts = count_orm(files)
    signals: list[Signal] = []
    for candidate in (join_signal(counts), migration_signal(files)):
        if candidate is not None:
            signals.append(candidate)
    if counts.vector_columns:
        signals.append(Signal(field_id="eco.vector", value=True, confidence=0.85, evidence=counts.vector_evidence))
        signals.append(Signal(field_id="data.shape", value=["vector"], confidence=0.7, evidence=counts.vector_evidence))
    if counts.entities:
        signals.append(Signal(field_id="wl.pattern", value="oltp", confidence=0.55, evidence=[f"{counts.entities} ORM entities (transactional model)"] + counts.entity_evidence[:3]))
    return signals, counts

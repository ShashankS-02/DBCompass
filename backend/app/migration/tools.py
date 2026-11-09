"""Doc 07 step 3: pick tools from the tool matrix in migration_tools.yaml."""

from app.models.knowledge import Csp
from app.models.migration import MigrationKnowledge, ToolMatrixRow, ToolRef, ToolSet

CSP_TOOL_PREFIX = "csp:"
SAME_ENGINE = "same"


def row_matches(row: ToolMatrixRow, source_engine: str | None, target_engine: str, csp: Csp) -> bool:
    """Empty lists match anything; targets 'same' means the engine does not change."""
    if row.sources and source_engine not in row.sources:
        return False
    if row.csps and csp not in row.csps:
        return False
    if not row.targets:
        return True
    if SAME_ENGINE in row.targets and target_engine == source_engine:
        return True
    return target_engine in row.targets


def matching_row(knowledge: MigrationKnowledge, source_engine: str | None, target_engine: str, csp: Csp) -> ToolMatrixRow:
    """First matching row (the last row in the YAML matches everything)."""
    for row in knowledge.tool_matrix:
        if row_matches(row, source_engine, target_engine, csp):
            return row
    return knowledge.tool_matrix[-1]


def tool_ref(tool_id: str, csp: Csp, knowledge: MigrationKnowledge) -> ToolRef:
    """Resolve a tool id (or 'csp:<kind>') to its name and documentation link."""
    if tool_id.startswith(CSP_TOOL_PREFIX):
        tool_id = getattr(knowledge.csp_tools[csp], tool_id[len(CSP_TOOL_PREFIX):])
    tool = knowledge.tools[tool_id]
    return ToolRef(id=tool_id, name=tool.name, url=tool.url, review=tool.review)


def tool_refs(tool_ids: list[str], csp: Csp, knowledge: MigrationKnowledge) -> list[ToolRef]:
    """Resolved tools without duplicates, in YAML order."""
    refs: list[ToolRef] = []
    seen: set[str] = set()
    for tool_id in tool_ids:
        ref = tool_ref(tool_id, csp, knowledge)
        if ref.id not in seen:
            seen.add(ref.id)
            refs.append(ref)
    return refs


def choose_tools(source_engine: str | None, target_engine: str, csp: Csp, needs_device: bool, knowledge: MigrationKnowledge) -> ToolSet:
    """Assessment, conversion, movement and validation tools, plus network (and device when needed)."""
    row = matching_row(knowledge, source_engine, target_engine, csp)
    supporting = [knowledge.csp_tools[csp].network]
    if needs_device:
        supporting.append(knowledge.csp_tools[csp].device)
    return ToolSet(
        assessment=tool_refs(row.assessment, csp, knowledge),
        schema_conversion=tool_refs(row.schema_conversion, csp, knowledge),
        data_movement=tool_refs(row.data_movement, csp, knowledge),
        validation=tool_refs(row.validation, csp, knowledge),
        supporting=tool_refs(supporting, csp, knowledge),
    )

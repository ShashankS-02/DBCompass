"""Evaluate a justification against its assessment: requirements, ranking and cost comparison."""

from dataclasses import dataclass

from app.justification.economics import compare_costs
from app.justification.evaluate import evaluate
from app.knowledge.loader import KnowledgeBundle
from app.migration.planner import resolve_values
from app.models.justification import JustificationConfig, JustificationEvaluation, JustificationInput
from app.models.licensing import LicensingConfig
from app.models.migration import MigrationKnowledge
from app.models.results import AssessmentResult


@dataclass
class GateKnowledge:
    """Everything the gate reads from the knowledge base."""

    knowledge: KnowledgeBundle
    licensing: LicensingConfig
    migration: MigrationKnowledge
    config: JustificationConfig


def evaluate_request(request: JustificationInput, assessment: AssessmentResult, gate: GateKnowledge) -> JustificationEvaluation:
    """Advisory verdict for one request, using the assessment's answers and ranked candidates."""
    answers = dict(assessment.input.answers)
    values, _ = resolve_values(answers, gate.knowledge)
    commercial_engines = gate.licensing.commercial_engines
    is_commercial = request.requested_engine in commercial_engines
    comparison = compare_costs(request, assessment.trace.scores, values, commercial_engines, gate.knowledge, gate.migration)
    return evaluate(request, values, comparison, is_commercial, gate.config)

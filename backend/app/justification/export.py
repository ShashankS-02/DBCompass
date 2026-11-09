"""Markdown export of a request's justification packet (for attaching to the org's request ticket)."""

from app.models.justification import CostedOption, DbRequest

VERDICT_LABELS = {
    "not_required": "Not required (no commercial licence)",
    "justified": "Justified",
    "needs_review": "Needs architecture review",
    "not_justified": "Not justified",
}


def money(value: float | None) -> str:
    """USD with thousands separators, or 'n/a'."""
    return "n/a" if value is None else f"${value:,.0f}"


def option_row(title: str, option: CostedOption | None, months: int) -> str:
    """One table row for a costed option."""
    if option is None:
        return f"| {title} | none passed the filters | | | |"
    star = "" if option.cost_complete else " *"
    return (f"| {title} | {option.service_name} ({option.engine}) | {money(option.monthly_usd)}{star} | "
            f"{money(option.licence_monthly_usd)} | {money(option.period_cost_usd)}{star} |")


def packet_markdown(request: DbRequest) -> str:
    """The full packet: request, verdict, reasons, cost comparison and audit trail."""
    data, result = request.input, request.evaluation
    lines = [
        f"# Database request: {data.application_name}", "",
        f"- Request: {request.id} ({data.kind.replace('_', ' ')}), status **{request.status}**",
        f"- Requested engine: **{data.requested_engine}**",
        f"- Requested by: {request.created_by_name}, {request.created_at:%d %b %Y}",
        f"- DBCompass verdict (advisory): **{VERDICT_LABELS[result.verdict]}**, {result.points:g} points", "",
        "## Justification", "", data.justification_text or "_none given_", "",
        "## Alternatives considered", "", data.alternatives_considered or "_none given_", "",
        "## Reasons", "", "| Reason | Status | Points | Evidence |", "|---|---|---|---|",
    ]
    evidence = {claim.reason_id: claim.evidence or "" for claim in data.reasons}
    for reason in result.reasons:
        lines.append(f"| {reason.label} | {reason.status} | {reason.points:g} | {evidence.get(reason.reason_id, '')} |")
    lines += ["", f"## Cost comparison ({result.months_compared} months, list prices)", "",
              "| Option | Service | Monthly | of which licence | Period total |", "|---|---|---|---|---|",
              option_row("Requested", result.requested_option, result.months_compared),
              option_row("Best licence-free", result.alternative_option, result.months_compared), "",
              f"- Refactor cost: {money(result.refactor_cost_usd)}",
              f"- Net saving with the licence-free option: {money(result.period_saving_usd)}",
              f"- Break-even: {'n/a' if result.break_even_months is None else f'{result.break_even_months:g} months'}", ""]
    lines += [f"- {message}" for message in result.messages]
    lines += ["", "## Audit trail", ""]
    lines += [f"- {event.at:%d %b %Y %H:%M} UTC: {event.actor_name} {event.action.replace('_', ' ')}" + (f": {event.note}" if event.note else "") for event in request.events]
    lines += ["", "_\\* not fully priced. Licence figures are list prices less the org discount in licensing.yaml._", ""]
    return "\n".join(lines)

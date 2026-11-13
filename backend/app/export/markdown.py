"""Markdown renderer for the design document."""

from app.export.document import Bullets, Chart, DesignDocument, Heading, Paragraph, Table


def cell(text: str) -> str:
    """Table cell text: pipes escaped, line breaks flattened."""
    return text.replace("|", "\\|").replace("\n", " ")


def table_lines(table: Table) -> list[str]:
    lines = ["| " + " | ".join(cell(header) for header in table.headers) + " |"]
    separators = []
    for index in range(len(table.headers)):
        separators.append("---:" if index in table.numeric_columns else "---")
    lines.append("| " + " | ".join(separators) + " |")
    for row in table.rows:
        lines.append("| " + " | ".join(cell(value) for value in row) + " |")
    return lines


def chart_table(chart: Chart) -> Table:
    """Markdown cannot draw charts, so a chart is written as its data table."""
    headers = [""] + chart.categories
    rows = []
    for series in chart.series:
        cells = [series.name]
        for value in series.values:
            cells.append(f"${value:,.0f}" if chart.value_label else f"{value:g}")
        rows.append(cells)
    return Table(headers, rows, numeric_columns=list(range(1, len(headers))))


def render_markdown(document: DesignDocument) -> str:
    """The document as GitHub-flavoured Markdown."""
    lines = [f"# {document.title}", ""]
    for subtitle in document.subtitle:
        lines.append(f"_{subtitle}_  ")
    lines.append("")
    for block in document.blocks:
        if isinstance(block, Heading):
            lines.append("#" * (block.level + 1) + " " + block.text)
        elif isinstance(block, Paragraph):
            if block.style == "muted":
                lines.append(f"_{block.text}_")
            elif block.style == "callout":
                lines.append(f"**{block.text}**")
            else:
                lines.append(block.text)
        elif isinstance(block, Bullets):
            for item in block.items:
                lines.append(f"- {item}")
        elif isinstance(block, Table):
            lines.extend(table_lines(block))
        elif isinstance(block, Chart):
            lines.append(f"**{block.title}** (chart in the PDF version)")
            lines.append("")
            lines.extend(table_lines(chart_table(block)))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

"""PDF renderer for the design document (reportlab, built-in Helvetica, theme colours)."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph as PdfParagraph, SimpleDocTemplate, Spacer, Table as PdfTable, TableStyle
from reportlab.platypus.flowables import Flowable

from app.export.document import Bullets, DesignDocument, Heading, Paragraph, Table

CORAL = colors.HexColor("#F96246")
TEAL = colors.HexColor("#486061")
TEAL_DARK = colors.HexColor("#223132")
SAND = colors.HexColor("#E9D3C3")
SAND_LIGHT = colors.HexColor("#FCF8F5")
MUTED = colors.HexColor("#5D7778")

# Helvetica covers Latin-1 only; these characters are written out instead.
REPLACEMENTS = {
    "→": "->", "←": "<-", "–": "-", "—": "-", "≤": "<=", "≥": ">=", "×": "x",
    "₹": "INR ", "…": "...", "‘": "'", "’": "'", "“": '"', "”": '"', "•": "-",
}


def latin1(text: str) -> str:
    """Text Helvetica can draw: known symbols replaced, anything else outside Latin-1 becomes '?'."""
    for symbol, replacement in REPLACEMENTS.items():
        text = text.replace(symbol, replacement)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def markup(text: str) -> str:
    return escape(latin1(text))


def build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=TEAL_DARK, spaceAfter=4)
    return {
        "title": ParagraphStyle("title", parent=body, fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=TEAL),
        "subtitle": ParagraphStyle("subtitle", parent=body, fontSize=8.5, textColor=MUTED, spaceAfter=1),
        "h1": ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=TEAL, spaceBefore=12, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=CORAL, spaceBefore=9, spaceAfter=4),
        "body": body,
        "muted": ParagraphStyle("muted", parent=body, fontSize=8.5, textColor=MUTED),
        "callout": ParagraphStyle("callout", parent=body, fontName="Helvetica-Bold", textColor=TEAL, spaceBefore=4),
        "cell": ParagraphStyle("cell", parent=body, fontSize=8, leading=10.5, spaceAfter=0),
        "cell_right": ParagraphStyle("cell_right", parent=body, fontSize=8, leading=10.5, spaceAfter=0, alignment=TA_RIGHT),
        "header": ParagraphStyle("header", parent=body, fontName="Helvetica-Bold", fontSize=8, leading=10.5, spaceAfter=0, textColor=colors.white),
    }


MIN_COLUMN_CHARS = 6
MIN_NUMERIC_COLUMN_CHARS = 13
MAX_COLUMN_CHARS = 60


def column_widths(table: Table, width: float) -> list[float]:
    """Columns sized by their longest text (clamped), so long text gets room and short columns stay narrow."""
    weights: list[float] = []
    for index, header in enumerate(table.headers):
        longest = len(header)
        for row in table.rows:
            longest = max(longest, len(row[index]))
        floor = MIN_NUMERIC_COLUMN_CHARS if index in table.numeric_columns else MIN_COLUMN_CHARS
        weights.append(min(max(longest, floor), MAX_COLUMN_CHARS))
    total = sum(weights)
    return [width * weight / total for weight in weights]


def table_flowable(table: Table, styles: dict[str, ParagraphStyle], width: float) -> PdfTable:
    data = [[PdfParagraph(markup(header), styles["header"]) for header in table.headers]]
    for row in table.rows:
        cells = []
        for index, value in enumerate(row):
            style = styles["cell_right"] if index in table.numeric_columns else styles["cell"]
            cells.append(PdfParagraph(markup(value), style))
        data.append(cells)
    flowable = PdfTable(data, colWidths=column_widths(table, width), repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, SAND),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for row_index in range(2, len(data), 2):
        commands.append(("BACKGROUND", (0, row_index), (-1, row_index), SAND_LIGHT))
    flowable.setStyle(TableStyle(commands))
    return flowable


def block_flowables(block: object, styles: dict[str, ParagraphStyle], width: float) -> list[Flowable]:
    if isinstance(block, Heading):
        return [PdfParagraph(markup(block.text), styles["h1" if block.level == 1 else "h2"])]
    if isinstance(block, Paragraph):
        return [PdfParagraph(markup(block.text), styles.get(block.style, styles["body"]))]
    if isinstance(block, Bullets):
        items = [ListItem(PdfParagraph(markup(item), styles["body"]), leftIndent=10) for item in block.items]
        return [ListFlowable(items, bulletType="bullet", bulletColor=CORAL, start="\u2022", bulletFontSize=8, leftIndent=10)]
    if isinstance(block, Table):
        return [table_flowable(block, styles, width), Spacer(1, 5)]
    return []


def draw_page_frame(canvas: object, document: SimpleDocTemplate) -> None:
    """Coral rule at the top and a footer with the page number."""
    canvas.saveState()
    page_width, page_height = A4
    canvas.setFillColor(CORAL)
    canvas.rect(0, page_height - 4 * mm, page_width, 4 * mm, stroke=0, fill=1)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(document.leftMargin, 10 * mm, "DBCompass - database design document")
    canvas.drawRightString(page_width - document.rightMargin, 10 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def render_pdf(document: DesignDocument) -> bytes:
    """The document as PDF bytes."""
    buffer = BytesIO()
    template = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
        title=latin1(document.title), author="DBCompass",
    )
    styles = build_styles()
    story: list[Flowable] = [PdfParagraph(markup(document.title), styles["title"]), Spacer(1, 4)]
    for subtitle in document.subtitle:
        story.append(PdfParagraph(markup(subtitle), styles["subtitle"]))
    story.append(Spacer(1, 8))
    for block in document.blocks:
        story.extend(block_flowables(block, styles, template.width))
    template.build(story, onFirstPage=draw_page_frame, onLaterPages=draw_page_frame)
    return buffer.getvalue()

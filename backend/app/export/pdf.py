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

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.spider import SpiderChart
from reportlab.graphics.shapes import Drawing, String

from app.export.document import Bullets, Chart, DesignDocument, Heading, Paragraph, Table

CORAL = colors.HexColor("#F96246")
TEAL = colors.HexColor("#486061")  # accent only, used sparingly
TEAL_DARK = colors.HexColor("#251F1C")  # warm ink for body text (name kept for the existing styles)
SAND = colors.HexColor("#E9D3C3")
SAND_LIGHT = colors.HexColor("#FCF8F5")
MUTED = colors.HexColor("#85776E")

INK = colors.HexColor("#4D433D")
GOLD = colors.HexColor("#D4AC47")
SERIES_COLOURS = [CORAL, INK, GOLD, TEAL]
CHART_HEIGHT = 190
LEGEND_ROW_HEIGHT = 12

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
        "title": ParagraphStyle("title", parent=body, fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=TEAL_DARK),
        "subtitle": ParagraphStyle("subtitle", parent=body, fontSize=8.5, textColor=MUTED, spaceAfter=1),
        "h1": ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=TEAL_DARK, spaceBefore=12, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=CORAL, spaceBefore=9, spaceAfter=4),
        "body": body,
        "muted": ParagraphStyle("muted", parent=body, fontSize=8.5, textColor=MUTED),
        "callout": ParagraphStyle("callout", parent=body, fontName="Helvetica-Bold", textColor=CORAL, spaceBefore=4),
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
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, SAND),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for row_index in range(2, len(data), 2):
        commands.append(("BACKGROUND", (0, row_index), (-1, row_index), SAND_LIGHT))
    flowable.setStyle(TableStyle(commands))
    return flowable


def series_colour(chart: Chart, index: int) -> colors.Color:
    """The chart's own colours when given (e.g. neutral for staying, coral for moving), else the palette."""
    if chart.colours:
        return colors.HexColor(chart.colours[index % len(chart.colours)])
    return SERIES_COLOURS[index % len(SERIES_COLOURS)]


def chart_title(chart: Chart, width: float, height: float) -> String:
    return String(0, height - 10, latin1(chart.title), fontName="Helvetica-Bold", fontSize=9, fillColor=TEAL_DARK)


def chart_legend(chart: Chart, y: float) -> Legend:
    """One row per series at the bottom of the drawing."""
    legend = Legend()
    legend.x = 0
    legend.y = y
    legend.alignment = "right"
    legend.fontName = "Helvetica"
    legend.fontSize = 7.5
    legend.dx = 7
    legend.dy = 7
    legend.deltay = LEGEND_ROW_HEIGHT
    legend.columnMaximum = len(chart.series)
    pairs = []
    for index, series in enumerate(chart.series):
        pairs.append((series_colour(chart, index), latin1(series.name)[:90]))
    legend.colorNamePairs = pairs
    return legend


def radar_drawing(chart: Chart, width: float) -> Drawing:
    """Spider chart of 0-100 scores, one outline per option."""
    legend_height = LEGEND_ROW_HEIGHT * len(chart.series) + 6
    height = CHART_HEIGHT + legend_height
    drawing = Drawing(width, height)
    spider = SpiderChart()
    spider.x = width / 2 - 85
    spider.y = legend_height + 4
    spider.width = 170
    spider.height = CHART_HEIGHT - 26
    spider.data = [series.values for series in chart.series]
    spider.labels = [latin1(label) for label in chart.categories]
    spider.strands.strokeWidth = 1.4
    spider.strands.fillColor = None
    for index in range(len(chart.series)):
        colour = series_colour(chart, index)
        spider.strands[index].strokeColor = colour
        spider.strands[index].fillColor = colors.Color(colour.red, colour.green, colour.blue, alpha=0.12)
    spider.spokes.strokeColor = SAND
    spider.strandLabels.fontSize = 0
    spider.spokeLabels.fontName = "Helvetica"
    spider.spokeLabels.fontSize = 7.5
    spider.spokeLabels.fillColor = MUTED
    drawing.add(spider)
    drawing.add(chart_title(chart, width, height))
    drawing.add(chart_legend(chart, legend_height - 6))
    return drawing


def bar_drawing(chart: Chart, width: float) -> Drawing:
    """Grouped vertical bars, one colour per series."""
    legend_height = LEGEND_ROW_HEIGHT * len(chart.series) + 6
    height = CHART_HEIGHT + legend_height
    drawing = Drawing(width, height)
    bars = VerticalBarChart()
    bars.x = 52
    bars.y = legend_height + 16
    bars.width = width - 64
    bars.height = CHART_HEIGHT - 44
    bars.data = [series.values for series in chart.series]
    bars.categoryAxis.categoryNames = [latin1(name) for name in chart.categories]
    bars.categoryAxis.labels.fontName = "Helvetica"
    bars.categoryAxis.labels.fontSize = 7.5
    bars.valueAxis.valueMin = 0
    bars.valueAxis.labels.fontName = "Helvetica"
    bars.valueAxis.labels.fontSize = 7
    bars.valueAxis.labelTextFormat = lambda value: f"${value:,.0f}"
    bars.valueAxis.gridStrokeColor = SAND
    bars.valueAxis.visibleGrid = True
    bars.barSpacing = 2
    bars.groupSpacing = 10
    for index in range(len(chart.series)):
        bars.bars[index].fillColor = series_colour(chart, index)
        bars.bars[index].strokeColor = None
    drawing.add(bars)
    drawing.add(chart_title(chart, width, height))
    if chart.value_label:
        drawing.add(String(0, legend_height + CHART_HEIGHT - 26, latin1(chart.value_label), fontName="Helvetica", fontSize=7, fillColor=MUTED))
    drawing.add(chart_legend(chart, legend_height - 6))
    return drawing


def chart_flowables(chart: Chart, width: float) -> list[Flowable]:
    """A chart as a drawing; empty data draws nothing."""
    if not chart.series or not chart.categories:
        return []
    drawing = radar_drawing(chart, width) if chart.kind == "radar" else bar_drawing(chart, width)
    return [Spacer(1, 4), drawing, Spacer(1, 8)]


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
    if isinstance(block, Chart):
        return chart_flowables(block, width)
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

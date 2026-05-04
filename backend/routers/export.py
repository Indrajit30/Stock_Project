import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _cache(request: Request):
    return request.app.state.cache


async def _get_report(ticker: str, cache):
    if cache:
        data = await cache.get(f"stock:{ticker}:report")
        if data:
            return data
    raise HTTPException(status_code=404, detail=f"No cached report for {ticker}. Trigger /api/stock/{ticker}/report first.")


@router.get("/stock/{ticker}/export/pdf")
async def export_pdf(ticker: str, request: Request):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ticker = ticker.upper()
    report = await _get_report(ticker, _cache(request))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph(f"<b>{report.get('company_name', ticker)} ({ticker})</b>", styles["Title"]))
    story.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | StockResearch AI", styles["Normal"]))
    story.append(Spacer(1, 0.3*cm))

    # Verdict badge
    verdict = report.get("verdict", "wait").upper()
    confidence = round(report.get("verdict_confidence", 0.5) * 100)
    verdict_colors = {"BUY": colors.green, "AVOID": colors.red, "WAIT": colors.orange}
    verdict_color = verdict_colors.get(verdict, colors.gray)
    verdict_table = Table([[f"{verdict} — {confidence}% confidence"]], colWidths=[16*cm])
    verdict_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), verdict_color),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 18),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(verdict_table)
    story.append(Spacer(1, 0.3*cm))

    # Summary
    story.append(Paragraph(report.get("plain_english_summary", ""), styles["BodyText"]))
    story.append(Spacer(1, 0.4*cm))

    # Bulls & Risks two-column
    bulls = report.get("three_bulls", [])
    risks = report.get("three_risks", [])
    bull_text = "<b>Bull Case</b><br/>" + "<br/>".join(f"• {b['text']}" for b in bulls) if bulls else "<b>Bull Case</b><br/>N/A"
    risk_text = "<b>Bear Case</b><br/>" + "<br/>".join(f"• {r['text']}" for r in risks) if risks else "<b>Bear Case</b><br/>N/A"
    two_col = Table([[Paragraph(bull_text, styles["BodyText"]), Paragraph(risk_text, styles["BodyText"])]], colWidths=[8*cm, 8*cm])
    story.append(two_col)
    story.append(Spacer(1, 0.4*cm))

    # Snowflake scores bar chart (simple table representation)
    sf = report.get("snowflake_scores", {})
    if sf:
        sf_data = [["Axis", "Score"]] + [[k.capitalize(), f"{v:.1f}/10"] for k, v in sf.items()]
        sf_table = Table(sf_data, colWidths=[8*cm, 8*cm])
        sf_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(sf_table)
        story.append(Spacer(1, 0.4*cm))

    # Financials table
    fin = report.get("financials", {})
    if fin:
        def _fmt(v):
            if v is None:
                return "N/A"
            if abs(v) >= 1e9:
                return f"${v/1e9:.1f}B"
            if abs(v) >= 1e6:
                return f"${v/1e6:.1f}M"
            return f"{v:.2f}"

        fin_data = [
            ["Metric", "Value"],
            ["Revenue TTM", _fmt(fin.get("revenue_ttm"))],
            ["Net Income TTM", _fmt(fin.get("net_income_ttm"))],
            ["P/E Ratio", _fmt(fin.get("pe_ratio"))],
            ["EV/EBITDA", _fmt(fin.get("ev_ebitda"))],
            ["Gross Margin", f"{fin.get('gross_margin', 0)*100:.1f}%" if fin.get("gross_margin") else "N/A"],
            ["Debt/Equity", _fmt(fin.get("debt_to_equity"))],
        ]
        fin_table = Table(fin_data, colWidths=[8*cm, 8*cm])
        fin_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(fin_table)

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("<i>Data sourced from SEC EDGAR, DefeatBeta API. Not financial advice.</i>", styles["Normal"]))

    doc.build(story)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={ticker}_report.pdf"},
    )


@router.get("/stock/{ticker}/export/excel")
async def export_excel(ticker: str, request: Request):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    ticker = ticker.upper()
    cache = _cache(request)
    report = await _get_report(ticker, cache)

    wb = openpyxl.Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(fill_type="solid", fgColor="1A1A2E")
    alt_fill = PatternFill(fill_type="solid", fgColor="F5F5F5")

    def _style_header(ws, row=1):
        for cell in ws[row]:
            cell.font = header_font
            cell.fill = header_fill

    def _auto_width(ws):
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 50)

    # Sheet 1 — Summary
    ws1 = wb.active
    ws1.title = "Summary"
    fin = report.get("financials", {})
    sf = report.get("snowflake_scores", {})
    rows = [
        ["Field", "Value"],
        ["Ticker", report.get("ticker")],
        ["Company", report.get("company_name")],
        ["Verdict", report.get("verdict")],
        ["Confidence", report.get("verdict_confidence")],
        ["Summary", report.get("plain_english_summary")],
        ["Revenue TTM", fin.get("revenue_ttm")],
        ["Net Income TTM", fin.get("net_income_ttm")],
        ["PE Ratio", fin.get("pe_ratio")],
        ["EV/EBITDA", fin.get("ev_ebitda")],
        ["Gross Margin", fin.get("gross_margin")],
        ["Debt/Equity", fin.get("debt_to_equity")],
        ["Market Cap", fin.get("market_cap")],
        ["Snowflake Value", sf.get("value")],
        ["Snowflake Growth", sf.get("growth")],
        ["Snowflake Health", sf.get("health")],
        ["Snowflake Momentum", sf.get("momentum")],
        ["Snowflake Smart Money", sf.get("smart_money")],
    ]
    for i, row in enumerate(rows):
        ws1.append(row)
        if i > 0 and i % 2 == 0:
            for cell in ws1[i + 1]:
                cell.fill = alt_fill
    _style_header(ws1)
    _auto_width(ws1)

    # Sheet 2 — Financials (placeholder — needs quarterly data)
    ws2 = wb.create_sheet("Financials")
    ws2.append(["Quarter", "Revenue", "Net Income", "Gross Margin"])
    _style_header(ws2)
    _auto_width(ws2)

    # Sheet 3 — Peer Comparison
    ws3 = wb.create_sheet("Peer Comparison")
    ws3.append(["Ticker", "Company", "Market Cap", "PE", "EV/EBITDA", "Gross Margin", "D/E"])
    if cache:
        peers = await cache.get(f"peers:{ticker}:list")
        if peers:
            for p in peers:
                ws3.append([p.get("ticker"), p.get("company_name"), p.get("market_cap"),
                             p.get("pe_ratio"), p.get("ev_ebitda"), p.get("gross_margin"), p.get("debt_to_equity")])
    _style_header(ws3)
    _auto_width(ws3)

    # Sheet 4 — Filing Diff
    ws4 = wb.create_sheet("Filing Diff")
    ws4.append(["Section", "Type", "Text"])
    if cache:
        diff = await cache.get(f"stock:{ticker}:filing_diff")
        if diff:
            for sec in diff.get("changed_sections", []):
                for p in sec.get("positives", []):
                    ws4.append([sec["section_name"], "Positive", p])
                for n in sec.get("negatives", []):
                    ws4.append([sec["section_name"], "Negative", n])
    _style_header(ws4)
    _auto_width(ws4)

    # Sheet 5 — Insider Trades
    ws5 = wb.create_sheet("Insider Trades")
    ws5.append(["Name", "Role", "Shares", "Value USD", "Trade Date", "10b5 Plan"])
    if cache:
        cluster = await cache.get(f"stock:{ticker}:insider_cluster")
        if cluster:
            for t in cluster.get("insiders", []):
                ws5.append([t.get("name"), t.get("role"), t.get("shares"),
                             t.get("value_usd"), t.get("trade_date"), t.get("is_10b5_plan")])
    _style_header(ws5)
    _auto_width(ws5)

    # Sheet 6 — Congressional Trades
    ws6 = wb.create_sheet("Congressional Trades")
    ws6.append(["Politician", "Chamber", "Party", "Transaction", "Amount", "Date"])
    if cache:
        cong = await cache.get(f"stock:{ticker}:congressional_trades")
        if cong:
            for t in cong:
                ws6.append([t.get("politician_name"), t.get("chamber"), t.get("party"),
                             t.get("transaction_type"), t.get("amount_range"), t.get("trade_date")])
    _style_header(ws6)
    _auto_width(ws6)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={ticker}_report.xlsx"},
    )

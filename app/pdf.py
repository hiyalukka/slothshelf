"""Weekly digest as a PDF (reportlab). Uses the Vera fonts that ship with reportlab."""
import io
import os
import re
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

_FONTS = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
for _name, _file in [("Vera", "Vera.ttf"), ("Vera-Bold", "VeraBd.ttf"), ("Vera-Italic", "VeraIt.ttf")]:
    if _name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(_name, os.path.join(_FONTS, _file)))

INK = colors.HexColor("#17211c")
MUTED = colors.HexColor("#5d6b63")
MOSS = colors.HexColor("#2f6b4f")
PAPER = colors.HexColor("#f3f6f3")
VERDICT = {"read": colors.HexColor("#2f6b4f"), "skim": colors.HexColor("#b7791f"), "skip": colors.HexColor("#8a8f8c")}
W, _H = A4
MARGIN = 18 * mm
CONTENT_W = W - 2 * MARGIN

_ST = {
    "title": ParagraphStyle("title", fontName="Vera-Bold", fontSize=24, leading=28, textColor=colors.white),
    "sub": ParagraphStyle("sub", fontName="Vera", fontSize=10, leading=14, textColor=colors.HexColor("#d5e6dc")),
    "h": ParagraphStyle("h", fontName="Vera-Bold", fontSize=14, leading=18, textColor=INK, spaceBefore=10, spaceAfter=6),
    "ct": ParagraphStyle("ct", fontName="Vera-Bold", fontSize=11.5, leading=15, textColor=INK),
    "meta": ParagraphStyle("meta", fontName="Vera", fontSize=8, leading=11, textColor=MUTED),
    "body": ParagraphStyle("body", fontName="Vera", fontSize=9.5, leading=13.5, textColor=INK, alignment=TA_LEFT),
    "bul": ParagraphStyle("bul", fontName="Vera", fontSize=9.2, leading=13, textColor=INK, leftIndent=10, bulletIndent=0),
    "try": ParagraphStyle("try", fontName="Vera-Italic", fontSize=9.2, leading=13, textColor=MOSS),
    "label": ParagraphStyle("label", fontName="Vera-Bold", fontSize=8, leading=11, textColor=MOSS, spaceBefore=4),
    "small": ParagraphStyle("small", fontName="Vera", fontSize=8.5, leading=12, textColor=MUTED),
}
_covered: dict[str, bool] = {}


def _covers(ch: str) -> bool:
    if ch not in _covered:
        font = pdfmetrics.getFont("Vera")
        _covered[ch] = ord(ch) in font.face.charToGlyph
    return _covered[ch]


def safe(text) -> str:
    """Drop glyphs the bundled font cannot draw (emoji, CJK), then escape for Paragraph markup."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = "".join(c if (c.isascii() or _covers(c)) else "" for c in text)
    return escape(text)


def _link(url: str, label: str) -> str:
    return f'<a href="{escape(url, {chr(34): "&quot;"})}" color="#2f6b4f">{label}</a>'


def _quality(doc: dict) -> str:
    return {"caption": "read from the public caption only", "note": "read from your pasted note"}.get(
        doc.get("source_quality") or "", ""
    )


def _entry(doc: dict, full: bool) -> Table:
    card = doc.get("card") or {}
    verdict = card.get("verdict") or "skim"
    title = safe(doc.get("title") or doc.get("url"))
    meta_bits = [verdict.upper(), safe(card.get("topic") or "")]
    meta_bits += [safe(t) for t in (card.get("tags") or [])[:4]]
    q = _quality(doc)
    if q:
        meta_bits.append(q)
    rows = [
        [Paragraph(_link(doc["url"], title), _ST["ct"])],
        [Paragraph(" | ".join(b for b in meta_bits if b), _ST["meta"])],
    ]
    if card.get("summary") and not (full and card.get("overview")):
        rows.append([Paragraph(safe(card["summary"]), _ST["body"])])
    if full:
        if card.get("overview"):
            rows.append([Paragraph("<b>The gist.</b> " + safe(card["overview"]), _ST["body"])])
        if card.get("key_points"):
            rows.append([Paragraph("Key points", _ST["label"])])
        for kp in card.get("key_points") or []:
            rows.append([Paragraph(safe(kp), _ST["bul"], bulletText="•")])
        if card.get("terms"):
            rows.append([Paragraph("Worth knowing", _ST["label"])])
            for t in card["terms"]:
                name, _, rest = t.partition(":")
                line = f"<b>{safe(name)}</b>: {safe(rest)}" if rest else safe(t)
                rows.append([Paragraph(line, _ST["bul"], bulletText="\u2022")])
        if card.get("try_this"):
            rows.append([Paragraph("Try this: " + safe(card["try_this"]), _ST["try"])])
        if card.get("reason"):
            rows.append([Paragraph("Why it is here: " + safe(card["reason"]), _ST["small"])])
        rows.append([Paragraph(safe(doc["url"])[:110], _ST["meta"])])
    if not full:
        for kp in (card.get("key_points") or [])[:3]:
            rows.append([Paragraph(safe(kp), _ST["bul"], bulletText="\u2022")])
    inner = Table(rows, colWidths=[CONTENT_W - 4 * mm])
    inner.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    outer = Table([["", inner]], colWidths=[1.6 * mm, CONTENT_W - 1.6 * mm])
    outer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), VERDICT.get(verdict, MUTED)),
        ("BACKGROUND", (1, 0), (1, 0), PAPER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (1, 0), (1, 0), 6), ("BOTTOMPADDING", (1, 0), (1, 0), 7),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 0),
    ]))
    return outer


def _stat_row(stats: dict) -> Table:
    cells = [("Saved", stats.get("links_in", 0)), ("Read by Gemma", stats.get("carded", 0)),
             ("Start here", stats.get("picked", 0)), ("Skip", stats.get("skipped_by_verdict", 0)),
             ("Unreadable", stats.get("failed", 0))]
    big = ParagraphStyle("big", fontName="Vera-Bold", fontSize=18, leading=22, textColor=MOSS)
    t = Table([[Paragraph(str(v), big) for _, v in cells], [Paragraph(k, _ST["meta"]) for k, _ in cells]],
              colWidths=[CONTENT_W / len(cells)] * len(cells))
    t.setStyle(TableStyle([("LINEBELOW", (0, 1), (-1, 1), 0.6, colors.HexColor("#cfd8d2")),
                           ("BOTTOMPADDING", (0, 1), (-1, 1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _footer(week: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Vera", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 10 * mm, f"SlothShelf weekly digest, {week}")
        canvas.drawRightString(W - MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def render_digest_pdf(report: dict) -> bytes:
    week = report.get("week") or "this week"
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=16 * mm,
                          bottomMargin=18 * mm, title=f"SlothShelf digest {week}", author="SlothShelf")
    frame = Frame(MARGIN, 18 * mm, CONTENT_W, A4[1] - 34 * mm, id="f", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=_footer(safe(week)))])

    head = Table([[Paragraph("Your weekly reading digest", _ST["title"])],
                  [Paragraph(f"Week {safe(week)}. What to read first, what to skim, what to let go.", _ST["sub"])]],
                 colWidths=[CONTENT_W])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), MOSS), ("LEFTPADDING", (0, 0), (-1, -1), 14),
                              ("TOPPADDING", (0, 0), (0, 0), 14), ("BOTTOMPADDING", (0, -1), (-1, -1), 14)]))
    story = [head, Spacer(1, 10), _stat_row(report.get("stats") or {}), Spacer(1, 6)]

    picks = report.get("picks") or []
    story.append(Paragraph("Start here", _ST["h"]))
    if picks:
        for p in picks:
            story += [KeepTogether([_entry(p, True)]), Spacer(1, 7)]
    else:
        story.append(Paragraph("Nothing to pick yet. Paste some links and let Gemma read them.", _ST["body"]))

    topics = report.get("topics") or []
    if topics:
        story.append(Paragraph("More on your shelf, by topic", _ST["h"]))
        for t in topics:
            story.append(Paragraph(f"{safe(t['topic'])} ({len(t['items'])})", _ST["ct"]))
            story.append(Spacer(1, 3))
            for it in t["items"]:
                story += [KeepTogether([_entry(it, False)]), Spacer(1, 4)]
            story.append(Spacer(1, 6))

    if report.get("skipped"):
        story.append(Paragraph("Safe to skip", _ST["h"]))
        for s in report["skipped"]:
            line = _link(s["url"], safe(s["title"])) + (f" ({safe(s['reason'])})" if s.get("reason") else "")
            story.append(Paragraph(line, _ST["small"], bulletText="•"))
    if report.get("failed"):
        story.append(Paragraph("Could not read", _ST["h"]))
        story.append(Paragraph("Instagram and other login-wall links often land here. Paste the caption on the same "
                               "line as the link and run it again.", _ST["small"]))
        story.append(Spacer(1, 3))
        for f in report["failed"]:
            story.append(Paragraph(f"{safe(f['url'])[:90]} ({safe(f['error'])[:70]})", _ST["small"], bulletText="•"))

    doc.build(story)
    return buf.getvalue()

"""Export a tailored resume as Word (.docx) or PDF.

Both exporters read the same content, in the same order as render_markdown():
the tailored text from the LLM, plus contact details, education and languages copied
from the profile. No new text is written here, so the faithfulness check still applies.
"""
import io
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, KeepTogether, Paragraph,
                                SimpleDocTemplate, Table, TableStyle)

ACCENT = "1F3A5F"      # dark blue used for the name and section headings
MARGIN_CM = 1.8
TEXT_WIDTH_CM = 21 - 2 * MARGIN_CM   # A4 width minus both side margins

# ---- PDF font ----
# DejaVu Sans (in the fonts/ folder next to this file) covers accents, special hyphens and
# dashes, curly quotes, arrows, math symbols, Greek, Cyrillic and more. If the files are
# missing we fall back to the built-in Helvetica, which only covers Western characters.
FONT_DIR = Path(__file__).parent / "fonts"
try:
    for _name, _file in (("ResumeSans", "DejaVuSans.ttf"),
                         ("ResumeSans-Bold", "DejaVuSans-Bold.ttf"),
                         ("ResumeSans-Italic", "DejaVuSans-Oblique.ttf")):
        pdfmetrics.registerFont(TTFont(_name, str(FONT_DIR / _file)))
    FONT, FONT_BOLD, FONT_ITALIC = "ResumeSans", "ResumeSans-Bold", "ResumeSans-Italic"
    UNICODE_FONT = True
except Exception:
    FONT, FONT_BOLD, FONT_ITALIC = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
    UNICODE_FONT = False


def _structure(t, profile):
    """The resume as plain data: (name, contact line, [(section title, [items])]).
    Item kinds: ("text", str), ("bullets", [str]), ("entry", left, right, [bullets])."""
    contact = " | ".join(x for x in [profile.email, profile.phone,
                                     profile.linkedin, profile.github] if x)
    sections = []
    if t.summary:
        sections.append(("Summary", [("text", t.summary)]))
    if t.skills:
        sections.append(("Skills", [("text", ", ".join(t.skills))]))
    if t.experience:
        sections.append(("Experience", [
            ("entry", ", ".join(x for x in [e.role, e.company] if x), e.duration, e.bullets)
            for e in t.experience]))
    if t.projects:
        sections.append(("Projects", [("entry", p.name, "", p.bullets) for p in t.projects]))
    if profile.education:
        sections.append(("Education", [
            ("entry", ", ".join(x for x in [e.degree, e.institution] if x), e.year, [])
            for e in profile.education]))
    if t.certifications:
        sections.append(("Certifications", [("bullets", t.certifications)]))
    if t.achievements:
        sections.append(("Achievements", [("bullets", t.achievements)]))
    if profile.languages:
        sections.append(("Languages", [("text", ", ".join(profile.languages))]))
    return profile.name or "", contact, sections


# =====================================================================
# Word
# =====================================================================
_PPR_AFTER_BORDER = ("w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
                     "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN",
                     "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind",
                     "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
                     "w:textDirection", "w:textAlignment", "w:textboxTightWrap",
                     "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr",
                     "w:pPrChange")


def _bottom_border(par):
    """Thin line under a paragraph (a real paragraph border, not a table or underscores)."""
    pPr = par._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for key, val in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", ACCENT)):
        bottom.set(qn(key), val)
    borders.append(bottom)
    pPr.insert_element_before(borders, *_PPR_AFTER_BORDER)   # keeps the schema element order


def to_docx_bytes(t, profile) -> bytes:
    name, contact, sections = _structure(t, profile)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)          # A4
    sec.left_margin = sec.right_margin = Cm(MARGIN_CM)
    sec.top_margin = sec.bottom_margin = Cm(1.5)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(2)

    doc.core_properties.title = f"{name} - Resume" if name else "Resume"
    doc.core_properties.author = name

    head = doc.add_paragraph()
    head.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = head.add_run(name)
    r.bold = True
    r.font.size = Pt(20)
    r.font.color.rgb = RGBColor.from_string(ACCENT)
    head.paragraph_format.space_after = Pt(1)

    if contact:
        c = doc.add_paragraph()
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cr = c.add_run(contact)
        cr.font.size = Pt(9.5)
        cr.font.color.rgb = RGBColor(0x59, 0x59, 0x59)

    for title, items in sections:
        h = doc.add_paragraph()
        hr = h.add_run(title.upper())
        hr.bold = True
        hr.font.size = Pt(11)
        hr.font.color.rgb = RGBColor.from_string(ACCENT)
        _bottom_border(h)
        h.paragraph_format.space_before = Pt(8)
        h.paragraph_format.space_after = Pt(3)
        h.paragraph_format.keep_with_next = True

        for item in items:
            kind = item[0]
            if kind == "text":
                doc.add_paragraph(item[1])
            elif kind == "bullets":
                for b in item[1]:
                    doc.add_paragraph(b, style="List Bullet").paragraph_format.space_after = Pt(1)
            else:
                _, left, right, bullets = item
                p = doc.add_paragraph()
                pf = p.paragraph_format
                pf.space_before = Pt(4)
                pf.space_after = Pt(1)
                pf.keep_with_next = bool(bullets)
                pf.tab_stops.add_tab_stop(Cm(TEXT_WIDTH_CM), WD_TAB_ALIGNMENT.RIGHT)
                p.add_run(left).bold = True
                if right:
                    p.add_run("\t")
                    rr = p.add_run(right)
                    rr.italic = True
                    rr.font.color.rgb = RGBColor(0x59, 0x59, 0x59)
                for b in bullets:
                    doc.add_paragraph(b, style="List Bullet").paragraph_format.space_after = Pt(1)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# =====================================================================
# PDF
# =====================================================================
# invisible or layout-only characters that would otherwise show as boxes
_INVISIBLE = {"\u00a0": " ", "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "", "\u00ad": ""}
# lookalikes for the Helvetica fallback only
_ASCII_FALLBACK = {"\u2011": "-", "\u2212": "-", "\ufb01": "fi", "\ufb02": "fl",
                   "\u2192": "->", "\u2265": ">=", "\u2264": "<="}


def _pdf_text(s) -> str:
    """Clean and escape text for reportlab's mini-markup. Any character the font cannot
    draw becomes '?' instead of a black box."""
    s = "".join(_INVISIBLE.get(ch, ch) for ch in str(s))
    if UNICODE_FONT:
        glyphs = pdfmetrics.getFont(FONT).face.charToGlyph
        s = "".join(ch if ord(ch) in glyphs else "?" for ch in s)
    else:
        s = "".join(_ASCII_FALLBACK.get(ch, ch) for ch in s)
        s = s.encode("cp1252", "replace").decode("cp1252")
    return escape(s)


def to_pdf_bytes(t, profile) -> bytes:
    name, contact, sections = _structure(t, profile)
    accent = colors.HexColor("#" + ACCENT)
    grey = colors.HexColor("#595959")

    base = ParagraphStyle("base", fontName=FONT, fontSize=9.5, leading=12.5,
                          bulletFontName=FONT)
    name_st = ParagraphStyle("name", parent=base, fontName=FONT_BOLD, fontSize=20,
                             leading=24, alignment=TA_CENTER, textColor=accent)
    contact_st = ParagraphStyle("contact", parent=base, fontSize=9, alignment=TA_CENTER,
                                textColor=grey)
    head_st = ParagraphStyle("head", parent=base, fontName=FONT_BOLD, fontSize=11,
                             textColor=accent, spaceBefore=8, spaceAfter=1, keepWithNext=1)
    title_st = ParagraphStyle("title", parent=base, fontName=FONT_BOLD)
    right_st = ParagraphStyle("right", parent=base, fontName=FONT_ITALIC,
                              alignment=TA_RIGHT, textColor=grey)
    bullet_st = ParagraphStyle("bullet", parent=base, leftIndent=14, bulletIndent=4, spaceAfter=1)

    story = [Paragraph(_pdf_text(name), name_st)]
    if contact:
        story.append(Paragraph(_pdf_text(contact), contact_st))

    # reportlab frames have 6pt padding on each side, so the table must be 12pt narrower
    right_w = 4 * cm
    left_w = TEXT_WIDTH_CM * cm - 12 - right_w
    for title, items in sections:
        rule = HRFlowable(width="100%", thickness=0.8, color=accent, spaceAfter=3)
        rule.keepWithNext = 1
        story += [Paragraph(_pdf_text(title.upper()), head_st), rule]

        for item in items:
            kind = item[0]
            if kind == "text":
                story.append(Paragraph(_pdf_text(item[1]), base))
            elif kind == "bullets":
                story += [Paragraph(_pdf_text(b), bullet_st, bulletText="\u2022") for b in item[1]]
            else:
                _, left, right, bullets = item
                row = Table([[Paragraph(_pdf_text(left), title_st),
                              Paragraph(_pdf_text(right), right_st)]],
                            colWidths=[left_w, right_w], spaceBefore=4, spaceAfter=1)
                row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                         ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                         ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                         ("TOPPADDING", (0, 0), (-1, -1), 0),
                                         ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
                bps = [Paragraph(_pdf_text(b), bullet_st, bulletText="\u2022") for b in bullets]
                story.append(KeepTogether([row] + bps[:1]))   # no heading left alone at a page end
                story += bps[1:]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4,
                      leftMargin=MARGIN_CM * cm, rightMargin=MARGIN_CM * cm,
                      topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                      title=f"{name} - Resume" if name else "Resume", author=name).build(story)
    return buf.getvalue()
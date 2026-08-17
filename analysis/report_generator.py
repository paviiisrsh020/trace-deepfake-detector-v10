"""
report_generator.py
--------------------
Generates a one-page-plus forensic summary PDF for a completed scan:
verdict, alteration %, technique classification, signal breakdown, and
the top evidence frame with its heatmap overlay.
"""

import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, HRFlowable
)

AMBER = colors.HexColor("#e8862e")
RED = colors.HexColor("#c93a3f")
GREEN = colors.HexColor("#1f9d63")
INK = colors.HexColor("#1a1f26")
MUTED = colors.HexColor("#5c6b7a")


def build_report(payload, job_dir, out_path):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title2", parent=styles["Title"], fontSize=22, textColor=INK, spaceAfter=2)
    sub_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=9.5, textColor=MUTED, spaceAfter=14)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12.5, textColor=INK, spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, textColor=INK, leading=15)

    verdict = payload.get("verdict") or "N/A"
    verdict_color = RED if verdict == "FAKE" else GREEN
    pct = payload.get("alteration_pct")

    doc = SimpleDocTemplate(out_path, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                             leftMargin=0.7 * inch, rightMargin=0.7 * inch)
    story = []

    story.append(Paragraph("TRACE — Forensic Scan Report", title_style))
    story.append(Paragraph(f"Generated {datetime.now().strftime('%d %b %Y, %H:%M')} · Job ID {payload.get('job_id','')}", sub_style))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#ddd"), thickness=1))
    story.append(Spacer(1, 12))

    verdict_style = ParagraphStyle("Verdict", parent=styles["Title"], fontSize=26, textColor=verdict_color,
                                    leading=32, spaceAfter=10)
    story.append(Paragraph(f"{verdict} — {pct if pct is not None else 'N/A'}% likely altered", verdict_style))
    story.append(Paragraph(payload.get("explanation") or "", body))
    story.append(Spacer(1, 10))

    tech = payload.get("technique")
    if tech:
        story.append(Paragraph("Manipulation technique (heuristic)", h2))
        story.append(Paragraph(f"<b>{tech.get('technique')}</b>", body))
        story.append(Paragraph(tech.get("technique_desc", ""), body))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Signal breakdown (video)", h2))
    top_frame = None
    if payload.get("frames"):
        top_frame = max(payload["frames"], key=lambda f: f["score"])
    if top_frame:
        sig = top_frame["signals"]
        data = [
            ["Signal", "Score"],
            ["Error level analysis (ELA)", f"{round(sig['ela']*100)}%"],
            ["Noise-residual inconsistency", f"{round(sig['noise_inconsistency']*100)}%"],
            ["Frequency-domain artifact", f"{round(sig['frequency_artifact']*100)}%"],
            ["Boundary-blend seam", f"{round(sig['boundary_blend']*100)}%"],
        ]
        t = Table(data, colWidths=[3.6 * inch, 1.2 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1f26")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ddd")),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))

        img_rel = top_frame.get("image", "")
        img_name = os.path.basename(img_rel)
        img_path = os.path.join(job_dir, img_name)
        if os.path.exists(img_path):
            story.append(Paragraph("Highest-scoring evidence frame", h2))
            story.append(RLImage(img_path, width=4.4 * inch, height=3.3 * inch))
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"Frame at {top_frame['timestamp']}s — {round(top_frame['score']*100)}% altered. "
                "Red/yellow heatmap regions and yellow boxes mark the strongest localized evidence.",
                sub_style,
            ))

    if payload.get("audio"):
        a = payload["audio"]
        story.append(Paragraph("Audio signal", h2))
        story.append(Paragraph(
            f"Audio alteration score: {round(a['score']*100)}% — "
            f"roll-off naturalness {round(a['signals']['rolloff_naturalness']*100)}%, "
            f"discontinuity {round(a['signals']['discontinuity']*100)}%, "
            f"spectral flatness {round(a['signals']['spectral_flatness']*100)}%.",
            body,
        ))

    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#ddd"), thickness=1))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "This report is produced by a classical forensic signal-analysis baseline (ELA, noise-residual, "
        "frequency-domain, boundary-blend), not a trained deep-learning classifier. Treat results as a "
        "first-pass indicator rather than a definitive verdict.",
        sub_style,
    ))

    doc.build(story)
    return out_path

"""Vector PDF Reference Sheet and Snapshot Exporter using ReportLab and PySide6."""

import os
from typing import List, Optional, Set
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

from core.models import Neck
from core.resolver import ActiveStringState, FretboardResolver
from core.voicing_solver import VoicingMatch


class CopedantPdfExporter:
    @classmethod
    def export_neck_sheet(
        cls,
        filepath: str,
        neck: Neck,
        bar_fret: int,
        engaged_levers: Set[str],
        active_pocket: Set[int],
        target_root: Optional[str] = None,
        target_chord: Optional[str] = None,
        voicing_matches: Optional[List[VoicingMatch]] = None,
    ) -> None:
        """Generates a landscape reference PDF sheet for the active setup."""
        doc = SimpleDocTemplate(
            filepath,
            pagesize=landscape(letter),
            leftMargin=0.5 * inch,
            rightMargin=0.5 * inch,
            topMargin=0.4 * inch,
            bottomMargin=0.4 * inch,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "SheetTitle",
            parent=styles["Heading1"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1a1a1c"),
            fontName="Helvetica-Bold",
        )
        subtitle_style = ParagraphStyle(
            "SheetSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#555a64"),
        )
        section_style = ParagraphStyle(
            "SectionHeader",
            parent=styles["Heading3"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#0d6efd"),
            fontName="Helvetica-Bold",
        )

        story = []

        # 1. Document Header
        chord_info = f" | Target Analysis: {target_root} {target_chord}" if target_root and target_root != "None" else ""
        levers_str = " + ".join(sorted(list(engaged_levers))) if engaged_levers else "None (Open)"
        pocket_str = " - ".join(map(str, sorted(list(active_pocket)))) if active_pocket else "All"

        story.append(Paragraph(f"Pedal Steel Reference Sheet — {neck.name}", title_style))
        story.append(
            Paragraph(
                f"Position: Fret {bar_fret} | Engaged Controllers: {levers_str} | Active Grip: [{pocket_str}]{chord_info}",
                subtitle_style,
            )
        )
        story.append(Spacer(1, 10))

        # 2. Copedant Matrix Table
        story.append(Paragraph("COPEDANT MATRIX & OPEN TUNING", section_style))
        story.append(Spacer(1, 4))

        controllers = []
        for pid in sorted(neck.pedals.keys()):
            controllers.append(("P", pid, neck.pedals[pid]))
        for lid in sorted(neck.knee_levers.keys()):
            controllers.append(("L", lid, neck.knee_levers[lid]))

        copedant_headers = ["Str", "Open", "MIDI"] + [c[1] for c in controllers]
        copedant_rows = [copedant_headers]

        for s_idx in range(neck.string_count):
            str_num = s_idx + 1
            sp = neck.open_tuning[s_idx] if s_idx < len(neck.open_tuning) else None
            note_label = sp.note_name if sp else ""
            midi_label = str(sp.midi_note) if sp else ""

            row = [str(str_num), note_label, midi_label]
            for _, _, change_obj in controllers:
                delta = change_obj.changes.get(str_num, 0)
                txt = f"+{delta}" if delta > 0 else (str(delta) if delta < 0 else "-")
                row.append(txt)
            copedant_rows.append(row)

        copedant_table = Table(copedant_rows, hAlign="LEFT")
        copedant_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9ecef")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#212529")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ced4da")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )
        story.append(copedant_table)
        story.append(Spacer(1, 14))

        # 3. Active Fret Voicing Breakdown
        story.append(Paragraph(f"SOUNDING STRINGS AT FRET {bar_fret}", section_style))
        story.append(Spacer(1, 4))

        active_states = FretboardResolver.resolve_neck_state(
            neck=neck,
            fret=bar_fret,
            engaged_levers=engaged_levers,
            target_root_name=target_root if target_root != "None" else None,
            target_chord_type=target_chord,
        )

        voicing_headers = ["String", "Sounding Pitch", "MIDI", "Interval Role", "In Active Grip"]
        voicing_rows = [voicing_headers]

        for s in active_states:
            in_grip = "YES" if s.string_number in active_pocket else "-"
            role = s.interval_label if s.interval_label else "-"
            voicing_rows.append([
                f"String {s.string_number}",
                s.active_note_name,
                str(s.active_midi),
                role,
                in_grip,
            ])

        voicing_table = Table(voicing_rows, colWidths=[1.1 * inch, 1.3 * inch, 0.9 * inch, 1.2 * inch, 1.1 * inch], hAlign="LEFT")
        voicing_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )
        story.append(voicing_table)

        doc.build(story)
import csv
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

BASE = Path("/tmp/claude-0/-home-user-Lukacino/5fb15e14-3e9c-5162-bbd0-928805449cf5/scratchpad/es2008")
ANALYSIS = BASE / "analysis_full"
OUT_PDF = BASE / "ES_2008_2026_Backtest_Report.pdf"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=24, leading=28, spaceAfter=6, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="SubTitle", fontSize=13, leading=18, textColor=colors.HexColor("#4b5563"), spaceAfter=20))
styles.add(ParagraphStyle(name="H1", fontSize=16, leading=20, spaceBefore=18, spaceAfter=8, fontName="Helvetica-Bold", textColor=colors.HexColor("#111827")))
styles.add(ParagraphStyle(name="H2", fontSize=12.5, leading=16, spaceBefore=12, spaceAfter=6, fontName="Helvetica-Bold", textColor=colors.HexColor("#1f2937")))
styles.add(ParagraphStyle(name="BodyCZ", fontSize=10, leading=14.5, spaceAfter=8, fontName="Helvetica"))
styles.add(ParagraphStyle(name="Caption", fontSize=8.5, leading=11, textColor=colors.HexColor("#6b7280"), spaceAfter=14, fontName="Helvetica-Oblique"))
styles.add(ParagraphStyle(name="BigStat", fontSize=20, leading=24, fontName="Helvetica-Bold", textColor=colors.HexColor("#059669")))
styles.add(ParagraphStyle(name="BigStatLabel", fontSize=9, leading=12, textColor=colors.HexColor("#6b7280")))
styles.add(ParagraphStyle(name="Warn", fontSize=10, leading=14.5, spaceAfter=8, fontName="Helvetica-Oblique", textColor=colors.HexColor("#92400e")))

GREEN = colors.HexColor("#059669")
RED = colors.HexColor("#dc2626")
GREY = colors.HexColor("#6b7280")
HEADER_BG = colors.HexColor("#1f2937")


def r_color(val: float):
    return GREEN if val >= 0 else RED


def table_style(header_bg=HEADER_BG):
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])


def parse_report(path: Path):
    """Parses analyze_entries.py's pattern_report.txt back into sections."""
    text = path.read_text()
    lines = text.splitlines()
    sections = {}
    cur = None
    header = {"overall": lines[0:2]}
    for line in lines:
        if line.startswith("=== "):
            cur = line.strip("= ").strip()
            sections[cur] = []
        elif cur and line.strip() and not line.startswith("bucket"):
            sections[cur].append(line)
    return header, sections


def bucket_table(lines, col_label="Segment"):
    data = [[col_label, "Obchodů", "Win rate", "Celkové R", "Expectancy R"]]
    for line in lines:
        parts = line.split()
        # bucket name may contain spaces -- last 4 tokens are always the numbers
        *name_parts, trades, wr, total_r, exp_r = parts
        name = " ".join(name_parts)
        data.append([name, trades, wr, total_r, exp_r])
    return data


def build():
    header, sections = parse_report(ANALYSIS / "pattern_report.txt")
    overall_line = header["overall"][1]  # "Overall: win_rate=... total_R=... expectancy_R=..."

    doc = SimpleDocTemplate(
        str(OUT_PDF), pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title="ES 2008-2026 Backtest Report", author="Lukacino trading system",
    )
    story = []

    # --- Title page ---
    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph("ES Backtest Report", styles["TitleBig"]))
    story.append(Paragraph("2008&ndash;2026 &middot; Multi-timeframe weighted synthesis model &middot; 36 603 obchodů", styles["SubTitle"]))
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#d1d5db")))
    story.append(Spacer(1, 0.8 * cm))

    stat_data = [
        [Paragraph("36 603", styles["BigStat"]), Paragraph("+2 647R", styles["BigStat"]), Paragraph("42,9 %", styles["BigStat"]), Paragraph("+0,072R", styles["BigStat"])],
        [Paragraph("Obchodů celkem", styles["BigStatLabel"]), Paragraph("Celkové R (baseline)", styles["BigStatLabel"]), Paragraph("Win rate", styles["BigStatLabel"]), Paragraph("Expectancy / obchod", styles["BigStatLabel"])],
    ]
    t = Table(stat_data, colWidths=[4 * cm] * 4)
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, 1), 2),
    ]))
    story.append(t)
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(
        "Data: Sierra Chart 1-minutové bary (back-adjusted kontinuální ES kontrakt), "
        "4.5.2008 &ndash; 25.9.2026, 6 439 575 barů. Pravidla: měsíční/týdenní/intradenní VWAP tiery, "
        "kumulativní delta, slévání denních market profilů při 60% překryvu objemu transakcí, "
        "kompozity (VAL/VAH) jako cíle a confluence filtr.",
        styles["BodyCZ"],
    ))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "<b>Důležité upozornění:</b> žádné transakční náklady, spread ani slippage nejsou v tomto "
        "backtestu započteny. Výsledky jsou simulací proti last_price snímkům (1-minutové bary), ne "
        "reálným fillům. Tohle je výzkumný nástroj pro hledání edge, ne potvrzení obchodovatelné strategie.",
        styles["Warn"],
    ))

    story.append(PageBreak())

    # --- Executive summary ---
    story.append(Paragraph("Shrnutí klíčových zjištění", styles["H1"]))
    findings = [
        ("1. Counter long/short nese většinu edge.",
         "Equity křivka má nejstrmější a nejkonzistentnější sklon ze všech typů hypotéz "
         "(Counter long: +0,116R/obchod, Counter short: +0,053R/obchod) &mdash; multi-timeframe synthesis "
         "model (ARCHITECTURE.md bod 8) je reálný zdroj alfy, ne jen doplněk k A/B-day logice."),
        ("2. A_PLUS vs. CLEAN confluence skoro nerozlišuje kvalitu.",
         "Expectancy 0,071R (A_PLUS) vs. 0,076R (CLEAN) &mdash; prakticky identické. Současné "
         "skórování confluence NENÍ dobrý filtr pro „vysoce pravděpodobnostní A setupy“. Skutečné "
         "rozdíly leží jinde: typ hypotézy, HTF konvikce, den v týdnu, hodina."),
        ("3. Relativní sweep (násobky strukt. rizika) byl zavádějící &mdash; na FIXNÍCH bodech vychází jiný obrázek.",
         "Medián strukturalního rizika je jen 2,87 bodu, takže „nejlepší“ relativní kombinace "
         "(0,5× stop, RRR 3:1) odpovídá mediánu ~1,44 bodu SL &mdash; na ES prakticky neobchodovatelné "
         "(pod šířkou spreadu). Na FIXNÍCH bodových vzdálenostech (srovnatelných s G7FX referencí "
         "12&ndash;25 bodů TP) je systém na téhle škále (SL 10&ndash;20 bodů, RRR~1,5:1) "
         "<b>ztrátový</b> (např. SL=15pt/RRR=1,5 → -1194R). Jediná konzistentně zisková zóna: "
         "těsný stop 3&ndash;5 bodů s RRR 1,5&ndash;3:1 (+1200 až +3384R) &mdash; ale 3bodový stop "
         "je v dosahu běžného skluzu na ES, který tento backtest nemodeluje."),
        ("4. Fading extrémů kompozitu se v této analýze nepotvrzuje.",
         "„Mid-range“ pozice uvnitř kompozitu má lepší expectancy (0,081R) než kraje "
         "VAH (0,071R) či VAL (0,052R) &mdash; opak G7FX-style fading teorie. Metrika měří okraje "
         "VAL/VAH, ne skutečné ±2SD extrémy &mdash; stálo by za to zpřesnit."),
        ("5. Víceleg hypotézy jsou většina, ne výjimka.",
         "78,4 % zachycených obchodů mělo nastavený target_2 &mdash; stojí za samostatnou analýzu "
         "scale-out výkonnosti vs. jediný TP."),
    ]
    for title, body in findings:
        story.append(Paragraph(title, styles["H2"]))
        story.append(Paragraph(body, styles["BodyCZ"]))

    story.append(PageBreak())

    # --- Equity curves ---
    story.append(Paragraph("Equity křivky", styles["H1"]))
    charts = [
        ("equity_a_b_counter.png", "A vs. B vs. Counter setupy &mdash; Counter má nejstrmější a nejkonzistentnější křivku."),
        ("equity_long_short.png", "Long vs. Short &mdash; long strážuje více R, což odpovídá dlouhodobému růstovému (long) biasu indexů."),
        ("equity_confluence.png", "A_PLUS vs. CLEAN confluence &mdash; křivky jedou prakticky identicky, confluence skóre není silný filtr."),
        ("equity_by_type.png", "Všech 6 typů hypotéz zvlášť."),
    ]
    for fname, caption in charts:
        img_path = ANALYSIS / fname
        img = Image(str(img_path), width=16 * cm, height=16 * cm * 480 / 1500)
        story.append(KeepTogether([img, Paragraph(caption, styles["Caption"])]))
        story.append(Spacer(1, 0.3 * cm))

    story.append(PageBreak())

    # --- TP/SL/RRR sweep (relative) ---
    story.append(Paragraph("TP/SL/RRR sweep — relativní (násobky strukturalního rizika)", styles["H1"]))
    story.append(Paragraph(
        "Každý z 36 603 zachycených vstupů přesimulován proti mřížce 5×8 kombinací "
        "(stop = násobek strukturalního rizika, target = RRR × stop) &mdash; vstupy samotné se nemění, "
        "jen jak daleko seděl stop/target.",
        styles["BodyCZ"],
    ))
    story.append(Paragraph(
        "<b>Pozor:</b> „nejlepší“ kombinace níže odpovídá mediánu jen ~1,44 bodu SL "
        "(viz další sekce) &mdash; na reálném ES těžko obchodovatelná vzdálenost. Tahle "
        "relativní analýza je užitečná pro srovnání napříč různými volatilitními režimy, "
        "ale pro reálnou volbu SL/TP použij fixní bodovou analýzu níže.",
        styles["Warn"],
    ))
    img = Image(str(ANALYSIS / "sweep_heatmap.png"), width=14 * cm, height=14 * cm * 980 / 1200)
    story.append(img)
    story.append(Spacer(1, 0.4 * cm))

    sweep_csv = BASE / "sweep_results_full.csv"
    with open(sweep_csv, newline="") as f:
        sweep_rows = list(csv.DictReader(f))
    sweep_rows.sort(key=lambda r: -float(r["total_r"]))
    data = [["Stop ×", "RRR", "Obchodů", "Win rate", "Celkové R", "Expectancy R"]]
    for r in sweep_rows[:10]:
        wr = f"{float(r['win_rate']):.1%}" if r["win_rate"] else "n/a"
        data.append([r["stop_multiplier"], r["rrr"], r["trades"], wr, f"{float(r['total_r']):+.0f}", f"{float(r['expectancy_r'] or 0):+.3f}"])
    t = Table(data, colWidths=[2.2 * cm, 2 * cm, 2.5 * cm, 2.5 * cm, 3 * cm, 3.3 * cm])
    t.setStyle(table_style())
    story.append(Paragraph("Top 10 kombinací podle celkového R", styles["H2"]))
    story.append(t)

    story.append(PageBreak())

    # --- TP/SL/RRR sweep (fixed points) -- the decision-relevant one ---
    story.append(Paragraph("TP/SL/RRR sweep — FIXNÍ body (reálně obchodovatelné vzdálenosti)", styles["H1"]))
    story.append(Paragraph(
        "Stejný princip, ale SL/TP jsou FIXNÍ body (3 až 30), stejné pro každý obchod &mdash; "
        "tohle odpovídá tomu, jak diskreční trader (např. G7FX styl: SL~10&ndash;20pt, "
        "RRR~1,5:1, TP 12&ndash;25pt) skutečně nastavuje objednávky.",
        styles["BodyCZ"],
    ))
    img2 = Image(str(ANALYSIS / "sweep_heatmap_fixed_points.png"), width=14.5 * cm, height=14.5 * cm * 1050 / 1350)
    story.append(img2)
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        "<b>Klíčové zjištění:</b> na G7FX referenční škále (SL 10&ndash;20 bodů, RRR~1,5:1) "
        "je systém v této 18leté historii <b>ztrátový</b> (např. SL=15pt/RRR=1,5 → -1194R, "
        "SL=20pt/RRR=1,5 → -1578R). Jediná konzistentně zisková zóna: těsný stop 3&ndash;5 bodů "
        "s RRR 1,5&ndash;3:1. Další, odlišná zisková zóna: velmi široké stopy (25&ndash;30 bodů) "
        "s RRR 0,75 (TP menší než SL, vysoký win rate ~59&ndash;60&nbsp;%) &mdash; jiný charakter "
        "obchodu než trend-following. <b>Důležitá výhrada:</b> 3bodový stop je v dosahu běžného "
        "skluzu na ES (žádné transakční náklady nejsou v tomto backtestu započteny) &mdash; "
        "reálná edge u těsných stopů může být výrazně nižší.",
        styles["Warn"],
    ))
    story.append(Spacer(1, 0.3 * cm))

    sweep_fp_csv = BASE / "sweep_fixed_points.csv"
    with open(sweep_fp_csv, newline="") as f:
        fp_rows = list(csv.DictReader(f))
    fp_rows.sort(key=lambda r: -float(r["total_r"]))
    data = [["SL (pt)", "TP (pt)", "RRR", "Obchodů", "Win rate", "Celkové R", "Expectancy R"]]
    for r in fp_rows[:12]:
        wr = f"{float(r['win_rate']):.1%}" if r["win_rate"] else "n/a"
        data.append([
            r["sl_points"], f"{float(r['tp_points']):.1f}", r["rrr"], r["trades"], wr,
            f"{float(r['total_r']):+.0f}", f"{float(r['expectancy_r'] or 0):+.3f}",
        ])
    t2 = Table(data, colWidths=[2 * cm, 2 * cm, 1.8 * cm, 2.2 * cm, 2.2 * cm, 2.6 * cm, 3 * cm])
    t2.setStyle(table_style())
    story.append(Paragraph("Top 12 kombinací podle celkového R", styles["H2"]))
    story.append(t2)

    story.append(PageBreak())

    # --- Pattern mining tables ---
    story.append(Paragraph("Pattern-mining rozbor", styles["H1"]))
    story.append(Paragraph(overall_line, styles["BodyCZ"]))

    table_sections = [
        ("By hypothesis type", "Typ hypotézy"),
        ("By confluence", "Confluence"),
        ("By type x confluence (the 'A setups' question)", "Typ / Confluence"),
        ("By direction", "Směr"),
        ("By day of week", "Den v týdnu"),
        ("By HTF conviction (counter-intraday trades only)", "HTF konvikce (jen counter-intraday)"),
        ("By composite presence", "Přítomnost kompozitu"),
        ("By position within nearest composite (fading-the-edge question)", "Pozice v kompozitu"),
    ]
    for section_key, col_label in table_sections:
        if section_key not in sections:
            continue
        story.append(Paragraph(col_label, styles["H2"]))
        data = bucket_table(sections[section_key], col_label)
        t = Table(data, colWidths=[6 * cm, 2.5 * cm, 2.5 * cm, 2.7 * cm, 3.3 * cm])
        t.setStyle(table_style())
        story.append(t)
        story.append(Spacer(1, 0.3 * cm))

    story.append(PageBreak())
    story.append(Paragraph("By hour", styles["H2"]))
    data = bucket_table(sections["By hour (UTC-ish, source data's own clock)"], "Hodina")
    t = Table(data, colWidths=[6 * cm, 2.5 * cm, 2.5 * cm, 2.7 * cm, 3.3 * cm])
    t.setStyle(table_style())
    story.append(t)

    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph("Limity a další kroky", styles["H1"]))
    story.append(Paragraph(
        "&bull; Žádné transakční náklady/slippage/spread &mdash; při 30&ndash;43 % win rate by se "
        "reálné náklady projevily významně, hlavně u agresivnějších RRR kombinací.<br/>"
        "&bull; tolerance_fraction=0,1 (tiers.py) je stále nekalibrovaný placeholder.<br/>"
        "&bull; Metrika „pozice v kompozitu“ měří VAL/VAH okraje, ne skutečné ±2SD extrémy "
        "z G7FX-style fading popisu &mdash; stálo by za to přepracovat.<br/>"
        "&bull; Doporučený další krok: přepisat filtr „A setupu“ na "
        "hypothesis_type&isin;{Counter long, Counter short, B long} + htf_conviction=high + den&ne;neděle, "
        "místo spoléhání na A_PLUS/CLEAN confluence skóre.",
        styles["BodyCZ"],
    ))

    doc.build(story)
    print(f"PDF written: {OUT_PDF}")


if __name__ == "__main__":
    build()

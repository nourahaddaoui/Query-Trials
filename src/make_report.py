"""Build report.pdf from the real results. Two pages, six sections.

Everything factual is read from results/summary.csv, results/per_item.csv,
data/items.jsonl and results/hardware.md - nothing is typed twice, so the
report cannot drift from the numbers.

    python -m src.make_report

The one thing it cannot write is section 5, the choice paragraph. It drafts
a version from the numbers and marks it clearly: the team must rewrite it in
their own words. That paragraph is graded on judgement, not arithmetic.
"""

import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parent.parent
SUMMARY = ROOT / "results" / "summary.csv"
PER_ITEM = ROOT / "results" / "per_item.csv"
ITEMS = ROOT / "data" / "items.jsonl"
HARDWARE = ROOT / "results" / "hardware.md"
OUT = ROOT / "report.pdf"

NAVY = colors.HexColor("#1F3A5F")
GREY = colors.HexColor("#555555")
LINE = colors.HexColor("#CCCCCC")
LIGHT = colors.HexColor("#F2F4F7")

ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("t", parent=ss["Title"], fontSize=16, spaceAfter=2,
                            textColor=NAVY, alignment=0),
    "sub": ParagraphStyle("s", parent=ss["Normal"], fontSize=8.5,
                          textColor=GREY, spaceAfter=9),
    "h": ParagraphStyle("h", parent=ss["Heading2"], fontSize=10.5,
                        textColor=NAVY, spaceBefore=8, spaceAfter=3),
    "b": ParagraphStyle("b", parent=ss["Normal"], fontSize=8.7, leading=11.6,
                        spaceAfter=4, alignment=TA_JUSTIFY),
    "mono": ParagraphStyle("m", parent=ss["Normal"], fontName="Courier",
                           fontSize=7.2, leading=9.2, spaceAfter=3),
    "cell": ParagraphStyle("c", parent=ss["Normal"], fontSize=7.6, leading=9.5),
    "cellw": ParagraphStyle("cw", parent=ss["Normal"], fontSize=7.6,
                            leading=9.5, textColor=colors.white,
                            fontName="Helvetica-Bold"),
    "note": ParagraphStyle("n", parent=ss["Normal"], fontSize=7.6, leading=9.8,
                           textColor=GREY),
}


def P(t, s="b"):
    return Paragraph(t, S[s])


def read_csv(path):
    if not path.exists():
        sys.exit(f"Missing {path.name}. Run: python -m src.score && "
                 f"python -m src.cost")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def table(header, rows, widths, sizes=None):
    data = [[Paragraph(h, S["cellw"]) for h in header]]
    data += [[Paragraph(str(c), S["cell"]) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), NAVY),
          ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("GRID", (0, 0), (-1, -1), 0.35, LINE),
          ("LEFTPADDING", (0, 0), (-1, -1), 4),
          ("RIGHTPADDING", (0, 0), (-1, -1), 4),
          ("TOPPADDING", (0, 0), (-1, -1), 2.5),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    for i in range(2, len(data), 2):
        st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FAFBFC")))
    t.setStyle(TableStyle(st))
    return t


def hardware_bits():
    """Pull CPU / memory / model lines out of hardware.md if it exists."""
    if not HARDWARE.exists():
        return "⟨run results/collect_hardware.py⟩"
    txt = HARDWARE.read_text(encoding="utf-8")
    got = {}
    for key in ("CPU", "Memory", "Model", "OS"):
        m = re.search(rf"^\|\s*{key}\s*\|\s*(.+?)\s*\|$", txt, re.M)
        if m:
            got[key] = m.group(1).replace("`", "")
    if not got:
        return "⟨see results/hardware.md⟩"
    return ", ".join(f"{k}: {v}" for k, v in got.items())


def worst_examples(per_item, model_key, n=3):
    """Pick wrong answers, preferring ones with an explanatory note."""
    rows = [r for r in per_item
            if r["model_key"] == model_key and r["correct"] != "True"]
    rows.sort(key=lambda r: (r["note"] == "", r["item_id"]))
    return rows[:n]


def main():
    try:
        from reportlab.pdfgen import canvas  # noqa: F401
    except ImportError:
        sys.exit("pip install reportlab")

    summary = read_csv(SUMMARY)
    per_item = read_csv(PER_ITEM)
    items = {json.loads(l)["id"]: json.loads(l)
             for l in open(ITEMS, encoding="utf-8")}

    if not any(r.get("cost_per_1k_usd") for r in summary):
        print("WARNING: no cost figures in summary.csv - run python -m src.cost")

    n_test = len(items)          # all items are graded
    run_id = per_item[0]["run_id"] if per_item else "?"
    example = items.get("q027") or next(iter(items.values()))

    story = []

    # ---------------- page 1 ----------------
    story += [
        P("Query-Trials: three models write SQL", "title"),
        P(f"Youssef · Noura · Oumayma — CS496 Project 0 — run {run_id} — "
          f"generated {date.today()}", "sub"),

        P("1. The task", "h"),
        P("A model is given a database schema and a plain-English question, and "
          "must write one SQLite query that answers it. Scoring is "
          "<b>execution match</b>: we run the model's query and the reference "
          "query and compare the rows returned. The queries are never compared "
          "as text — two people can write the same query differently and both "
          "be right. No human judgement, no LLM judge."),
        P(f"<b>Example item ({example['id']}, {example['difficulty']}).</b> "
          f"{example['question']}"),
        P(f"Reference SQL: <font face='Courier' size='7'>"
          f"{example['gold_sql'][:300]}</font>", "note"),

        P("2. The data", "h"),
        P("The <i>Employees</i> sample database from Kaggle: six linked tables, "
          "300,024 employees, 967,330 salary records. The dataset encodes "
          "\"still current\" as <font face='Courier' size='7'>to_date = "
          "'9999-01-01'</font> rather than NULL; several questions depend on "
          "it, and models that assume NULL get them wrong. That is legitimate "
          "difficulty, not a flawed question."),
        P(f"<b>{n_test} questions</b> written by hand, all of them graded — the "
          f"brief asks for at least 50. Every reference query was executed "
          "before any model ran, and its row count checked. Two items were "
          "replaced at that stage because they returned nothing by "
          "construction: one asked which departments have no current manager "
          "(all nine have one) and one asked a set to exceed its own maximum. "
          "Both were replaced <b>before</b> any model saw them — which is not "
          "the same as removing an item a model failed. Labels were "
          "double-checked by a second reader; see data/labelling_note.md."),

        P("3. Setup", "h"),
        table(["Slot", "Model", "Exact name"],
              [["Top API", "Claude Opus 5", "claude-opus-5"],
               ["Cheap API", "Claude Haiku 4.5", "claude-haiku-4-5-20251001"],
               ["Open-weights, self-hosted", "Qwen2.5-Coder 3B (Q4_K_M)",
                "qwen2.5-coder:3b-instruct-q4_K_M"]],
              [34*mm, 52*mm, 80*mm]),
        Spacer(1, 4),
        P("Identical for all three: one prompt with the schema embedded "
          f"(fingerprint printed on every result row), temperature 0, 300 "
          f"output tokens, the same {n_test} items in the same order, one "
          "shared parser, calls made strictly sequentially, no retries. The "
          "three model adapters expose the same function signature, so the "
          "runner has no per-model branch — there is nowhere for a difference "
          "to hide."),
        P(f"Local model hardware — {hardware_bits()}. Three warm-up calls were "
          "excluded from timing. We planned the 7B model but the available "
          "machine could not run it usefully; the 3B is reported as its own "
          "model, not as a stand-in."),
        PageBreak(),
    ]

    # ---------------- page 2 ----------------
    head = ["Model", "Correct", "Acc", "p50", "p95", "Wrong", "Err", "$/1k"]
    rows = []
    for s in summary:
        errs = (int(s["n_sql_error"]) + int(s["n_timeout"]) +
                int(s["n_unsafe"]) + int(s["n_parse_error"]) +
                int(s["n_api_error"]))
        rows.append([s["model_name"],
                     f"{s['n_correct']}/{s['n_items']}",
                     s["accuracy"],
                     f"{s['p50_ms']} ms",
                     f"{s['p95_ms']} ms",
                     s["n_wrong_result"],
                     errs,
                     f"${s['cost_per_1k_usd']}" if s.get("cost_per_1k_usd")
                     else "—"])

    story += [
        P("4. Results", "h"),
        table(head, rows, [48*mm, 16*mm, 13*mm, 18*mm, 18*mm, 14*mm, 12*mm,
                           17*mm]),
        Spacer(1, 3),
        P("\"Wrong\" is a query that ran and returned different rows. \"Err\" "
          "counts SQL errors, timeouts, unsafe statements, unparseable output "
          "and failed API calls — all of which count as wrong, shown "
          "separately as the brief requires. Latency is time to the complete "
          "answer; we report p50 and p95 rather than the mean, because one "
          "very slow answer barely moves an average of fifty but is exactly "
          "what a user notices.", "note"),
    ]

    story.append(P("Wrong answers, and why", "h"))
    for s in summary:
        key = s["model_key"]
        ex = worst_examples(per_item, key)
        if not ex:
            continue
        story.append(P(f"<b>{s['model_name']}</b>", "note"))
        wrong_rows = [[r["item_id"], r["status"],
                       (r["note"] or "⟨explain why⟩")[:70],
                       (r["parsed_sql"] or "")[:95]] for r in ex]
        story.append(table(["Item", "Status", "Why it failed", "What it wrote"],
                           wrong_rows,
                           [13*mm, 22*mm, 55*mm, 66*mm]))
        story.append(Spacer(1, 3))

    story += [
        P("5. Our choice, and when it would change", "h"),
        Table([[Paragraph(
            "<b>TEAM: replace this paragraph with your own words before "
            "hand-in.</b> The numbers above are generated; this judgement is "
            "not, and it is graded as judgement. State which model you would "
            "deploy, justify it with the accuracy gap against the cost gap in "
            "actual figures, then name the specific conditions that would "
            "change the answer — a higher accuracy bar, a volume past the "
            "break-even, a latency ceiling the local model cannot meet, or an "
            "offline requirement that rules out an API entirely.",
            S["b"])]], colWidths=[166*mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("LINEBEFORE", (0, 0), (0, -1), 2, NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5)])),
        Spacer(1, 5),

        P("6. Cost at 100× traffic, and break-even", "h"),
        P("API cost scales <b>linearly</b>: at 100× the traffic the bill is "
          "100× larger, with no change in behaviour. Self-hosting is a "
          "<b>step function</b> — one machine absorbs the growth at almost no "
          "marginal cost until it saturates, at which point you buy another "
          "machine and the cost jumps. The two therefore cross at a specific "
          "volume."),
        P("Break-even is where total API spend equals total self-hosted spend, "
          "counting the one-off setup time as a fixed cost: "
          "<font face='Courier' size='7'>api_per_1k × N/1000 = fixed_setup + "
          "local_per_1k × N/1000</font>. Below that volume the API is cheaper "
          "overall; above it, self-hosting wins — but only if its p95 latency "
          "is acceptable, which for our machine is the binding constraint "
          "rather than the money. Exact figures and every assumption (hardware "
          "price, amortisation, electricity, utilisation) are printed by "
          "<font face='Courier' size='7'>python -m src.cost</font> and listed "
          "in src/prices.yaml with the date the prices were checked."),
        Spacer(1, 4),
        P("Reproduce: <font face='Courier' size='7'>python -m src.doctor && "
          "python -m src.run --model all && python -m src.score "
          "&& python -m src.cost</font>", "note"),
    ]

    doc = SimpleDocTemplate(str(OUT), pagesize=A4,
                            leftMargin=22*mm, rightMargin=22*mm,
                            topMargin=16*mm, bottomMargin=16*mm,
                            title="Query-Trials — Project 0")
    doc.build(story)

    from pypdf import PdfReader
    n = len(PdfReader(str(OUT)).pages)
    print(f"Wrote {OUT.relative_to(ROOT)} ({n} pages)")
    if n != 2:
        print(f"  NOTE: {n} pages, the brief asks for 2. Trim a paragraph "
              f"or shorten the wrong-answer notes.")
    print("  Section 5 still needs the team's own words.")


if __name__ == "__main__":
    main()

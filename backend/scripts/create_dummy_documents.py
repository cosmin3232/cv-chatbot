"""Create fictional, locally ignored CV documents and activate their extracted text.

Run from backend: .venv/Scripts/python.exe scripts/create_dummy_documents.py
Existing documents or knowledge files are never overwritten.
"""

from pathlib import Path

from docx import Document
from docx.shared import Pt
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.ingest import extract_document
from app.knowledge import load_knowledge

DATA = Path(__file__).resolve().parents[1] / "data"


def create_cv(path: Path):
    lines = [
        (21, "ALEX MARIN"),
        (12, "Full Stack Software Engineer | Brasov, Romania"),
        (10, "FICTIONAL TEST PROFILE - all names, employers, and achievements are invented."),
        (10, "alex.marin@example.com | https://example.com/alex-marin"),
        (14, "PROFESSIONAL SUMMARY"),
        (11, "Software engineer building web applications with React, TypeScript, and Python."),
        (11, "Experienced in API development, PostgreSQL, automated testing, and small teams."),
        (14, "EXPERIENCE"),
        (12, "Full Stack Engineer | Cedar Finch Labs (fictional) | Jan 2024 - present"),
        (11, "Built a Next.js customer portal used by 120 internal staff."),
        (11, "Developed FastAPI services and PostgreSQL queries for order management."),
        (11, "Reduced median API response time from 800 ms to 300 ms in load tests."),
        (11, "Added Playwright end-to-end tests and GitHub Actions CI checks."),
        (12, "Frontend Developer | Blue Lantern Digital (fictional) | Jun 2021 - Dec 2023"),
        (11, "Delivered React and TypeScript dashboards for three fictional retail clients."),
        (11, "Improved keyboard navigation and worked with designers on accessible forms."),
        (11, "Collaborated in a team of four developers; no formal management role."),
        (14, "SELECTED PROJECTS"),
        (12, "TrailNotes | Personal project | 2025"),
        (11, "A hiking journal built with Next.js, FastAPI, and PostgreSQL."),
        (11, "Implemented route notes, photo metadata, and user authentication."),
        (12, "BudgetNest | Learning project | 2023"),
        (11, "A React expense tracker with CSV import and monthly spending charts."),
        (14, "TECHNICAL SKILLS"),
        (11, "TypeScript, JavaScript, Python, React, Next.js, FastAPI, SQL, PostgreSQL"),
        (11, "Docker, Git, GitHub Actions, pytest, Playwright, REST APIs"),
        (11, "Basic AWS knowledge from personal experiments; no AWS certification."),
        (14, "EDUCATION AND LANGUAGES"),
        (11, "BSc Computer Science | North Valley Institute (fictional) | 2018 - 2021"),
        (11, "Romanian: native | English: B2, self-assessed"),
    ]
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    commands = []
    y = 795
    for size, text in lines:
        if size >= 14:
            y -= 9
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"BT /F1 {size} Tf 42 {y} Td ({escaped}) Tj ET")
        y -= size + 6
    assert y > 30, "CV does not fit the page"
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_metadata({"/Title": "Alex Marin - Fictional Test CV", "/Author": "Synthetic test data"})
    writer.write(path)


def create_notes(path: Path):
    document = Document()
    document.styles["Normal"].font.name = "Calibri"
    document.styles["Normal"].font.size = Pt(11)
    document.add_heading("Alex Marin - Additional Information", 0)
    document.add_paragraph("FICTIONAL TEST PROFILE. This document describes an invented candidate, not the project owner.")
    document.add_heading("Career preferences", level=1)
    document.add_paragraph("Alex is interested in mid-level full stack engineering roles, especially developer tools and education products. Alex prefers hands-on implementation over people management.")
    table = document.add_table(rows=1, cols=2)
    table.style = "Light Shading Accent 1"
    table.rows[0].cells[0].text = "Topic"
    table.rows[0].cells[1].text = "Information"
    for topic, information in [
        ("Work arrangement", "Remote within Romania, or hybrid in Brasov up to two days per week."),
        ("Relocation", "Not currently interested in relocation."),
        ("Availability", "30 calendar days after accepting an offer."),
        ("Travel", "Occasional business travel, up to four trips per year."),
        ("Public contact", "alex.marin@example.com (fictional example address)."),
    ]:
        cells = table.add_row().cells
        cells[0].text, cells[1].text = topic, information
    document.add_heading("Collaboration and strengths", level=1)
    document.add_paragraph("Alex enjoys clarifying ambiguous requirements, writing short technical notes, and reviewing pull requests. In the fictional portal project, Alex worked with a designer and two backend engineers.")
    document.add_heading("Learning goals and limits", level=1)
    document.add_paragraph("Alex is learning observability with OpenTelemetry and introductory Kubernetes concepts. There is no production Kubernetes experience, no professional Go experience, and no formal management experience.")
    document.add_heading("Information not provided", level=1)
    document.add_paragraph("Salary expectations, current compensation, nationality, visa or work authorization status, and reference contacts are not provided. Do not infer them from the candidate's location or language.")
    document.add_heading("Outside work", level=1)
    document.add_paragraph("Alex likes hiking, board games, and helping friends learn basic programming.")
    document.save(path)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    targets = [DATA / name for name in ("dummy_cv.pdf", "dummy_info.docx", "knowledge.draft.md", "knowledge.md")]
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise SystemExit("Refusing to overwrite existing files: " + ", ".join(existing))
    cv, notes, draft, active = targets
    create_cv(cv)
    create_notes(notes)
    text = extract_document(cv) + "\n\n---\n\n" + extract_document(notes) + "\n"
    draft.write_text(text, encoding="utf-8")
    active.write_text(text, encoding="utf-8")
    loaded = load_knowledge(active)
    for expected in ("FICTIONAL TEST PROFILE", "800 ms to 300 ms", "30 calendar days", "Salary expectations"):
        assert expected in loaded, f"Missing extracted content: {expected}"
    print(f"Created fictional PDF, DOCX, draft and active knowledge ({len(loaded):,} characters).")
    print("Candidate: Alex Marin. Data is fictional and excluded from Git.")


if __name__ == "__main__":
    main()

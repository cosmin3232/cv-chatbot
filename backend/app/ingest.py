"""Run: python -m app.ingest path/to/cv.pdf path/to/info.docx"""

import argparse
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from .config import BACKEND_DIR


def extract_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        pages = []
        for number, page in enumerate(PdfReader(path).pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                raise ValueError(f"Page {number} has no extractable text. OCR is required for scanned pages.")
            pages.append(f"## CV, page {number}\n\n{text}")
        result = "\n\n".join(pages)
    elif path.suffix.lower() == ".docx":
        document = Document(path)
        blocks = []
        for block in document.iter_inner_content():
            if hasattr(block, "rows"):
                blocks.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
            else:
                blocks.append(block.text)
        result = "## Additional information\n\n" + "\n".join(text for text in blocks if text.strip())
        if not any(text.strip() for text in blocks):
            raise ValueError("Word document has no extractable text.")
    else:
        raise ValueError("Use a .pdf or .docx file. Older .doc files must be converted first.")
    if not result.strip():
        raise ValueError("Document has no extractable text.")
    return result


def main():
    parser = argparse.ArgumentParser(description="Extract CV and notes for local review.")
    parser.add_argument("documents", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, default=BACKEND_DIR / "data" / "knowledge.draft.md")
    args = parser.parse_args()
    try:
        text = "\n\n---\n\n".join(extract_document(path) for path in args.documents)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(text + "\n")
    except Exception as exc:
        parser.exit(1, f"Import failed: {exc}\n")
    print(f"Extracted {len(text):,} characters to {args.output}.")
    print("Review layout, dates, and public contact details, then copy to data/knowledge.md.")
    if len(text) > 12000:
        print("Shorten the reviewed text to at most 12,000 characters before using it.")


if __name__ == "__main__":
    main()

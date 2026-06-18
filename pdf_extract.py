#!/usr/bin/env python3
# Usage: pdf_extract.py <input.pdf> <output.txt>
"""
Extract clean text from PDF using pymupdf.
- Strips footnotes (smaller font size than body text)
- Strips References/Bibliography section
- Strips inline citations [1], [2,3], (Smith et al., 2023)
- Strips superscript number markers
"""

import sys
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import fitz  # pymupdf


END_HEADING = re.compile(
    r"^(?:References|Bibliography|Works Cited|Footnotes|REFERENCES|BIBLIOGRAPHY|FOOTNOTES)\s*$"
)
NUMERIC_CITATION = re.compile(r"\[\d+(?:[,\-]\s*\d+)*\]")
ET_AL_CITATION = re.compile(r"\([A-Z][a-z]+(?:\s+et\s+al\.)?,?\s*\d{4}\)")
AUTHORS_YEAR_CITATION = re.compile(
    r"\([A-Z][a-z]+(?:\s*[,&]\s*[A-Z][a-z]+)+,?\s*\d{4}\)"
)
SUPERSCRIPT_DIGITS = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")


def get_body_size(doc: fitz.Document) -> float:
    size_counts: dict[float, int] = {}
    for span in _text_spans(doc):
        size = round(span["size"], 1)
        text = span["text"].strip()
        if len(text) > 10:
            size_counts[size] = size_counts.get(size, 0) + len(text)
    if not size_counts:
        return 10.0
    return max(size_counts, key=lambda s: size_counts[s])


def _text_spans(doc: fitz.Document):
    for page in doc:
        for block in _page_text_blocks(page):
            for line in block["lines"]:
                yield from line["spans"]


def extract_clean_text(pdf_path: str) -> str:
    pdf_path = _validated_pdf_path(pdf_path)
    pymupdf_text = _extract_with_pymupdf(pdf_path)
    pdftotext_text = _extract_with_pdftotext(pdf_path)

    # Printed web pages can have a text layer that PyMuPDF barely sees while
    # poppler/pdftotext extracts correctly. Prefer it only when it is clearly
    # more complete, so paper footnote stripping remains the normal path.
    if _word_count(pdftotext_text) > max(
        300, int(_word_count(pymupdf_text) * 1.35)
    ):
        return _clean(pdftotext_text)
    return _clean(pymupdf_text)


def _extract_with_pdftotext(pdf_path: str) -> str:
    if not shutil.which("pdftotext"):
        return ""

    pdf_path = _validated_pdf_path(pdf_path)
    try:
        result = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", pdf_path, "-"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return ""

    if result.returncode != 0:
        return ""
    return result.stdout


def _extract_with_pymupdf(pdf_path: str) -> str:
    pdf_path = _validated_pdf_path(pdf_path)
    with fitz.open(pdf_path) as doc:
        footnote_threshold = get_body_size(doc) - 1.5
        paragraphs = []

        for page in doc:
            for block in _page_text_blocks(page):
                if _is_end_heading(block):
                    return "\n\n".join(paragraphs)

                paragraph = _block_paragraph(
                    block, page.rect.height, footnote_threshold
                )
                if paragraph:
                    paragraphs.append(paragraph)

        return "\n\n".join(paragraphs)


def _page_text_blocks(page):
    return [
        block
        for block in page.get_text("dict")["blocks"]
        if block["type"] == 0
    ]


def _is_end_heading(block) -> bool:
    if not block["lines"]:
        return False
    first_line_text = "".join(span["text"] for span in block["lines"][0]["spans"])
    return bool(END_HEADING.match(first_line_text.strip()))


def _block_paragraph(block, page_height: float, footnote_threshold: float) -> str:
    lines = [
        line_text
        for line in block["lines"]
        if (line_text := _line_text(line, page_height, footnote_threshold))
    ]
    return " ".join(lines)


def _line_text(line, page_height: float, footnote_threshold: float) -> str:
    near_page_bottom = line["bbox"][1] > page_height * 0.72
    if near_page_bottom and _has_small_span(line, footnote_threshold):
        return ""
    return "".join(span["text"] for span in line["spans"]).strip()


def _has_small_span(line, footnote_threshold: float) -> bool:
    return any(round(span["size"], 1) < footnote_threshold for span in line["spans"])


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _clean(text: str) -> str:
    text = _strip_end_matter(text)
    # Inline citations [1], [2,3], [1-5]
    text = NUMERIC_CITATION.sub("", text)
    # (Author et al., 2023) / (Author, 2023)
    text = ET_AL_CITATION.sub("", text)
    text = AUTHORS_YEAR_CITATION.sub("", text)
    # Superscript unicode digits
    text = SUPERSCRIPT_DIGITS.sub("", text)
    # Whitespace
    text = text.replace("\f", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _strip_end_matter(text: str) -> str:
    kept_lines = []
    for line in text.splitlines():
        if END_HEADING.match(line.strip()):
            break
        kept_lines.append(line)
    return "\n".join(kept_lines)


def _validated_pdf_path(path_arg: str) -> str:
    path = Path(path_arg).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a readable PDF file: {path_arg}")
    return str(path)


def _validated_output_path(path_arg: str) -> str:
    path = Path(path_arg).expanduser()
    parent = path.parent.resolve(strict=True)
    output_path = parent / path.name
    if not _is_inside_allowed_temp_root(parent):
        raise ValueError(f"Output path must be in a temp directory: {path_arg}")
    if output_path.suffix.lower() != ".txt":
        raise ValueError(f"Output path must be a .txt file: {path_arg}")
    if output_path.exists() and not output_path.is_file():
        raise ValueError(f"Output path is not a file: {path_arg}")
    return str(output_path)


def _allowed_temp_roots() -> set[Path]:
    return {Path(tempfile.gettempdir()).resolve(strict=True)}


def _is_inside_allowed_temp_root(path: Path) -> bool:
    return any(path == root or root in path.parents for root in _allowed_temp_roots())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.pdf> <output.txt>", file=sys.stderr)
        sys.exit(1)

    try:
        input_pdf = _validated_pdf_path(sys.argv[1])
        output_txt = _validated_output_path(sys.argv[2])
        text = extract_clean_text(input_pdf)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not text:
        print("ERROR: no text extracted", file=sys.stderr)
        sys.exit(1)

    with open(output_txt, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"Extracted {len(text):,} chars → {output_txt}")

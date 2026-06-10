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
import fitz  # pymupdf


END_HEADING = re.compile(
    r"^(?:References|Bibliography|Works Cited|Footnotes|REFERENCES|BIBLIOGRAPHY|FOOTNOTES)\s*$"
)


def get_body_size(doc: fitz.Document) -> float:
    size_counts: dict[float, int] = {}
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    size = round(span["size"], 1)
                    text = span["text"].strip()
                    if len(text) > 10:
                        size_counts[size] = size_counts.get(size, 0) + len(text)
    if not size_counts:
        return 10.0
    return max(size_counts, key=lambda s: size_counts[s])


def extract_clean_text(pdf_path: str) -> str:
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
    doc = fitz.open(pdf_path)
    body_size = get_body_size(doc)
    footnote_threshold = body_size - 1.5

    paragraphs = []

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:
                continue

            # Detect end-matter heading — stop here.
            first_line_text = ""
            if block["lines"]:
                for span in block["lines"][0]["spans"]:
                    first_line_text += span["text"]
            if END_HEADING.match(first_line_text.strip()):
                doc.close()
                return "\n\n".join(paragraphs)

            # Skip small-font footnote lines only near the page bottom. Printed
            # web pages often use larger headlines than body text.
            block_lines = []
            for line in block["lines"]:
                line_text = ""
                is_footnote = False
                line_y = line["bbox"][1]
                near_page_bottom = line_y > page.rect.height * 0.72
                for span in line["spans"]:
                    if near_page_bottom and round(span["size"], 1) < footnote_threshold:
                        is_footnote = True
                        break
                    line_text += span["text"]
                if not is_footnote and line_text.strip():
                    block_lines.append(line_text.strip())
            if block_lines:
                paragraphs.append(" ".join(block_lines))

    doc.close()
    return "\n\n".join(paragraphs)


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _clean(text: str) -> str:
    text = _strip_end_matter(text)
    # Inline citations [1], [2,3], [1-5]
    text = re.sub(r"\[\d+(?:[,\-]\s*\d+)*\]", "", text)
    # (Author et al., 2023) / (Author, 2023)
    text = re.sub(r"\([A-Z][a-z]+(?:\s+et\s+al\.)?(?:\s*[,&]\s*[A-Z][a-z]+)*,?\s*\d{4}\)", "", text)
    # Superscript unicode digits
    text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", "", text)
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


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.pdf> <output.txt>", file=sys.stderr)
        sys.exit(1)

    text = extract_clean_text(sys.argv[1])
    if not text:
        print("ERROR: no text extracted", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(text)

    print(f"Extracted {len(text):,} chars → {sys.argv[2]}")

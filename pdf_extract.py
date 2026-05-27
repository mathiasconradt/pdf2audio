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
import fitz  # pymupdf


REF_HEADING = re.compile(
    r"^(?:References|Bibliography|Works Cited|REFERENCES|BIBLIOGRAPHY)\s*$"
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
    doc = fitz.open(pdf_path)
    body_size = get_body_size(doc)
    footnote_threshold = body_size - 1.5

    paragraphs = []

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:
                continue

            # Detect References heading — stop here
            first_line_text = ""
            if block["lines"]:
                for span in block["lines"][0]["spans"]:
                    first_line_text += span["text"]
            if REF_HEADING.match(first_line_text.strip()):
                doc.close()
                text = "\n\n".join(paragraphs)
                return _clean(text)

            # Skip footnote blocks
            block_lines = []
            for line in block["lines"]:
                line_text = ""
                is_footnote = False
                for span in line["spans"]:
                    if round(span["size"], 1) < footnote_threshold:
                        is_footnote = True
                        break
                    line_text += span["text"]
                if not is_footnote and line_text.strip():
                    block_lines.append(line_text.strip())
            if block_lines:
                paragraphs.append(" ".join(block_lines))

    doc.close()
    return _clean("\n\n".join(paragraphs))


def _clean(text: str) -> str:
    # Inline citations [1], [2,3], [1-5]
    text = re.sub(r"\[\d+(?:[,\-]\s*\d+)*\]", "", text)
    # (Author et al., 2023) / (Author, 2023)
    text = re.sub(r"\([A-Z][a-z]+(?:\s+et\s+al\.)?(?:\s*[,&]\s*[A-Z][a-z]+)*,?\s*\d{4}\)", "", text)
    # Superscript unicode digits
    text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", "", text)
    # Whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


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

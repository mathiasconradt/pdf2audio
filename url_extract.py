#!/usr/bin/env python3
"""Fetch URL input and prepare it for pdf2audio.

Usage: url_extract.py <http(s)-url> <temp-dir>

Prints three tab-separated fields:
  pdf|text <path-to-temp-input> <safe-base-name>
"""

import html
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
USER_AGENT = "pdf2audio/0.1 (+https://github.com/mathiasconradt/pdf2audio)"


class ReadableHTMLParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside"}
    BLOCK_TAGS = {
        "article", "main", "section", "div", "p", "br", "li", "ul", "ol",
        "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.in_title = False
        self.title_parts: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        if self.skip_depth == 0:
            self.parts.append(text)

    @property
    def title(self) -> str:
        return _normalize_text(" ".join(self.title_parts))

    @property
    def text(self) -> str:
        return _normalize_text(" ".join(self.parts))


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <http(s)-url> <temp-dir>", file=sys.stderr)
        return 1

    try:
        result_type, path, base_name = prepare_url(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"{result_type}\t{path}\t{base_name}")
    return 0


def prepare_url(url_arg: str, temp_dir_arg: str) -> tuple[str, str, str]:
    url = _validated_url(url_arg)
    temp_dir = Path(temp_dir_arg).resolve(strict=True)
    if not temp_dir.is_dir():
        raise ValueError(f"Not a temp directory: {temp_dir_arg}")

    body, content_type, final_url = _fetch(url)
    if _is_pdf(content_type, body, final_url):
        base_name = _base_name(final_url, "download")
        pdf_path = temp_dir / f"{base_name}.pdf"
        pdf_path.write_bytes(body)
        return "pdf", str(pdf_path), base_name

    if not _is_html(content_type):
        raise ValueError(f"Unsupported URL content type: {content_type or 'unknown'}")

    html_text = body.decode(_charset(content_type), errors="replace")
    text, title = _extract_readable_text(html_text, final_url)
    if _word_count(text) < 50:
        raise ValueError("Could not extract enough readable text from HTML page")

    base_name = _safe_slug(title) or _base_name(final_url, "webpage")
    text_path = temp_dir / f"{base_name}.txt"
    text_path.write_text(text, encoding="utf-8")
    return "text", str(text_path), base_name


def _validated_url(url_arg: str) -> str:
    parsed = urlparse(url_arg)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must use http or https")
    return url_arg


def _fetch(url: str) -> tuple[bytes, str, str]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "")
        final_url = response.geturl()
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_DOWNLOAD_BYTES:
            raise ValueError("URL response is too large")
        body = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(body) > MAX_DOWNLOAD_BYTES:
            raise ValueError("URL response is too large")
        return body, content_type, final_url


def _is_pdf(content_type: str, body: bytes, url: str) -> bool:
    return (
        "application/pdf" in content_type.lower()
        or body.startswith(b"%PDF-")
        or urlparse(url).path.lower().endswith(".pdf")
    )


def _is_html(content_type: str) -> bool:
    lowered = content_type.lower()
    return not lowered or "text/html" in lowered or "application/xhtml+xml" in lowered


def _charset(content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.IGNORECASE)
    return match.group(1).strip("\"'") if match else "utf-8"


def _extract_readable_text(html_text: str, url: str) -> tuple[str, str]:
    trafilatura_text = _extract_with_trafilatura(html_text, url)
    fallback_text, title = _extract_with_html_parser(html_text)
    text = trafilatura_text if _word_count(trafilatura_text) >= 50 else fallback_text
    return text, title


def _extract_with_trafilatura(html_text: str, url: str) -> str:
    try:
        import trafilatura
    except ImportError:
        return ""
    extracted = trafilatura.extract(
        html_text,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_recall=True,
    )
    return _normalize_text(extracted or "")


def _extract_with_html_parser(html_text: str) -> tuple[str, str]:
    parser = ReadableHTMLParser()
    parser.feed(html_text)
    return parser.text, parser.title


def _normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _base_name(url: str, fallback: str) -> str:
    path_name = Path(unquote(urlparse(url).path)).stem
    return _safe_slug(path_name) or fallback


def _safe_slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = value.strip(".-_")
    return value[:80]


if __name__ == "__main__":
    sys.exit(main())

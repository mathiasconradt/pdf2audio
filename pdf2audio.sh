#!/bin/bash
# PDF → Audio (opus, ~24kbps — most compressed)
# Deps: pymupdf (uv pip install pymupdf), poppler/pdftotext, ffmpeg, kokoro (uv pip install kokoro)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KOKORO="${SCRIPT_DIR}/.venv/bin/kokoro"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"
PDF_EXTRACT="${SCRIPT_DIR}/pdf_extract.py"
PDF_BROWSER="${SCRIPT_DIR}/pdf_browser.py"
URL_EXTRACT="${SCRIPT_DIR}/url_extract.py"

VOICE="af_heart"   # American-English female; change e.g. to am_adam, bf_emma, bm_george …
SPEED=1.0          # speech speed (1.0 = normal)

# --- SPINNER ---
spinner_start() {
    local msg="$1"
    local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
    local i=0
    while true; do
        printf "\r  %s  %s " "${frames[$((i % 10))]}" "$msg"
        sleep 0.1
        ((i++))
    done &
    SPINNER_PID=$!
    return 0
}
spinner_stop() {
    kill "$SPINNER_PID" 2>/dev/null
    wait "$SPINNER_PID" 2>/dev/null
    printf "\r\033[2K"
    return 0
}

# --- PARSE ARGS ---
SELECTED_FILE=""
OPEN_AFTER=1

show_help() {
    cat <<EOF
pdf2audio — Convert PDF to audio (opus) using local TTS
© 2026 Mathias Conradt • MIT License • https://github.com/mathiasconradt/pdf2audio

Usage:
  ./pdf2audio.sh [options]

Options:
  --file=PATH   Path to input PDF file or http(s) URL
                (omit to open interactive file browser)
  --open        Open the output audio file after conversion (default on)
  --help        Show this help message

Examples:
  ./pdf2audio.sh
  ./pdf2audio.sh --file=~/Downloads/paper.pdf
  ./pdf2audio.sh --file=https://example.com/article
  ./pdf2audio.sh --file=~/Downloads/paper.pdf --open
EOF
    return 0
}

is_url() {
    [[ "$1" =~ ^https?:// ]]
}

for arg in "$@"; do
    case "$arg" in
        --file=*)   SELECTED_FILE="${arg#--file=}"; SELECTED_FILE="${SELECTED_FILE/#\~/$HOME}" ;;
        --open)     OPEN_AFTER=1 ;;
        --help|-h)  show_help; exit 0 ;;
        *) echo "Unknown option: $arg"; echo "Run ./pdf2audio.sh --help for usage."; exit 1 ;;
    esac
done

# --- 1. SELECT FILE ---
if [[ -z "$SELECTED_FILE" ]]; then
    BROWSER_TMP=$(mktemp -t pdf_browser_XXXXXX)
    "$PYTHON" "$PDF_BROWSER" . "$BROWSER_TMP" "$OPEN_AFTER"
    BROWSER_EXIT=$?
    if [[ -s "$BROWSER_TMP" ]]; then
        OPEN_AFTER=$(sed -n '1p' "$BROWSER_TMP")
        SELECTED_FILE=$(sed '1d' "$BROWSER_TMP")
    fi
    rm -f "$BROWSER_TMP"
    if [[ $BROWSER_EXIT -ne 0 ]] || [[ -z "$SELECTED_FILE" ]]; then
        echo "No file selected."
        exit 1
    fi
fi

# --- 2. CHECK DEPS ---
for cmd in ffmpeg; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Missing: $cmd"
        [[ "$cmd" = "ffmpeg" ]] && echo "  → brew install ffmpeg"
        exit 1
    fi
done

if [[ ! -x "$PYTHON" ]]; then
    echo "Missing: python venv not found at $PYTHON"
    exit 1
fi
if ! "$PYTHON" -c "import fitz" &>/dev/null; then
    echo "Missing: pymupdf not installed"
    echo "  → uv pip install pymupdf"
    exit 1
fi

if [[ ! -x "$KOKORO" ]]; then
    echo "Missing: kokoro not found at $KOKORO"
    echo "  → uv pip install kokoro"
    exit 1
fi

TEMP_DIR=$(mktemp -d -t pdf2audio_XXXXXX)
SOURCE_KIND="pdf"

if is_url "$SELECTED_FILE"; then
    spinner_start "🌐 Fetching URL..."
    URL_RESULT=$("$PYTHON" "$URL_EXTRACT" "$SELECTED_FILE" "$TEMP_DIR")
    URL_EXIT=$?
    spinner_stop
    if [[ $URL_EXIT -ne 0 ]]; then
        echo "$URL_RESULT"
        rmdir "$TEMP_DIR" 2>/dev/null || true
        exit 1
    fi

    IFS=$'\t' read -r SOURCE_KIND SELECTED_FILE FILENAME_NO_EXT <<< "$URL_RESULT"
    INPUT_DIR="$PWD"
    FILENAME="${FILENAME_NO_EXT}.${SOURCE_KIND}"
else
    INPUT_DIR=$(dirname "$SELECTED_FILE")
    FILENAME=$(basename -- "$SELECTED_FILE")
    FILENAME_NO_EXT="${FILENAME%.*}"
fi

TEMP_TXT="${TEMP_DIR}/${FILENAME_NO_EXT}.txt"
TEMP_WAV="${TEMP_DIR}/${FILENAME_NO_EXT}.wav"
OUTPUT="${INPUT_DIR}/${FILENAME_NO_EXT}.opus"


# --- 3. EXTRACT TEXT ---
if [[ "$SOURCE_KIND" = "text" ]]; then
    TEMP_TXT="$SELECTED_FILE"
    EXTRACT_EXIT=0
    echo "🌐 Web text extracted."
else
    spinner_start "📄 Extracting text from $FILENAME (stripping footnotes & references)..."
    "$PYTHON" "$PDF_EXTRACT" "$SELECTED_FILE" "$TEMP_TXT"
    EXTRACT_EXIT=$?
    spinner_stop
    echo "📄 Text extracted."
fi

if [[ $EXTRACT_EXIT -ne 0 ]] || [[ ! -s "$TEMP_TXT" ]]; then
    echo "Text extraction failed or PDF is empty/image-only."
    rm -f "$TEMP_TXT" "$TEMP_WAV"
    rmdir "$TEMP_DIR" 2>/dev/null || true
    exit 1
fi

# --- 4. TTS → WAV (kokoro) ---
WORD_COUNT=$(wc -w < "$TEMP_TXT")
ESTIMATED_MIN=$(echo "$WORD_COUNT / 150" | bc)
spinner_start "🗣️  Synthesizing speech (voice: $VOICE, speed: ${SPEED}x, ~${ESTIMATED_MIN} min estimated)..."
"$KOKORO" -i "$TEMP_TXT" -m "$VOICE" -s "$SPEED" -o "$TEMP_WAV"
TTS_EXIT=$?
spinner_stop
echo "🗣️  Speech synthesis done."

if [[ $TTS_EXIT -ne 0 ]] || [[ ! -f "$TEMP_WAV" ]]; then
    echo "Speech synthesis failed."
    rm -f "$TEMP_TXT" "$TEMP_WAV"
    rmdir "$TEMP_DIR" 2>/dev/null || true
    exit 1
fi

# --- 5. ENCODE OPUS ---
spinner_start "🎵 Encoding to opus (~24kbps, max compression)..."
ffmpeg -i "$TEMP_WAV" \
    -c:a libopus \
    -b:a 24k \
    -vbr on \
    -compression_level 10 \
    -application voip \
    "$OUTPUT" -y -loglevel error
spinner_stop
echo "🎵 Encoding done."

# --- 6. CLEANUP ---
rm -f "$TEMP_TXT" "$TEMP_WAV"
rmdir "$TEMP_DIR" 2>/dev/null || true

SIZE=$(du -sh "$OUTPUT" 2>/dev/null | cut -f1)
echo "✨ Done! → ${OUTPUT} (${SIZE})"
if [[ $OPEN_AFTER -eq 1 ]]; then
    open "$OUTPUT"
fi

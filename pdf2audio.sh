#!/bin/bash
# PDF → Audio (opus, ~24kbps — most compressed)
# Deps: pymupdf (uv pip install pymupdf), ffmpeg, kokoro (uv pip install kokoro)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KOKORO="${SCRIPT_DIR}/.venv/bin/kokoro"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"
PDF_EXTRACT="${SCRIPT_DIR}/pdf_extract.py"
PDF_BROWSER="${SCRIPT_DIR}/pdf_browser.py"

VOICE="af_heart"   # American-English female; change e.g. to am_adam, bf_emma, bm_george …
SPEED=1.0          # speech speed (1.0 = normal)

# --- 1. SELECT FILE ---
if [ -z "$1" ]; then
    BROWSER_TMP=$(mktemp /tmp/pdf_browser_XXXXXX)
    "$PYTHON" "$PDF_BROWSER" . "$BROWSER_TMP"
    BROWSER_EXIT=$?
    SELECTED_FILE=$(cat "$BROWSER_TMP" 2>/dev/null)
    rm -f "$BROWSER_TMP"
    if [ $BROWSER_EXIT -ne 0 ] || [ -z "$SELECTED_FILE" ]; then
        echo "No file selected."
        exit 1
    fi
else
    SELECTED_FILE="${1/#\~/$HOME}"
fi

# --- 2. CHECK DEPS ---
for cmd in ffmpeg; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Missing: $cmd"
        [ "$cmd" = "ffmpeg" ] && echo "  → brew install ffmpeg"
        exit 1
    fi
done

if [ ! -x "$PYTHON" ]; then
    echo "Missing: python venv not found at $PYTHON"
    exit 1
fi
if ! "$PYTHON" -c "import fitz" &>/dev/null; then
    echo "Missing: pymupdf not installed"
    echo "  → uv pip install pymupdf"
    exit 1
fi

if [ ! -x "$KOKORO" ]; then
    echo "Missing: kokoro not found at $KOKORO"
    echo "  → uv pip install kokoro"
    exit 1
fi

INPUT_DIR=$(dirname "$SELECTED_FILE")
FILENAME=$(basename -- "$SELECTED_FILE")
FILENAME_NO_EXT="${FILENAME%.*}"
TEMP_TXT="/tmp/${FILENAME_NO_EXT}.txt"
TEMP_WAV="/tmp/${FILENAME_NO_EXT}.wav"
OUTPUT="${INPUT_DIR}/${FILENAME_NO_EXT}.opus"


# --- 3. EXTRACT TEXT ---
echo "📄 Extracting text from $FILENAME (stripping footnotes & references)..."
"$PYTHON" "$PDF_EXTRACT" "$SELECTED_FILE" "$TEMP_TXT"

if [ $? -ne 0 ] || [ ! -s "$TEMP_TXT" ]; then
    echo "Text extraction failed or PDF is empty/image-only."
    rm -f "$TEMP_TXT"
    exit 1
fi

# --- 4. TTS → WAV (kokoro) ---
echo "🗣️  Synthesizing speech (voice: $VOICE, speed: ${SPEED}x)..."
"$KOKORO" -i "$TEMP_TXT" -m "$VOICE" -s "$SPEED" -o "$TEMP_WAV"

if [ ! -f "$TEMP_WAV" ]; then
    echo "Speech synthesis failed."
    rm -f "$TEMP_TXT"
    exit 1
fi

# --- 5. ENCODE OPUS ---
echo "🎵 Encoding to opus (~24kbps, max compression)..."
ffmpeg -i "$TEMP_WAV" \
    -c:a libopus \
    -b:a 24k \
    -vbr on \
    -compression_level 10 \
    -application voip \
    "$OUTPUT" -y -loglevel error

# --- 6. CLEANUP ---
rm -f "$TEMP_TXT" "$TEMP_WAV"

SIZE=$(du -sh "$OUTPUT" 2>/dev/null | cut -f1)
echo "✨ Done! → ${OUTPUT} (${SIZE})"
open "$OUTPUT"

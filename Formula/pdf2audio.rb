class Pdf2audio < Formula
  desc "Convert PDF documents to audio (opus) using local TTS"
  homepage "https://github.com/mathiasconradt/pdf2audio"
  url "https://github.com/mathiasconradt/pdf2audio/archive/refs/tags/v0.1.7.tar.gz"
  sha256 "444a07f8ce9796c531edceb133b074fa98d41154e5f39abb4f3822f37886b6ed"
  head "https://github.com/mathiasconradt/pdf2audio.git", branch: "main"
  license "MIT"

  depends_on "ffmpeg"
  depends_on "poppler"
  depends_on "python@3.12"
  depends_on "uv"

  def install
    libexec.install Dir["*"]

    # Create venv explicitly forcing Homebrew's Python 3.12 binary
    system "uv", "venv", libexec/".venv", "--python", "#{Formula["python@3.12"].opt_bin}/python3.12"
    
    # Target libexec directory and tell uv to install the app and its pyproject.toml deps
    cd libexec do
      system "uv", "pip", "install", "--python", libexec/".venv/bin/python", "."
    end

    # Patch SCRIPT_DIR references to point to libexec
    inreplace libexec/"pdf2audio.sh",
              'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
              "SCRIPT_DIR=\"#{libexec}\""

    bin.install_symlink libexec/"pdf2audio.sh" => "pdf2audio"
  end

  def caveats
    <<~EOS
      On first run, Kokoro will download model weights (~300MB) from Hugging Face.
      This requires an internet connection the first time only.
    EOS
  end

  test do
    assert_match "pdf2audio", shell_output("#{bin}/pdf2audio --help")
  end
end

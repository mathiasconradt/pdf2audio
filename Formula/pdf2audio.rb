class Pdf2audio < Formula
  desc "Convert PDF documents to audio (opus) using local TTS"
  homepage "https://github.com/mathiasconradt/pdf2audio"
  url "https://github.com/mathiasconradt/pdf2audio/archive/refs/tags/v0.1.1.tar.gz"
  sha256 "b29f7cce43d746c9dd60b243a77d4203cbdf934f12585c8409bf1d75f7bc04f8"
  head "https://github.com/mathiasconradt/pdf2audio.git", branch: "main"
  license "MIT"

  depends_on "ffmpeg"
  depends_on "python@3.12"
  depends_on "uv"

  def install
    libexec.install Dir["*"]

    # Create venv explicitly forcing Homebrew's Python 3.12 binary
    # to bypass both macOS 3.9.6 and any incompatible global Python versions (like 3.14)
    system "uv", "venv", libexec/".venv", "--python", "#{Formula["python@3.12"].opt_bin}/python3.12"
    
    # Install Python deps via uv inside that venv
    system "uv", "pip", "install",
           "--python", libexec/".venv/bin/python",
           "kokoro>=0.9.4", "pymupdf>=1.27.0", "torch>=2.0.0"

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
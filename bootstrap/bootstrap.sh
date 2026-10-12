#!/usr/bin/env bash
# AICC Engineering Toolkit — macOS / Linux one-command bootstrapper.
#
# TRUE one command on a fresh machine: this script assumes NOTHING is installed
# except a POSIX shell and curl (both ship with macOS and every mainstream
# Linux). It detects / installs the prerequisites the AICC installer needs,
# fetches a PINNED Toolkit release, and hands off to installer/install.py.
#
# What it coordinates, in order:
#   1. Detect OS + CPU arch; refuse unsupported combinations honestly.
#   2. Detect Python 3 (>= 3.9); if missing, install with explicit consent via
#      the official platform mechanism (Homebrew when present, else the official
#      python.org installer on macOS; the distro package manager on Linux).
#   3. Detect git; install with consent if missing (not required to GET the
#      toolkit — we use a release archive — but handy for the engineer's work).
#   4. Acquire the Toolkit: when run from inside a checkout, use it in place;
#      otherwise download the PINNED release source archive over TLS and verify
#      its SHA-256 against a value the engineer can pin/override.
#   5. Hand off to installer/install.py, which (per its own consent prompts)
#      selects/uses the AI harness, installs+verifies the official AWS Labs
#      AI-DLC runtime, wires the sync hook, registers the project against the
#      default Workbench endpoint, and opens the engineer's Workbench.
#
# Security: no hidden elevation (user-scope installs only), no remote script is
# executed without consent, downloads are integrity-checked where a digest is
# available, and nothing here ever prints an update_token or a Workbench secret
# (those live only inside install.py's project config).
#
# Usage:
#   bootstrap.sh [--target <dir>] [--harness <id>] [--tool <legacy-id>]
#                [--yes] [--no-browser] [--ref <git-tag>] [--sha256 <digest>]
#                [--dry-run] [--help]
#
# Harness ids (official AWS Labs AI-DLC): claude, kiro, kiro-ide, codex, cursor,
# opencode, copilot. --tool accepts the legacy claude-code|kiro-cli aliases.
# If omitted, install.py detects an installed tool or prompts.
#
# Non-interactive automation: pass --yes (consents to prerequisite installs) and
# --harness. --dry-run prints the plan and changes nothing.
set -euo pipefail

# --------------------------------------------------------------------------
# Pinned release the bootstrapper fetches when NOT run from a checkout.
# Override with --ref (and --sha256 for the archive digest). Prefer a pinned,
# verifiable tag over a moving branch.
# --------------------------------------------------------------------------
TOOLKIT_REPO="lxrsd/AICC_Engineering_Toolkit"
DEFAULT_REF="v0.1.0"
MIN_PY_MINOR=9   # require Python 3.9+

TARGET=""
TOOL=""
HARNESS=""
ASSUME_YES=0
NO_BROWSER=0
DRY_RUN=0
REF="$DEFAULT_REF"
EXPECT_SHA256=""

say()  { printf '%s\n' "$*"; }
info() { printf '  %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
err()  { printf 'ERROR: %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

usage() {
  sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

confirm() {
  # confirm "<prompt>"  -> 0 if yes
  local prompt="$1"
  if [ "$ASSUME_YES" -eq 1 ]; then return 0; fi
  if [ ! -t 0 ]; then
    warn "no TTY and --yes not given; declining: $prompt"
    return 1
  fi
  printf '%s [y/N] ' "$prompt"
  local ans=""; read -r ans || true
  case "$ans" in y|Y|yes|YES) return 0;; *) return 1;; esac
}

run() {
  # run <cmd...>  — echo under --dry-run, otherwise execute.
  if [ "$DRY_RUN" -eq 1 ]; then info "DRY-RUN would run: $*"; return 0; fi
  "$@"
}

# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="${2:-}"; shift 2;;
    --harness) HARNESS="${2:-}"; shift 2;;
    --tool) TOOL="${2:-}"; shift 2;;
    --yes|-y) ASSUME_YES=1; shift;;
    --no-browser) NO_BROWSER=1; shift;;
    --ref) REF="${2:-}"; shift 2;;
    --sha256) EXPECT_SHA256="${2:-}"; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    --help|-h) usage;;
    *) die "unknown argument: $1 (try --help)";;
  esac
done

say "== AICC Engineering Toolkit bootstrap (macOS/Linux) =="

# --------------------------------------------------------------------------
# 1. OS + CPU detection; honest refusal of unsupported combos.
# --------------------------------------------------------------------------
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS" in
  Darwin) OS_NAME="macOS";;
  Linux)  OS_NAME="Linux";;
  *) die "unsupported OS '$OS'. This bootstrapper supports macOS and Linux; on Windows use bootstrap.ps1.";;
esac
case "$ARCH" in
  arm64|aarch64) ARCH_NAME="arm64";;
  x86_64|amd64)  ARCH_NAME="x64";;
  *) die "unsupported CPU architecture '$ARCH'. Supported: arm64 (Apple Silicon) and x86_64.";;
esac
info "Detected: $OS_NAME / $ARCH_NAME"

need_cmd() { command -v "$1" >/dev/null 2>&1; }

command -v curl >/dev/null 2>&1 || die "curl is required to bootstrap and was not found. Install curl, then re-run."

# --------------------------------------------------------------------------
# 2. Python 3 (>= 3.9)
# --------------------------------------------------------------------------
PYTHON=""
pick_python() {
  local c
  for c in python3 python; do
    if need_cmd "$c"; then
      if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, '"$MIN_PY_MINOR"') else 1)' 2>/dev/null; then
        PYTHON="$c"; return 0
      fi
    fi
  done
  return 1
}

install_python_macos() {
  if need_cmd brew; then
    info "Installing Python 3 via Homebrew (official formula)…"
    run brew install python
    return $?
  fi
  warn "Homebrew not found. The official python.org installer requires a GUI package install."
  warn "Install Python 3 from https://www.python.org/downloads/macos/ (official, signed), then re-run."
  warn "Or install Homebrew first: https://brew.sh"
  return 1
}

install_python_linux() {
  if   need_cmd apt-get; then info "Installing python3 via apt…"; run sudo apt-get update && run sudo apt-get install -y python3; 
  elif need_cmd dnf;     then info "Installing python3 via dnf…";  run sudo dnf install -y python3;
  elif need_cmd yum;     then info "Installing python3 via yum…";  run sudo yum install -y python3;
  elif need_cmd pacman;  then info "Installing python3 via pacman…"; run sudo pacman -S --noconfirm python;
  elif need_cmd zypper;  then info "Installing python3 via zypper…"; run sudo zypper install -y python3;
  else
    warn "No supported package manager found. Install Python 3.$MIN_PY_MINOR+ from your distro, then re-run."
    return 1
  fi
}

if pick_python; then
  info "Python: $("$PYTHON" --version 2>&1) ($(command -v "$PYTHON"))"
else
  warn "A supported Python 3 ($MIN_PY_MINOR+) was not found."
  if confirm "Install Python 3 now using the official platform mechanism?"; then
    if [ "$OS_NAME" = "macOS" ]; then install_python_macos || die "Python install did not complete. See guidance above."
    else install_python_linux || die "Python install did not complete. See guidance above."; fi
    if [ "$DRY_RUN" -eq 0 ]; then
      pick_python || die "Python still not detected after install. Open a new terminal (PATH) and re-run."
      info "Python: $("$PYTHON" --version 2>&1)"
    else
      PYTHON="python3"  # dry-run placeholder
    fi
  else
    die "Python 3 is required and installation was declined. Install Python 3.$MIN_PY_MINOR+ and re-run."
  fi
fi

# --------------------------------------------------------------------------
# 3. Git (optional for bootstrap; useful for the engineer's own work)
# --------------------------------------------------------------------------
if need_cmd git; then
  info "git: $(git --version 2>&1)"
else
  warn "git not found (not required to install the Toolkit; recommended for your project work)."
  if confirm "Install git now?"; then
    if [ "$OS_NAME" = "macOS" ]; then
      if need_cmd brew; then run brew install git; else warn "Install Xcode Command Line Tools: xcode-select --install"; fi
    else
      if   need_cmd apt-get; then run sudo apt-get install -y git;
      elif need_cmd dnf;     then run sudo dnf install -y git;
      elif need_cmd yum;     then run sudo yum install -y git;
      elif need_cmd pacman;  then run sudo pacman -S --noconfirm git;
      elif need_cmd zypper;  then run sudo zypper install -y git; fi
    fi
  fi
fi

# --------------------------------------------------------------------------
# 4. Acquire the Toolkit (no git clone required): use a local checkout if we
#    are inside one, else download the PINNED release archive and verify it.
# --------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLKIT_DIR=""
CLEANUP_DIR=""

if [ -f "$SCRIPT_DIR/../installer/install.py" ]; then
  TOOLKIT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  info "Using the Toolkit from this checkout: $TOOLKIT_DIR"
else
  WORKDIR="$(mktemp -d)"; CLEANUP_DIR="$WORKDIR"
  ARCHIVE="$WORKDIR/toolkit.tar.gz"
  URL="https://github.com/$TOOLKIT_REPO/archive/refs/tags/$REF.tar.gz"
  info "Downloading pinned Toolkit $REF over TLS:"
  info "  $URL"
  if [ "$DRY_RUN" -eq 1 ]; then
    info "DRY-RUN would download and verify the archive, then extract it."
    TOOLKIT_DIR="$WORKDIR/AICC_Engineering_Toolkit-pinned"
  else
    if ! curl -fsSL --proto '=https' --tlsv1.2 "$URL" -o "$ARCHIVE"; then
      err "download failed. Common corporate causes:"
      err "  • outbound HTTPS to github.com blocked, or a TLS-inspecting proxy."
      err "  • set HTTPS_PROXY/HTTP_PROXY, or ask IT to allowlist github.com, then re-run."
      die "could not obtain the Toolkit release $REF."
    fi
    if [ -n "$EXPECT_SHA256" ]; then
      info "Verifying archive SHA-256…"
      ACTUAL="$( (shasum -a 256 "$ARCHIVE" 2>/dev/null || sha256sum "$ARCHIVE") | awk '{print $1}')"
      [ "$ACTUAL" = "$EXPECT_SHA256" ] || die "archive SHA-256 mismatch: expected $EXPECT_SHA256, got $ACTUAL. Aborting (integrity)."
      info "SHA-256 OK."
    else
      warn "no --sha256 provided; skipping digest verification (GitHub TLS still protects transport)."
      warn "For a verifiable install, pass --sha256 <digest> from the release notes."
    fi
    tar -xzf "$ARCHIVE" -C "$WORKDIR"
    TOOLKIT_DIR="$(find "$WORKDIR" -maxdepth 1 -type d -name 'AICC_Engineering_Toolkit-*' | head -n1)"
    [ -n "$TOOLKIT_DIR" ] && [ -f "$TOOLKIT_DIR/installer/install.py" ] || die "extracted archive missing installer/install.py."
    info "Extracted to $TOOLKIT_DIR"
  fi
fi

cleanup() { [ -n "$CLEANUP_DIR" ] && rm -rf "$CLEANUP_DIR" 2>/dev/null || true; }
trap cleanup EXIT

# --------------------------------------------------------------------------
# 5. Hand off to the existing installer. It owns harness selection, the AWS
#    Labs runtime install+verify, sync-hook wiring, Workbench registration
#    against the default endpoint, and opening the engineer's Workbench.
# --------------------------------------------------------------------------
if [ -z "$TARGET" ]; then
  if [ -t 0 ] && [ "$ASSUME_YES" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
    printf 'Project directory for your AI-DLC build: '
    read -r TARGET || true
  fi
  [ -n "$TARGET" ] || die "a project directory is required. Pass --target <dir>."
fi

INSTALL_ARGS=( "$TOOLKIT_DIR/installer/install.py" --target "$TARGET" )
# The installer may install the runtime with its own explicit consent prompt.
INSTALL_ARGS+=( --allow-runtime-install )
[ -n "$HARNESS" ] && INSTALL_ARGS+=( --harness "$HARNESS" )
[ -n "$TOOL" ] && INSTALL_ARGS+=( --tool "$TOOL" )
[ "$ASSUME_YES" -eq 1 ] && INSTALL_ARGS+=( --yes )
[ "$NO_BROWSER" -eq 1 ] && INSTALL_ARGS+=( --no-browser )
[ "$DRY_RUN" -eq 1 ] && INSTALL_ARGS+=( --dry-run )

say ""
say "Handing off to the AICC installer…"
info "$PYTHON ${INSTALL_ARGS[*]}"
say ""
if [ "$DRY_RUN" -eq 1 ]; then
  # In dry-run we still invoke install.py --dry-run so the engineer sees the
  # full downstream plan (it writes/opens nothing).
  "$PYTHON" "${INSTALL_ARGS[@]}"
else
  exec "$PYTHON" "${INSTALL_ARGS[@]}"
fi

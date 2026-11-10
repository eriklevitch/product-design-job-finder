#!/bin/bash
# Installs (or updates) Product Design Job Finder.
#
#   curl -fsSL https://raw.githubusercontent.com/eriklevitch/product-design-job-finder/main/install.sh | bash
#
# What it does, in order:
#   1. Checks that Python 3.10 or newer is installed.
#   2. Downloads this project into a "job-search" folder in your home folder.
#      If the folder already exists, it updates the code and leaves your
#      settings, notes, keys and tracker alone.
#   3. Installs the libraries it needs into that folder (nothing system-wide).
#   4. Starts the setup questions.
set -e

REPO="${JOBSEARCH_REPO:-eriklevitch/product-design-job-finder}"
DEST="${JOBSEARCH_DIR:-$HOME/job-search}"
# For testing: copy from a local folder instead of downloading.
LOCAL_SOURCE="${JOBSEARCH_SOURCE_DIR:-}"

bold() { printf "\n\033[1m%s\033[0m\n" "$1"; }

bold "Product Design Job Finder: installing"

# 1. Python ---------------------------------------------------------
PY=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    PY="$(command -v "$candidate")"
    break
  fi
done
if [ -z "$PY" ]; then
  echo
  echo "This needs Python 3.10 or newer, which isn't on your Mac yet."
  echo "  1. Go to https://www.python.org/downloads/ and click the yellow Download button."
  echo "  2. Open the downloaded file and click Continue until it's done."
  echo "  3. Come back to Terminal and paste the install line again."
  exit 1
fi
echo "Using $("$PY" --version)"

# 2. Download -------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if [ -n "$LOCAL_SOURCE" ]; then
  SRC="$LOCAL_SOURCE"
else
  echo "Downloading..."
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.zip" -o "$TMP/src.zip"
  unzip -q "$TMP/src.zip" -d "$TMP"
  SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
fi
mkdir -p "$DEST"
# Copy the code. Your own files (config.yaml, portfolio_notes.md, .env,
# applications.csv, drafts/) aren't part of the download, so they're kept.
( cd "$SRC" && tar --exclude='./venv' --exclude='./.git' --exclude='./config.yaml' \
    --exclude='./portfolio_notes.md' --exclude='./.env' --exclude='./applications.csv' \
    --exclude='./drafts' --exclude='__pycache__' --exclude='.pytest_cache' -cf - . ) |
  ( cd "$DEST" && tar -xf - )

# 3. Libraries ------------------------------------------------------
echo "Installing (this takes a minute the first time)..."
if [ ! -x "$DEST/venv/bin/python" ]; then
  "$PY" -m venv "$DEST/venv"
fi
"$DEST/venv/bin/python" -m pip install --quiet --upgrade pip
"$DEST/venv/bin/python" -m pip install --quiet --upgrade -r "$DEST/requirements.txt"

# Let the double-click files open without a security warning.
chmod +x "$DEST"/*.command
xattr -d com.apple.quarantine "$DEST"/*.command 2>/dev/null || true

bold "Installed in $DEST"

# 4. Setup ----------------------------------------------------------
if [ -z "$JOBSEARCH_SKIP_SETUP" ] && { [ -t 0 ] || [ -r /dev/tty ]; }; then
  cd "$DEST"
  "$DEST/venv/bin/python" engine/setup_wizard.py < /dev/tty || true
fi

if [ -z "$JOBSEARCH_SKIP_SETUP" ] && command -v open >/dev/null 2>&1; then
  open "$DEST"
fi
bold "Done. Your job-search folder is open in Finder."
echo "Every week: double-click 'Find Jobs', then 'Open Tracker'."

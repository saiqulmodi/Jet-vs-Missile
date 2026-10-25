#!/usr/bin/env bash
# Builds the Android app (.apk) inside WSL Ubuntu and copies it to bin\ on Windows.
#   wsl -e bash -l tools/build_android.sh
#
# Buildozer is slow and fragile on the Windows drive (/mnt/c), so the game
# files are copied to ~/JetVsMissile (Linux disk) first and built there.
# The build tools (~/dwd-buildenv, ~/dwd-cython) are shared with Domino Game.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$HOME/JetVsMissile"
ENV="$HOME/dwd-buildenv"
export PATH="$HOME/.local/bin:$PATH"
# Java on WSL can hang trying IPv6 first (Gradle download timed out); use IPv4
export JAVA_TOOL_OPTIONS="-Djava.net.preferIPv4Stack=true"
# low-RAM laptop: one Gradle worker, no daemon, two compile jobs
export GRADLE_OPTS="-Xmx1536m -Dorg.gradle.daemon=false -Dorg.gradle.workers.max=1"
export MAKEFLAGS=-j2

if [ ! -x "$ENV/bin/buildozer" ]; then
  echo "=== setting up the build tools (once)"
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
  uv python install 3.11
  uv venv -p 3.11 --seed "$ENV"
  "$ENV/bin/pip" install -q "cython==0.29.37" buildozer setuptools wheel
fi
# a modern Cython for pygame's C code (p4a-recipes/pygame)
if [ ! -x "$HOME/dwd-cython/bin/cython" ]; then
  uv venv -p 3.11 --seed "$HOME/dwd-cython"
  "$HOME/dwd-cython/bin/pip" install -q "cython>=3.1,<3.2" setuptools
fi
. "$ENV/bin/activate"

echo "=== copying game files to $WORK"
mkdir -p "$WORK"
rsync -a --delete \
  --exclude .git --exclude venv --exclude docs --exclude build --exclude bin \
  --exclude .buildozer --exclude __pycache__ --exclude tests --exclude .pytest_cache \
  "$SRC/" "$WORK/"

cd "$WORK"
echo "=== buildozer android debug (the first build takes 20-40 minutes)"
# "< <(yes)" answers yes to licence questions and keeps buildozer's own exit code
buildozer android debug < <(yes)
OUT="$(ls -t bin/*.apk | head -1)"

mkdir -p "$SRC/bin"
cp "$OUT" "$SRC/bin/JetVsMissile.apk"
echo "=== ready: $SRC/bin/JetVsMissile.apk"

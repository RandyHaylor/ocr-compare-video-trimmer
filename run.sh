#!/usr/bin/env sh
# macOS / Linux launcher. Installs uv if needed; uv then installs Python and the dependencies.
# No arguments opens the web UI; with arguments it runs the command line tool.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    else
        wget -qO- https://astral.sh/uv/install.sh | sh
    fi
    PATH="$HOME/.local/bin:$PATH"
fi

exec uv run --project "$DIR" ocr-compare-video-trimmer "$@"

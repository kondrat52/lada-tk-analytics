#!/bin/sh
# One-time setup: a Python 3.12 environment at ~/.venvs/hockey with the pipeline's packages.
# macOS ships Python 3.9, which current yt-dlp no longer supports, so uv fetches a standalone 3.12.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ENV=${HOCKEY_ENV:-$HOME/.venvs/hockey}
if [ -x "$ENV/bin/python" ]; then
  echo "environment already exists: $ENV"
else
  if command -v uv >/dev/null 2>&1; then
    UV=uv
  else
    # bootstrap uv into a throwaway venv using the system python
    python3 -m venv "$HOME/.venvs/uv-bootstrap"
    "$HOME/.venvs/uv-bootstrap/bin/pip" install -q uv
    UV="$HOME/.venvs/uv-bootstrap/bin/uv"
  fi
  "$UV" venv -q --python 3.12 "$ENV"
  "$UV" pip install -q --python "$ENV/bin/python" -r "$HERE/requirements.txt"
fi
"$ENV/bin/python" -c "import torch, ultralytics, rapidocr, yt_dlp; print('ok: torch', torch.__version__, '| mps', torch.backends.mps.is_available())"

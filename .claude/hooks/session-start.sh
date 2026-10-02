#!/usr/bin/env bash
# Ensure UREME's Python dependencies are present when a Claude Code session starts.
# Never fails the session: missing network just leaves a message.
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0
if ! python3 -c "import docx, scipy, statsmodels, rich, matplotlib, requests" 2>/dev/null; then
  echo "UREME: installing Python dependencies from requirements.txt ..."
  python3 -m pip install -q -r requirements.txt >/dev/null 2>&1 \
    && echo "UREME: dependencies installed." \
    || echo "UREME: dependency install failed; run 'pip install -r requirements.txt' manually."
fi
exit 0

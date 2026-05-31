#!/usr/bin/env bash
# Install the wealth-planning skill suite into ~/.claude/skills (macOS / Linux).
#
# Copies the 7 skills from this repo's skills/ folder into the user's Claude skills
# directory. Optionally persists GUAP_ORCH_ROOT and runs a quick verification.
#
# Usage:
#   ./install.sh [--set-env] [--verify]
#
#   --set-env   Append `export GUAP_ORCH_ROOT=<repo>/orchestrator` to your shell rc
#               (~/.bashrc or ~/.zshrc). Otherwise guap.py only auto-finds the
#               orchestrator if this repo is at ~/projects/LOCALSonly or ~/LOCALSonly.
#   --verify    After installing, run the compliance unit tests and a guap smoke check.

set -euo pipefail

SET_ENV=0
VERIFY=0
for arg in "$@"; do
  case "$arg" in
    --set-env) SET_ENV=1 ;;
    --verify)  VERIFY=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$REPO_ROOT/skills"
ORCH_ROOT="$REPO_ROOT/orchestrator"
SKILLS_DEST="$HOME/.claude/skills"

echo "Wealth-planning suite installer"
echo "  repo:        $REPO_ROOT"
echo "  skills dest: $SKILLS_DEST"

[ -d "$SKILLS_SRC" ] || { echo "skills/ not found at $SKILLS_SRC" >&2; exit 1; }
mkdir -p "$SKILLS_DEST"

# Python check (3.8+ required; suite is pure stdlib)
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "WARNING: Python not found on PATH. Skills install, but scripts need Python 3.8+." >&2
else
  echo "  python:      $PY"
fi

count=0
for d in "$SKILLS_SRC"/*/; do
  name="$(basename "$d")"
  rm -rf "${SKILLS_DEST:?}/$name"
  cp -R "$d" "$SKILLS_DEST/$name"
  echo "  installed -> $name"
  count=$((count + 1))
done
echo "Installed $count skills."

if [ "$SET_ENV" -eq 1 ]; then
  rc="$HOME/.bashrc"; [ -n "${ZSH_VERSION:-}" ] && rc="$HOME/.zshrc"
  [ "${SHELL:-}" = "/bin/zsh" ] || [ "${SHELL:-}" = "/usr/bin/zsh" ] && rc="$HOME/.zshrc"
  line="export GUAP_ORCH_ROOT=\"$ORCH_ROOT\""
  if ! grep -qsF "GUAP_ORCH_ROOT" "$rc" 2>/dev/null; then
    printf '\n# wealth-planning suite\n%s\n' "$line" >> "$rc"
    echo "Appended GUAP_ORCH_ROOT to $rc (open a new shell to apply)."
  else
    echo "GUAP_ORCH_ROOT already present in $rc; not modified."
  fi
  export GUAP_ORCH_ROOT="$ORCH_ROOT"
else
  echo
  echo "To wire the orchestrator to guap.py, add to your shell rc:"
  echo "  export GUAP_ORCH_ROOT=\"$ORCH_ROOT\""
  echo "  (or re-run with --set-env; skip if this repo is at ~/projects/LOCALSonly)"
fi

if [ "$VERIFY" -eq 1 ] && [ -n "$PY" ]; then
  echo
  echo "Verifying..."
  export GUAP_ORCH_ROOT="$ORCH_ROOT"
  "$PY" "$SKILLS_DEST/compliance-review/scripts/tests/test_compliance.py"
  "$PY" "$SKILLS_DEST/guap-guide/scripts/guap.py" --help >/dev/null
  echo "guap.py loaded and found the orchestrator OK."
fi

echo
echo "Done."

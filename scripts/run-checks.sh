#!/bin/bash
# Test gate for the cortexes plugin: ruff lint + both pytest suites.
#
# Runnable standalone (./scripts/run-checks.sh) and wired into
# .pre-commit-config.yaml. Uses the ambient `python3` (your pyenv interpreter)
# so it shares already-installed deps. All checks run even if an earlier one
# fails, so you see every problem in one pass; exits non-zero on any failure.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2
status=0

echo "── ruff ──────────────────────────────────────────"
if command -v ruff >/dev/null 2>&1; then
  ruff check hooks/ tests/ cortex-vec/src cortex-vec/tests || status=1
else
  echo "ruff not installed — skipping lint (pip install ruff to enable)"
fi

echo "── pytest: hooks (tests/) ────────────────────────"
python3 -m pytest tests/ -q || status=1

echo "── pytest: cortex-vec ────────────────────────────"
( cd cortex-vec && python3 -m pytest -q ) || status=1

echo "──────────────────────────────────────────────────"
if [[ $status -eq 0 ]]; then
  echo "✓ all checks passed"
else
  echo "✗ checks failed"
fi
exit $status

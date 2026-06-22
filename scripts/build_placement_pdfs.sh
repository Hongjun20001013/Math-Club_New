#!/usr/bin/env bash
# Compile all placement blank-test PDFs from repo-root LaTeX sources.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TEX_FILES=(
  Placement_Test
  Placement_Middle_Level
  Placement_Enhanced_Math_1
  Placement_Enhanced_Math_2
)

for base in "${TEX_FILES[@]}"; do
  if [[ ! -f "${base}.tex" ]]; then
    echo "Skip missing ${base}.tex"
    continue
  fi
  echo "Building ${base}.pdf ..."
  pdflatex -interaction=nonstopmode "${base}.tex" >/dev/null
  pdflatex -interaction=nonstopmode "${base}.tex" | tail -1
done

if [[ -f Placement_Test.tex ]]; then
  cp Placement_Test.tex banks/placement/placement_test.tex
  echo "Synced banks/placement/placement_test.tex"
fi

echo "Done. Run: python3 scripts/build_question_bank.py"

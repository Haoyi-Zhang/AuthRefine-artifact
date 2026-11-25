#!/usr/bin/env python3
"""Review-facing entry point for exact manuscript-figure regeneration.

Writes the thirteen statistical figures, the generated cost-table rows
(family-cost-rows.tex) and figure-receipt.json into a new directory.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_directory.resolve()
    if output.exists():
        parser.error("choose a fresh output directory")
    output.mkdir(parents=True)
    return subprocess.run([
        sys.executable, "-B", str(HERE / "paper_figures.py"),
        "--artifact", str(HERE.parent),
        "--output-directory", str(output),
        "--table-output", str(output / "family-cost-rows.tex"),
        "--receipt", str(output / "figure-receipt.json"),
    ], cwd=HERE).returncode


if __name__ == "__main__":
    raise SystemExit(main())

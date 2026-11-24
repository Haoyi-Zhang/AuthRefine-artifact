#!/usr/bin/env python3
"""Run the reproducible native H19 comparison into a new output directory."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ARTIFACT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ARTIFACT))
from source_study.historical_h19.contract import fixtures
from source_study.historical_h19.source import check_native, check_source, registry_model, HERE


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(output: Path, orm_version="1.16.0"):
    source = check_source()
    runtime = check_native(orm_version)
    registry = registry_model(orm_version)
    output.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    inputs = fixtures()
    write(output / "fixtures.json", inputs)
    write(output / "source-manifest.json", source)
    from source_study.historical_h19.native import execute
    observations = asyncio.run(execute(inputs))
    observations.update(orm_version=orm_version, registry_source=registry)
    write(output / "native-observations.json", observations)
    native_hash = hashlib.sha256((output / "native-observations.json").read_bytes()).hexdigest()
    # The native records and fixtures exist before the existing IR is imported.
    from source_study.historical_h19.compare import compare
    comparisons = compare(inputs, observations)
    write(output / "comparison.json", comparisons)
    if hashlib.sha256((output / "native-observations.json").read_bytes()).hexdigest() != native_hash:
        raise ValueError("Native observations changed during comparison")
    from source_study.historical_h19.verify import verify_directory
    summary = verify_directory(output)
    write(output / "summary.json", summary)
    runtime.update(wall_seconds=time.perf_counter() - start, platform=platform.platform(),
                   source_files=[{"path": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                                 for p in sorted(HERE.iterdir()) if p.is_file()],
                   native_frozen_before_interpreter_import=True,
                   source_module_execution="Complete pinned original modules, native ORM/SQLite/Pydantic; no server started.")
    write(output / "runtime.json", runtime)
    write(output / "file-hashes.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(output.iterdir()) if p.is_file()})
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--orm-version", choices=("1.16.0", "1.34.0"), default="1.16.0")
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.orm_version), indent=2))

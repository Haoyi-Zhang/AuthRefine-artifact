#!/usr/bin/env python3
"""Regenerate all manuscript figures into one fresh directory with receipts.

Requires ReportLab, PyMuPDF and the documented manuscript fonts. This command
reads retained observations and timings. It does not rerun source applications
or benchmark measurements and does not modify the manuscript directory.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import fitz
import reportlab
from figure_typography import tex_file

ART = Path(__file__).resolve().parents[1]
EXPECTED = {
    'authrefine-overview.pdf', 'session-lifecycle.pdf', 'credential-handoff.pdf',
    'semantic-square.pdf', 'diagnostic-trace.pdf', 'analysis-workflow.pdf',
    'family-diagnosis-cost.pdf', 'source-interface-coverage.pdf',
    'evaluation-design.pdf', 'source-screening.pdf', 'adaptation-handling.pdf',
    'frontend-batch-cost.pdf', 'credential-algorithm-cost.pdf', 'width.pdf',
    'session-correspondence.pdf',
    'symbolic-comparison.pdf',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_path(path: Path, output: Path | None = None) -> str:
    path = path.resolve()
    if output is not None:
        try:
            return "<output>/" + path.relative_to(output.resolve()).as_posix()
        except ValueError:
            pass
    try:
        return path.relative_to(ART).as_posix()
    except ValueError:
        pass
    try:
        return "../" + path.relative_to(ART.parent).as_posix()
    except ValueError:
        return "<external>/" + path.name


def fingerprint(paths):
    return {public_path(path): sha(path) for path in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--math-font', type=Path,
                        help="Legacy option; labels use the manuscript's Libertine math face")
    parser.add_argument('--session-results', type=Path,
                        default=ART/'results/native-session')
    parser.add_argument('--cost-results', type=Path,
                        default=ART/'results/symbolic-comparison')
    parser.add_argument('--correspondence-results', type=Path,
                        default=ART/'results/session-correspondence')
    parser.add_argument('--strict-historical-audit', action='store_true',
                        help='also require current implementation hashes to match the retained timing acquisition')
    args = parser.parse_args()
    output = args.output_directory.resolve()
    if output.exists():
        parser.error('the output directory must not already exist')
    session = args.session_results.resolve(strict=True)
    cost = args.cost_results.resolve(strict=True)
    correspondence = args.correspondence_results.resolve(strict=True)
    source_paths = set((ART/'figures').glob('*.py')) | set((ART/'src').rglob('*.py'))
    data_paths = {
        ART/'results/width.csv',
        ART/'adaptation_study/casebook.json', ART/'adaptation_study/survey.json.gz',
        ART/'prospective_study/primary.json.gz', ART/'prospective_study/secondary.json.gz',
        *(ART/'source_study/data'/name for name in (
            'credential-input.json.gz', 'credential-observations.json.gz',
            'credential-family.json.gz', 'source-transfer.json.gz',
            'credential-cost.json.gz', 'frontend-cost.json.gz')),
        *(session/name for name in ('native-observations.json', 'diagnosis.json',
                                   'native-witness-replay.json')),
        cost/'summary.json', cost/'trials.json',
        *(cost/'trials').glob('*.stdout.json'),
        *(cost/'trials').glob('*.stderr.txt'),
        correspondence/'diagnosis.json',
    }
    font_paths = {Path(tex_file(name)) for name in (
        'LiberationSerif-Regular.ttf', 'LiberationSerif-Bold.ttf',
        'LiberationSerif-Italic.ttf')}
    inputs = fingerprint(source_paths | data_paths | font_paths)
    paper_before = fingerprint(set((ART.parent/'paper').rglob('*')) -
                               {p for p in (ART.parent/'paper').rglob('*') if not p.is_file()})
    output.mkdir(parents=True)
    commands = []
    if args.strict_historical_audit:
        commands.append(['benchmarks/audit_symbolic_comparison.py', '--results', str(cost)])
    commands.extend([
        ['figures/draw_schematics.py', '--output-directory', str(output)],
        ['figures/draw_evaluation.py', '--output-directory', str(output)],
        ['figures/session_lifecycle.py', '--results', str(session),
         '--output', str(output/'session-lifecycle.pdf'), '--svg', str(output/'session-lifecycle.svg')],
        ['figures/family_cost.py', '--results', str(cost), '--output', str(output)],
        ['figures/session_correspondence.py', '--results', str(correspondence),
         '--comparison-results', str(cost), '--output', str(output)],
        ['figures/symbolic_comparison.py', '--results', str(cost), '--output', str(output)],
    ])
    record = {'completed': False, 'scientific_measurements_rerun': False,
              'purpose': 'regeneration from retained scientific inputs',
              'strict_historical_acquisition_audit': args.strict_historical_audit,
              'historical_audit_note': ('required' if args.strict_historical_audit else
                  'not required for plotting; figure loaders verify raw records, denominators, outputs and scientific fields'),
              'typography': {'text': 'Liberation Serif (Times-compatible)', 'mathematics': 'Liberation Serif Italic',
                             'palette': 'grayscale-safe blue/green/orange'},
              'python': sys.version, 'reportlab': reportlab.Version,
              'pymupdf': fitz.VersionBind, 'input_sha256': inputs, 'commands': []}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    try:
        for i, arguments in enumerate(commands, 1):
            command = [sys.executable, '-B', *arguments]
            started = time.monotonic()
            result = subprocess.run(command, cwd=ART, env=env, text=True,
                                    capture_output=True, timeout=120)
            (output/f'command-{i}.stdout.txt').write_text(result.stdout)
            (output/f'command-{i}.stderr.txt').write_text(result.stderr)
            record['commands'].append({
                'command': [public_path(Path(value), output) if value.startswith('/') else value
                            for value in command],
                'exit_code': result.returncode,
                'seconds': time.monotonic()-started,
            })
            if result.returncode:
                raise RuntimeError(f'figure command {i} failed')
        actual = {p.name for p in output.glob('*.pdf')}
        if actual != EXPECTED:
            raise RuntimeError(f'figure set differs: missing={EXPECTED-actual}; extra={actual-EXPECTED}')
        pdfs = {}
        for name in sorted(EXPECTED):
            path = output/name
            with fitz.open(path) as doc:
                if len(doc) != 1:
                    raise RuntimeError(name + ' must contain one vector figure')
                page = doc[0]
                if page.get_images():
                    raise RuntimeError(name + ' unexpectedly contains a raster image')
                # Reopen, decode, and render every delivered vector page.
                pix = page.get_pixmap(matrix=fitz.Matrix(.5,.5), alpha=False)
                if not pix.samples:
                    raise RuntimeError(name + ' did not render')
                fonts = []
                for font in page.get_fonts(full=True):
                    data = doc.extract_font(font[0])
                    if not data[-1]:
                        raise RuntimeError(name + ' contains an unembedded font')
                    fonts.append({'name': font[3], 'format': font[2]})
                pdfs[name] = {'sha256': sha(path), 'width_pt': page.rect.width,
                              'height_pt': page.rect.height, 'fonts': fonts,
                              'raster_images': 0}
        if fingerprint(source_paths | data_paths | font_paths) != inputs:
            raise RuntimeError('a figure source or scientific input changed during regeneration')
        paper_after = fingerprint({p for p in (ART.parent/'paper').rglob('*') if p.is_file()})
        if paper_before != paper_after:
            raise RuntimeError('manuscript files changed during regeneration')
        record.update(completed=True, figures=pdfs, manuscript_unchanged=True,
                      output_sha256={p.name:sha(p) for p in sorted(output.iterdir())
                                     if p.is_file()})
    except Exception as exc:
        record['error'] = str(exc)
        raise
    finally:
        (output/'generation-receipt.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'completed': True, 'figures': len(pdfs),
                      'receipt': str(output/'generation-receipt.json')}))


if __name__ == '__main__':
    main()

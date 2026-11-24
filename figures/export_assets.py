#!/usr/bin/env python3
"""Export the checked vector figures as outlined SVG and 600 dpi PNG assets.

The manuscript uses the PDF originals. These exports support inspection and
reuse; they never replace the originals or infer new scientific content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fitz
from regenerate import EXPECTED


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-directory', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    args = parser.parse_args()
    source = args.input_directory.resolve(strict=True)
    destination = args.output_directory.resolve()
    if destination.exists():
        parser.error('the output directory must be new')
    if {p.name for p in source.glob('*.pdf')} != EXPECTED:
        parser.error('the input directory must contain the sixteen figure PDFs')
    destination.mkdir(parents=True)
    rows = []
    for name in sorted(EXPECTED):
        path = source / name
        before = path.read_bytes()
        with fitz.open(path) as document:
            if len(document) != 1 or document[0].get_images():
                raise ValueError(name + ': expected one vector-only page')
            page = document[0]
            png = page.get_pixmap(dpi=600, alpha=False)
            png_path = destination / (path.stem + '.png')
            png.save(png_path)
            svg_path = destination / (path.stem + '.svg')
            svg_path.write_text(page.get_svg_image(text_as_path=True), encoding='utf-8')
            if not png_path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError(name + ': invalid PNG export')
            if path.read_bytes() != before:
                raise ValueError(name + ': original changed during export')
            rows.append({
                'source': name,
                'source_sha256': hashlib.sha256(before).hexdigest(),
                'width_points': page.rect.width,
                'height_points': page.rect.height,
                'png': png_path.name,
                'png_width': png.width,
                'png_height': png.height,
                'png_dpi': 600,
                'svg': svg_path.name,
                'svg_text_as_paths': True,
                'source_unchanged': True,
            })
    receipt = {'completed': True, 'figures': rows,
               'scope': 'Format exports of the vector originals; no new data or diagrams.'}
    (destination / 'export-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    (destination / 'README.txt').write_text(
        'AuthRefine figure assets\n\n'
        'The manuscript includes the vector PDFs in the parent directory.\n'
        'PNG files are rendered directly from those originals at 600 dpi.\n'
        'SVG files preserve their outlines, including the manuscript glyphs,\n'
        'without requiring an installed font on another computer.\n'
        'Edit the Python figure sources and regenerate the PDF before exporting.\n'
        'These files contain the same scientific content as the originals.\n')
    print(json.dumps({'completed': True, 'figures': len(rows), 'png_dpi': 600}))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Assemble main-paper and supplement figures at their journal display width.

Requires PyMuPDF. Each atlas page embeds the original vector PDF and a 300 dpi
grayscale rendering. Figure numbering belongs to its source document; atlas
page numbering is a separate, global sequence. No fixed figure count is assumed.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import fitz
from figure_typography import tex_file

DOCUMENTS = (("main", "Main paper"), ("supplement", "Supplement"))
# The supplied acmsmall class uses a 6.75-inch page and two 46-TeX-point
# horizontal margins. PDF coordinates use 72 points per inch; TeX uses 72.27.
COLUMN_WIDTH = 6.75 * 72 - 2 * 46 * 72 / 72.27


def strip_comments(text):
    lines = []
    for line in text.splitlines():
        end = len(line)
        for index, character in enumerate(line):
            if character != "%":
                continue
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                end = index
                break
        lines.append(line[:end])
    return "\n".join(lines)


def expanded(path, root, stack):
    path = path.resolve()
    if path in stack:
        raise ValueError("Cyclic manuscript input: " + str(path))
    stack = {*stack, path}
    text = strip_comments(path.read_text(encoding="utf-8"))

    def sub(match):
        name = match[1]
        suffix = Path(name).suffix
        # TeX font resources such as Ustmry.fd are not manuscript inputs.
        if suffix and suffix != ".tex":
            return match[0]
        child = root / (name if suffix else name + ".tex")
        if not child.is_file():
            raise ValueError("Missing manuscript input: " + str(child))
        return expanded(child, root, stack)

    return re.sub(r"\\(?:input|include)\s*\{([^}]+)\}", sub, text)


def source_figures(root, document):
    text = expanded(root / (document + ".tex"), root, set())
    blocks = re.findall(r"\\begin\{(figure\*?)\}(.*?)\\end\{\1\}", text, re.S)
    figures, labels = [], set()
    for ordinal, (_, block) in enumerate(blocks, 1):
        found = re.findall(r"\\label\{([^}]+)\}", block)
        if len(found) != 1 or found[0] in labels:
            raise ValueError(f"Each {document} figure needs one unique local label: {found}")
        label = found[0]
        labels.add(label)
        graphics = re.findall(r"\\includegraphics\s*\[([^]]*)\]\s*\{([^}]+)\}", block)
        if len(graphics) != 1:
            raise ValueError("A figure must contain one graphic with a display width: " + document + ":" + label)
        options, relative = graphics[0]
        scale = re.search(r"(?:^|,)\s*width\s*=\s*([0-9.]*)\\linewidth(?:\s*,|\s*$)", options)
        if scale is None:
            raise ValueError("Unsupported figure width: " + document + ":" + label + " / " + options)
        fraction = float(scale[1] or "1")
        if not 0 < fraction <= 1:
            raise ValueError("Figure exceeds the declared journal column: " + label)
        source = root / relative
        if not source.suffix:
            source = source.with_suffix(".pdf")
        if not source.is_file() or source.suffix.lower() != ".pdf":
            raise ValueError("Figure source is not an existing vector PDF: " + str(source))
        figures.append({"document": document, "ordinal": ordinal, "label": label,
                        "source": str(source.relative_to(root)), "display_width_points": COLUMN_WIDTH * fraction})
    return figures


def aux_text(path, root, stack):
    path = path.resolve()
    if path in stack:
        raise ValueError("Cyclic auxiliary input: " + str(path))
    stack = {*stack, path}
    text = path.read_text(encoding="utf-8")

    def sub(match):
        child = root / match[1]
        if not child.is_file():
            raise ValueError("Missing compiled auxiliary input: " + str(child))
        return aux_text(child, root, stack)

    return re.sub(r"\\@input\{([^}]+)\}", sub, text)


def compiled_figures(root):
    figures = []
    for name, title in DOCUMENTS:
        entries = source_figures(root, name)
        aux_path, pdf_path = root / (name + ".aux"), root / (name + ".pdf")
        if not aux_path.is_file() or not pdf_path.is_file():
            raise ValueError("Build both main and supplement before the atlas: " + name)
        aux = aux_text(aux_path, root, set())
        with fitz.open(pdf_path) as source_document:
            pages = len(source_document)
        pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        aux_hash = hashlib.sha256(aux_path.read_bytes()).hexdigest()
        numbers = set()
        for entry in entries:
            label = entry["label"]
            matches = re.findall(r"\\newlabel\{" + re.escape(label) + r"\}\{\{([^{}]+)\}\{([^{}]+)\}", aux)
            if len(matches) != 1:
                raise ValueError("Missing or duplicate compiled figure label: " + name + ":" + label)
            number, page = matches[0]
            numeric = re.fullmatch(r"[A-Za-z]*([0-9]+)", number)
            if numeric is None or int(numeric[1]) != entry["ordinal"] or number in numbers:
                raise ValueError("Figure order differs from compiled document: " + name + ":" + label)
            if not page.isdigit() or not 1 <= int(page) <= pages:
                raise ValueError("Figure page is outside its compiled document: " + name + ":" + label)
            numbers.add(number)
            figures.append({**entry, "id": name + ":" + label,
                            "document_title": title, "number": int(number) if number.isdigit() else number,
                            "document_page": int(page), "paper_page": int(page),
                            "document_pdf": pdf_path.name, "document_pdf_sha256": pdf_hash,
                            "document_aux_sha256": aux_hash})
    if not figures:
        raise ValueError("No figures were found in the main paper or supplement")
    if len({entry["id"] for entry in figures}) != len(figures):
        raise ValueError("Duplicate document/figure identity")
    return figures


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_build(root, summary_path, figures):
    """Require the same frozen inputs that the successful TeX run consumed."""
    summary_path = summary_path.resolve(strict=True)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("completed") is not True or summary.get("inputs_unchanged_during_build") is not True:
        raise ValueError("The atlas requires a completed build with unchanged inputs")
    if summary.get("build_script_sha256") != sha256(root / "build.py"):
        raise ValueError("The build driver differs from the successful build record")
    current_sources = {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix in {".tex", ".bib", ".cls", ".bst", ".fd"}
    }
    if summary.get("source_sha256") != current_sources:
        raise ValueError("Manuscript sources differ from the successful build record")
    current_assets = {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted((root / "figures").rglob("*"))
        if path.is_file() and path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".svg"}
    }
    if summary.get("figure_asset_sha256") != current_assets:
        raise ValueError("Figure assets differ from the successful build record")
    recorded_pdfs = summary.get("pdf_sha256", {})
    if not isinstance(recorded_pdfs, dict) or not recorded_pdfs:
        raise ValueError("The build record has no compiled PDF identities")
    for name, digest in recorded_pdfs.items():
        if Path(name).name != name or Path(name).suffix != ".pdf":
            raise ValueError("Invalid compiled PDF name in build record")
        path = root / name
        if not path.is_file() or sha256(path) != digest:
            raise ValueError("Compiled PDF differs from the successful build record: " + name)
    consumed = summary.get("target_figure_inputs", {})
    for document, _ in DOCUMENTS:
        if document not in summary.get("targets", ()) or document + ".pdf" not in recorded_pdfs:
            raise ValueError("The successful build must include main and supplement")
        expected = {entry["source"]: current_assets[entry["source"]]
                    for entry in figures if entry["document"] == document}
        if consumed.get(document) != expected:
            raise ValueError("Recorded TeX figure inputs differ from the atlas figure set: " + document)
        # The auxiliary page index is checked against visible captions in the
        # exact compiled PDF, so a stale auxiliary index cannot relocate a figure.
        with fitz.open(root / (document + ".pdf")) as pdf:
            for entry in (e for e in figures if e["document"] == document):
                text = pdf[entry["document_page"] - 1].get_text()
                caption = r"\bFig\.\s*" + re.escape(str(entry["number"])) + r"\."
                if re.search(caption, text) is None:
                    raise ValueError("Compiled figure caption is missing from the auxiliary page: " + entry["id"])
    return {"build_summary_sha256": sha256(summary_path),
            "build_script_sha256": summary["build_script_sha256"],
            "inputs_unchanged_during_build": True,
            "recorded_figure_inputs_verified": True}


def build(root, output, build_summary=None):
    figures = compiled_figures(root)
    summary_path = build_summary or root / "build-logs/build-summary.json"
    verified = verify_build(root, summary_path, figures)
    atlas = fitz.open()
    manifest = []
    regular_font = Path(tex_file("LiberationSerif-Regular.ttf")).read_bytes()
    bold_font = Path(tex_file("LiberationSerif-Bold.ttf")).read_bytes()
    for atlas_page, entry in enumerate(figures, 1):
        source = root / entry["source"]
        with fitz.open(source) as figure:
            if len(figure) != 1:
                raise ValueError("A figure input must have exactly one page: " + str(source))
            width = entry["display_width_points"]
            height = figure[0].rect.height * width / figure[0].rect.width
            page_height = max(842.0, 180 + height * 2)
            page = atlas.new_page(width=595, height=page_height)
            page.insert_font(fontname="AtlasRegular", fontbuffer=regular_font)
            page.insert_font(fontname="AtlasBold", fontbuffer=bold_font)
            page.insert_text((48, 32), f"AuthRefine / {entry['document_title']} / Figure {entry['number']}",
                             fontname="AtlasBold", fontsize=13)
            page.insert_text((48, 49), f"{entry['document_title']}, page {entry['document_page']}",
                             fontname="AtlasRegular", fontsize=10)
            x = (595 - width) / 2
            page.insert_text((x, 72), "Vector original at manuscript display width",
                             fontname="AtlasRegular", fontsize=10)
            rect = fitz.Rect(x, 82, x + width, 82 + height)
            page.show_pdf_page(rect, figure, 0)
            y = rect.y1 + 33
            page.insert_text((x, y), "Grayscale, rendered at 300 dpi",
                             fontname="AtlasRegular", fontsize=10)
            gray = figure[0].get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), colorspace=fitz.csGRAY, alpha=False)
            page.insert_image(fitz.Rect(x, y + 10, x + width, y + 10 + height), pixmap=gray)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        page.insert_text((48, page_height - 44), f"AuthRefine figure atlas | {atlas_page}",
                         fontname="AtlasRegular", fontsize=10)
        manifest.append({**entry, **verified, "source_sha256": digest, "atlas_page": atlas_page,
                         "display_height_points": height})
    if verify_build(root, summary_path, figures) != verified:
        raise ValueError("Build evidence changed during atlas assembly")
    output.parent.mkdir(parents=True, exist_ok=True)
    atlas.set_metadata({"title": "AuthRefine main and supplement figure atlas: vector originals and grayscale",
                        "author": "AuthRefine authors"})
    atlas.save(output, deflate=True, garbage=4)
    output.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    result = {"figures": len(manifest), "pages": len(atlas), "documents": dict(Counter(r["document"] for r in manifest)),
              "output": str(output), **verified}
    atlas.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-directory", type=Path, default=Path(__file__).resolve().parents[2] / "paper")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-summary", type=Path,
                        help="successful build record (default: PAPER/build-logs/build-summary.json)")
    args = parser.parse_args()
    print(json.dumps(build(args.paper_directory.resolve(), args.output, args.build_summary)))


if __name__ == "__main__":
    main()

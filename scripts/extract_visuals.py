#!/usr/bin/env python3
"""Extract per-slide PNGs from a deck (.pptx) or PDF into a course module.

Renders every slide of the source deck to
``courses/<course>/build/<module>/visuals/<deck-slug>/slide-NNN.png``
so the deck's visuals can be curated, captioned in ``INDEX.md``, and
referenced from ``lesson.md``. Safe to run repeatedly: curation is
destructive (you delete the slides you don't want), so re-extraction
must stay cheap.

Pipeline:

1. ``.pptx`` -> PDF via LibreOffice (``soffice --headless``), the only
   external CLI this repo relies on. A ``.pdf`` input skips this step.
2. PDF -> per-page PNGs via ``pypdfium2`` (permissive license, pip-installable).

Requirements (both optional-tier, not needed for the SCORM pipeline itself):

- LibreOffice: ``brew install --cask libreoffice`` (macOS) or
  ``apt-get install libreoffice`` (Debian/Ubuntu). Only needed for ``.pptx``.
- pypdfium2: ``pip install pypdfium2``

Known LibreOffice gotcha: when a deck is open in PowerPoint/Keynote, a
hidden ``~$<name>.pptx`` lock file sits next to it and soffice silently
skips the conversion (exit 0, no output). This script always stages the
deck into a temp directory first, which sidesteps the lock, and warns
when a lock file is present so you know the on-disk copy may be stale.

Usage:
    python3 scripts/extract_visuals.py <deck.pptx|deck.pdf> \\
        --course <course-name> --module <module-id> [--deck-name <slug>] [--dpi 150]

After extraction: curate (delete irrelevant slides), then catalog the
keepers in the module's ``visuals/INDEX.md`` (see the power's
``source-intake.md`` steering file). Captions can be hand-written or
generated with the optional ``scripts/caption_visuals.py``.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_DPI = 150


def fail(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


_SOFFICE_CMD = "/usr/bin/soffice"
"""Default soffice path. Override via SOFFICE_PATH env var for non-standard installs."""


def preflight_soffice() -> str:
    """Return the soffice executable path or exit with an install hint."""
    exe = os.environ.get("SOFFICE_PATH") or shutil.which("soffice") or _SOFFICE_CMD
    if not os.path.isfile(exe):
        fail(
            "soffice (LibreOffice) not found on PATH. Install with:\n"
            "  macOS:         brew install --cask libreoffice\n"
            "  Debian/Ubuntu: sudo apt-get install libreoffice\n"
            "  Or set SOFFICE_PATH=/path/to/soffice"
        )
    return exe


def preflight_pypdfium2():
    """Import pypdfium2 or exit with an install hint."""
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        fail(
            "pypdfium2 not installed (needed to rasterize PDF pages to PNGs).\n"
            "Install with: pip install pypdfium2"
        )
    import pypdfium2

    return pypdfium2


def warn_on_lock_file(deck: Path) -> None:
    """Warn when an Office lock file sits next to the deck.

    soffice silently skips locked .pptx files; staging to a temp dir (which
    this script always does) works around the skip, but the file on disk may
    hold unsaved changes still living only in the editor.
    """
    lock = deck.parent / f"~${deck.name}"
    if lock.exists():
        print(
            f"WARNING: Office lock file detected ({lock}). The deck appears to be "
            "open in PowerPoint/Keynote - unsaved edits will not be in the "
            "extraction. Proceeding via copy-to-temp workaround.",
            file=sys.stderr,
        )


def slugify(name: str) -> str:
    """Filesystem-friendly kebab-case slug from a deck filename stem."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "deck"


def convert_pptx_to_pdf(soffice: str, deck: Path, workdir: Path) -> Path:
    """Convert the deck to PDF inside ``workdir``; return the PDF path."""
    staged = workdir / deck.name
    shutil.copy2(deck, staged)

    # argv is anchored on the static program name "soffice"; the actual
    # binary path (resolved and existence-checked by preflight_soffice)
    # is supplied via the ``executable`` kwarg. List form, no shell.
    result = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(workdir), str(staged)],
        executable=soffice,
        capture_output=True,
        text=True,
    )
    pdf = workdir / (deck.stem + ".pdf")
    if result.returncode != 0 or not pdf.exists():
        fail(
            f"LibreOffice failed to convert {deck} to PDF "
            f"(exit {result.returncode}).\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
        )
    return pdf


def rasterize_pdf_to_pngs(pdf: Path, outdir: Path, dpi: int) -> int:
    """Render every PDF page to ``outdir/slide-NNN.png``; return page count."""
    pypdfium2 = preflight_pypdfium2()
    outdir.mkdir(parents=True, exist_ok=True)
    doc = pypdfium2.PdfDocument(str(pdf))
    try:
        n_pages = len(doc)
        for i in range(n_pages):
            page = doc[i]
            bitmap = page.render(scale=dpi / 72)
            image = bitmap.to_pil()
            image.save(outdir / f"slide-{i + 1:03d}.png")
    finally:
        doc.close()
    return n_pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("deck", type=Path, help="Source .pptx or .pdf")
    parser.add_argument("--course", required=True, help="Course name under courses/")
    parser.add_argument("--module", required=True, help="Target module id, e.g. module-2")
    parser.add_argument(
        "--deck-name",
        default=None,
        help="Subfolder name under visuals/ (default: slug of the deck filename)",
    )
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help=f"Render DPI (default {DEFAULT_DPI})")
    args = parser.parse_args()

    deck: Path = args.deck
    if not deck.exists():
        fail(f"Deck not found: {deck}")
    suffix = deck.suffix.lower()
    if suffix not in (".pptx", ".pdf"):
        fail(f"Unsupported deck format {suffix!r}: expected .pptx or .pdf (export Keynote to .pptx first)")

    repo_root = Path(__file__).resolve().parents[1]
    module_dir = repo_root / "courses" / args.course / "build" / args.module
    if not module_dir.exists():
        fail(
            f"Module directory not found: {module_dir}\n"
            "Create the course scaffold first (see course-planning.md)."
        )

    deck_slug = args.deck_name or slugify(deck.stem)
    outdir = module_dir / "visuals" / deck_slug

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        if suffix == ".pptx":
            soffice = preflight_soffice()
            preflight_pypdfium2()  # fail fast before the slow soffice step
            warn_on_lock_file(deck)
            pdf = convert_pptx_to_pdf(soffice, deck, workdir)
        else:
            pdf = deck
        n_pages = rasterize_pdf_to_pngs(pdf, outdir, args.dpi)

    print(f"Extracted {n_pages} slides to {outdir.relative_to(repo_root)}")
    print("Next steps:")
    print("  1. Curate: delete slides you will not reference in the lesson")
    print(f"  2. Catalog the keepers in {outdir.parent.relative_to(repo_root)}/INDEX.md")
    print("     (captions by hand, or via the optional scripts/caption_visuals.py)")


if __name__ == "__main__":
    main()

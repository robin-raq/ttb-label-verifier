"""Real-label intake pipeline for the eval set.

Adds a real bottle-label image (or COLA PDF) to
`tests/fixtures/labels/real/` and scaffolds its `expected.yaml` so an analyst
can fill in the form-field ground truth.

Why this is a manual-input tool, not a scraper
----------------------------------------------
TTB's public COLA registry (ttbonline.gov/colasonline/) serves PDFs behind a
session-bound search UI; programmatic scraping breaks on cert validation,
session cookies, and rate limits. Most other on-web bottle-label sources are
copyrighted product packaging, which we can't redistribute as test fixtures.

The defensible workflow is:
  1. The analyst downloads an approved COLA PDF from a browser session at
     ttbonline.gov, OR photographs a real bottle, OR receives a label from a
     vendor with explicit fixture permission.
  2. They run this script with the local file path.
  3. The script normalises to PNG and scaffolds an `expected.yaml` template
     with TODO markers.
  4. The analyst fills in the form fields and expected verdicts.
  5. `make eval` (with RUN_LLM_TESTS=1) picks the new fixture up
     automatically — it lives next to the synthetic ones.

Usage
-----
    python scripts/fetch_real_labels.py path/to/cola_artifact.pdf --slug bourbon-acme
    python scripts/fetch_real_labels.py /Users/me/Pictures/bottle.jpg --slug merlot-2024
    python scripts/fetch_real_labels.py path/to/label.pdf --slug rye --page 1

PDFs require `pypdfium2` (optional dev dep — `pip install pypdfium2`). PNG/
JPEG/WebP inputs are converted to PNG with Pillow only.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml
from PIL import Image

REAL_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "labels" / "real"

# Slug must be filesystem-safe and pytest-id-friendly: lowercase, dashes/underscores,
# alphanumerics. No spaces, no dots, no special chars.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


def _validate_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug):
        sys.exit(
            f"Slug {slug!r} is invalid. Must be 2–63 chars, lowercase, "
            f"alphanumeric / dashes / underscores, starting with a letter or digit."
        )


def _pdf_to_png(pdf_path: Path, out_path: Path, page: int) -> None:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        sys.exit(
            "PDF input requires pypdfium2. Install with `pip install pypdfium2` "
            "(pure Python, no system deps)."
        )

    doc = pdfium.PdfDocument(pdf_path)
    if page < 1 or page > len(doc):
        sys.exit(f"--page {page} out of range; PDF has {len(doc)} pages.")

    pdf_page = doc[page - 1]
    pil_image = pdf_page.render(scale=2.0).to_pil()  # ~144 dpi
    pil_image.save(out_path, "PNG", optimize=True)
    pdf_page.close()
    doc.close()


def _image_to_png(src: Path, out_path: Path) -> None:
    with Image.open(src) as im:
        im.convert("RGB").save(out_path, "PNG", optimize=True)


def _scaffold_yaml(out_path: Path, slug: str, source: Path) -> None:
    template: dict = {
        "form_fields": {
            "brand": "TODO: enter brand exactly as it appears in COLA form",
            "class_type": "TODO: enter class/type",
            "abv_percent": 0.0,  # TODO: numeric, e.g. 45.0
            "net_contents": "TODO: e.g. '750 mL'",
        },
        "expected_overall": "PASS",  # TODO: PASS / FAIL / NEEDS_REVIEW
        "expected_per_field": None,  # TODO: tighten once verified, or leave None
        "notes": (
            f"Real-label fixture for slug={slug!r}. Sourced from {source.name}. "
            "Replace this entire YAML with verified ground truth before merging."
        ),
    }
    with out_path.open("w") as f:
        f.write(
            "# REAL-LABEL FIXTURE — fill in before this fixture is merged.\n"
            "# Every TODO must be replaced; expected_overall must reflect the\n"
            "# verdict an experienced TTB compliance agent would give.\n\n"
        )
        yaml.safe_dump(template, f, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="Local path to PNG/JPG/WEBP/PDF")
    parser.add_argument("--slug", required=True, help="Fixture slug (e.g. 'bourbon-acme')")
    parser.add_argument("--page", type=int, default=1, help="PDF page number (default 1)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing fixture")
    args = parser.parse_args()

    src: Path = args.source
    if not src.is_file():
        sys.exit(f"Source file not found: {src}")

    _validate_slug(args.slug)
    REAL_DIR.mkdir(parents=True, exist_ok=True)

    out_png = REAL_DIR / f"{args.slug}.png"
    out_yaml = REAL_DIR / f"{args.slug}.expected.yaml"
    if (out_png.exists() or out_yaml.exists()) and not args.force:
        sys.exit(
            f"Fixture {args.slug!r} already exists. Use --force to overwrite, "
            f"or pick a different --slug."
        )

    suffix = src.suffix.lower()
    if suffix == ".pdf":
        _pdf_to_png(src, out_png, args.page)
    elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        if suffix == ".png" and src.resolve() != out_png.resolve():
            shutil.copy2(src, out_png)
        else:
            _image_to_png(src, out_png)
    else:
        sys.exit(f"Unsupported source type {suffix!r}. Use PNG/JPG/WEBP/PDF.")

    _scaffold_yaml(out_yaml, args.slug, src)

    print(f"  wrote {out_png.relative_to(REAL_DIR.parent.parent.parent)}")
    print(f"  wrote {out_yaml.relative_to(REAL_DIR.parent.parent.parent)} (FILL IN TODOs)")


if __name__ == "__main__":
    main()

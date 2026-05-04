"""Build the demo batch ZIP served by the mock COLA queue.

Output: frontend/public/sample-batches/peak-season.zip

The ZIP contains a `manifest.csv` plus 5 label PNGs. It models a small slice
of a peak-season backlog: 5 *different* applications (different brands,
classes, volumes) with a mix of outcomes — exactly the shape a TTB
compliance agent would face. Picked specifically to exercise:

  • Brand fuzzy-match failure (04)            → FAIL
  • Wine, different beverage shape (06)       → PASS
  • Beer with fl-oz net contents (07)         → PASS
  • Class/type substring mismatch (08)        → FAIL
  • Missing federal warning (adv_03)          → FAIL (most consequential)

Re-run after changing fixtures:
    python scripts/build_sample_batch_zip.py
"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "labels"
OUT_PATH = ROOT / "frontend" / "public" / "sample-batches" / "peak-season.zip"

# Each row: (fixture-stem, manifest-row dict). image_filename is filled in below.
ROWS = [
    (
        "04_fail_brand_mismatch",
        {
            "brand": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "abv_percent": "45.0",
            "net_contents": "750 mL",
            "cola_id": "TTB-2026-002001",
        },
    ),
    (
        "06_pass_wine_label",
        {
            "brand": "VINEYARD HEIGHTS",
            "class_type": "Sonoma County Chardonnay",
            "abv_percent": "13.5",
            "net_contents": "750 mL",
            "cola_id": "TTB-2026-002002",
        },
    ),
    (
        "07_pass_beer_label",
        {
            "brand": "WESTBROOK BREWING",
            "class_type": "American IPA",
            "abv_percent": "6.5",
            "net_contents": "12 fl oz",
            "cola_id": "TTB-2026-002003",
        },
    ),
    (
        "08_fail_class_type_mismatch",
        {
            "brand": "OLD TOM DISTILLERY",
            "class_type": "Vodka",
            "abv_percent": "45.0",
            "net_contents": "750 mL",
            "cola_id": "TTB-2026-002004",
        },
    ),
    (
        "adv_03_missing_warning",
        {
            "brand": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "abv_percent": "45.0",
            "net_contents": "750 mL",
            "cola_id": "TTB-2026-002005",
        },
    ),
]


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Build manifest.csv in memory so we can write it as a single ZIP entry.
    csv_buf = io.StringIO()
    fieldnames = [
        "image_filename",
        "brand",
        "class_type",
        "abv_percent",
        "net_contents",
        "cola_id",
    ]
    writer = csv.DictWriter(csv_buf, fieldnames=fieldnames)
    writer.writeheader()

    # Use ZIP_DEFLATED so the archive stays small enough to ship via /public.
    with zipfile.ZipFile(OUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for stem, fields in ROWS:
            png_path = FIXTURES_DIR / f"{stem}.png"
            if not png_path.is_file():
                raise SystemExit(
                    f"Missing fixture {png_path}. Run tests/fixtures/labels/"
                    f"generate_fixtures.py first."
                )
            arcname = f"labels/{stem}.png"
            zf.write(png_path, arcname=arcname)
            writer.writerow({"image_filename": arcname, **fields})

        zf.writestr("manifest.csv", csv_buf.getvalue())

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"  wrote {OUT_PATH.relative_to(ROOT)} ({size_kb:.1f} KiB, {len(ROWS)} rows)")


if __name__ == "__main__":
    main()

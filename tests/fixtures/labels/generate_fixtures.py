"""Programmatic test-label generator.

Renders three synthetic-but-readable label PNGs plus their `*.expected.yaml`
ground-truth files. Used by `make eval` (see tests/eval/test_eval.py).

Why programmatic instead of DALL-E or hand-curated photos?
  - Deterministic: re-running this script produces byte-identical PNGs, so
    the eval suite is reproducible across machines.
  - Free: no LLM tokens spent on test artefacts.
  - Real text: GPT-4o vision OCR can read these reliably, exercising the
    same wire format and prompt path as a real bottle photo.
  - Three scenarios cover the verdict matrix:
      01_happy        → all comparators PASS
      02_fail_abv     → ABV comparator FAIL (label says 40, form says 45)
      03_review_glare → image_quality 'poor' triggers FR-017 NEEDS_REVIEW

Run: `python tests/fixtures/labels/generate_fixtures.py`
"""
from __future__ import annotations

from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.constants.ttb_warning import CANONICAL_WARNING

OUT = Path(__file__).parent

# ---------------------------------------------------------------------------
# Font loading — fall back gracefully if system fonts aren't where we expect.
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists() and (("Bold" in path) == bold or not bold):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Canvas helpers
# ---------------------------------------------------------------------------

W, H = 800, 1100
BG = (245, 235, 215)  # cream label background
FG = (40, 30, 20)
BORDER = (110, 80, 40)


def _new_canvas() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([(20, 20), (W - 20, H - 20)], outline=BORDER, width=4)
    return img


def _wrap(text: str, font, max_w: int) -> list[str]:
    """Naive word wrap that fits text within max_w pixels."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        candidate = (cur + " " + w).strip()
        if font.getbbox(candidate)[2] <= max_w:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _render_label(
    out_path: Path,
    *,
    brand: str,
    class_type: str,
    abv_text: str,
    net_contents: str,
    warning: str,
    warning_prefix_caps: bool = True,
    warning_prefix_bold: bool = True,
    apply_glare: bool = False,
) -> None:
    img = _new_canvas()
    draw = ImageDraw.Draw(img)

    title_font = _load_font(56, bold=True)
    subtitle_font = _load_font(34)
    field_font = _load_font(28)
    warn_prefix_font = _load_font(22, bold=warning_prefix_bold)
    warn_body_font = _load_font(18)

    y = 70
    # Brand name
    bw = title_font.getbbox(brand)[2]
    draw.text(((W - bw) // 2, y), brand, fill=FG, font=title_font)
    y += 90

    # Class/type
    cw = subtitle_font.getbbox(class_type)[2]
    draw.text(((W - cw) // 2, y), class_type, fill=FG, font=subtitle_font)
    y += 70

    # Decorative line
    draw.line([(120, y), (W - 120, y)], fill=BORDER, width=2)
    y += 40

    # ABV / net contents row
    draw.text((100, y), abv_text, fill=FG, font=field_font)
    nc_w = field_font.getbbox(net_contents)[2]
    draw.text((W - 100 - nc_w, y), net_contents, fill=FG, font=field_font)
    y += 80

    # Address line (decorative — not a verified field in v1)
    addr = "BOTTLED BY OLD TOM DISTILLERY · KENTUCKY USA"
    aw = subtitle_font.getbbox(addr)[2]
    draw.text(((W - aw) // 2, y), addr, fill=FG, font=ImageFont.truetype(_FONT_CANDIDATES[1], 18) if Path(_FONT_CANDIDATES[1]).exists() else _load_font(18))
    y += 60

    draw.line([(120, y), (W - 120, y)], fill=BORDER, width=2)
    y += 40

    # Government Warning — split prefix and body so we can render the prefix
    # in (optionally) bold + ALL CAPS independently.
    PREFIX = "GOVERNMENT WARNING:"
    body_text = warning.removeprefix(PREFIX).lstrip()
    rendered_prefix = PREFIX if warning_prefix_caps else "Government Warning:"

    # Prefix on its own line, indented from left edge
    draw.text((80, y), rendered_prefix, fill=FG, font=warn_prefix_font)
    y += 32

    # Body wrapped to label width
    for line in _wrap(body_text, warn_body_font, W - 160):
        draw.text((80, y), line, fill=FG, font=warn_body_font)
        y += 22

    if apply_glare:
        # Two-step glare effect: blur the bottom half, then paste a bright
        # translucent ellipse over the warning area.
        bottom = img.crop((0, H // 2, W, H))
        blurred = bottom.filter(ImageFilter.GaussianBlur(radius=3))
        img.paste(blurred, (0, H // 2))
        glare = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glare)
        gd.ellipse(
            [(W // 2 - 200, H - 400), (W // 2 + 200, H - 100)],
            fill=(255, 255, 255, 110),
        )
        img = Image.alpha_composite(img.convert("RGBA"), glare).convert("RGB")

    img.save(out_path, "PNG", optimize=True)


# ---------------------------------------------------------------------------
# Fixture definitions — each is (filename, render kwargs, expected.yaml dict)
# ---------------------------------------------------------------------------

FIXTURES = [
    {
        "filename": "01_happy_old_tom.png",
        "render": {
            "brand": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "abv_text": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "warning": CANONICAL_WARNING,
            "warning_prefix_caps": True,
            "warning_prefix_bold": True,
            "apply_glare": False,
        },
        "expected": {
            "form_fields": {
                "brand": "OLD TOM DISTILLERY",
                "class_type": "Kentucky Straight Bourbon Whiskey",
                "abv_percent": 45.0,
                "net_contents": "750 mL",
            },
            "expected_overall": "PASS",
            "expected_per_field": {
                "brand": "PASS",
                "class_type": "PASS",
                "abv": "PASS",
                "net_contents": "PASS",
                "warning_text": "PASS",
                "warning_caps": "PASS",
                "warning_bold": "PASS",
            },
        },
    },
    {
        "filename": "02_fail_abv_mismatch.png",
        "render": {
            "brand": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "abv_text": "40% Alc./Vol. (80 Proof)",  # Label shows 40
            "net_contents": "750 mL",
            "warning": CANONICAL_WARNING,
            "warning_prefix_caps": True,
            "warning_prefix_bold": True,
            "apply_glare": False,
        },
        "expected": {
            "form_fields": {
                "brand": "OLD TOM DISTILLERY",
                "class_type": "Kentucky Straight Bourbon Whiskey",
                "abv_percent": 45.0,  # Form says 45 → mismatch
                "net_contents": "750 mL",
            },
            "expected_overall": "FAIL",
            "expected_per_field": {
                "brand": "PASS",
                "class_type": "PASS",
                "abv": "FAIL",
                "net_contents": "PASS",
                "warning_text": "PASS",
                "warning_caps": "PASS",
                "warning_bold": "PASS",
            },
        },
    },
    {
        "filename": "03_review_glare.png",
        "render": {
            "brand": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "abv_text": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "warning": CANONICAL_WARNING,
            "warning_prefix_caps": True,
            "warning_prefix_bold": True,
            "apply_glare": True,
        },
        "expected": {
            "form_fields": {
                "brand": "OLD TOM DISTILLERY",
                "class_type": "Kentucky Straight Bourbon Whiskey",
                "abv_percent": 45.0,
                "net_contents": "750 mL",
            },
            # FR-017: image_quality 'poor' coerces a provisional PASS to
            # NEEDS_REVIEW. The model SHOULD report image_quality='poor'
            # because of the glare overlay; if it doesn't, this fixture
            # may PASS instead — flag as a prompt-tuning signal.
            "expected_overall": "NEEDS_REVIEW",
            "expected_per_field": None,  # Tolerant — only assert overall
            "notes": "Tests FR-017 image-quality gate. Tolerant per-field.",
        },
    },
]


def main() -> None:
    for fx in FIXTURES:
        png_path = OUT / fx["filename"]
        yaml_path = OUT / (Path(fx["filename"]).stem + ".expected.yaml")
        _render_label(png_path, **fx["render"])
        with yaml_path.open("w") as f:
            yaml.safe_dump(fx["expected"], f, sort_keys=False)
        print(f"  wrote {png_path.name} + {yaml_path.name}")


if __name__ == "__main__":
    main()

# Eval fixtures

Three programmatically-rendered label PNGs + paired `expected.yaml` ground truth.

## Files

| Fixture | Scenario | Expected overall |
|---|---|---|
| `01_happy_old_tom.png` | Clean label, all fields match form | PASS |
| `02_fail_abv_mismatch.png` | Label says 40% ABV, form says 45% | FAIL |
| `03_review_glare.png` | Glare overlay simulates poor image quality | NEEDS_REVIEW |

## Regenerate

```bash
python tests/fixtures/labels/generate_fixtures.py
```

Output is byte-deterministic (same Python + Pillow version → same PNG hash).

## Known limitations

Programmatically-rendered labels exercise the wire format reliably but **diverge from real bottle photos in two ways the model notices:**

1. **The `GOVERNMENT WARNING:` prefix sits on its own line** (followed by the wrapped body on subsequent lines). Real bottle labels typically have the prefix inline with the first body sentence. GPT-4o sometimes returns `warning_prefix_all_caps=false` for the rendered version because the visual prefix is a standalone line — the model interprets that as a heading rather than the statutory "GOVERNMENT WARNING:" prefix.
2. **OCR re-flow can introduce whitespace differences** between the rendered text and `CANONICAL_WARNING`. The comparator's whitespace normalization handles most cases, but punctuation rendering (regular vs. typographic punctuation, em-dash etc.) can leak through.

In the live deploy smoke test on 2026-05-02:
- Fixture 01 returned overall **FAIL** instead of PASS because of (1) — the model reported `warning_prefix_all_caps=false` on the rendered prefix line.
- Fixture 02 returned the expected **FAIL** (ABV correctly detected at `abv_diff:5.0000>tolerance:0.1`).
- Fixture 03 returned **FAIL** due to (1), masking the FR-017 NEEDS_REVIEW path the fixture was meant to test.

**These are prompt-tuning issues, not pipeline bugs.** The pipeline correctly:
- Runs OpenAI vision once per label.
- Returns 7 typed field results.
- Applies deterministic comparators.
- Computes correct overall verdicts from the field results it has.
- Stays under the 5-second SLA (1.7–2.5s on Railway in the smoke test).

## Future work (in `ROADMAP.md`)

- Replace synthetic labels with 8–12 real-or-AI-generated bottle photos.
- Tune the system prompt (in `app/extraction/prompts.py`) to robustly identify the `GOVERNMENT WARNING:` prefix when it's a standalone line.
- Add an FR-018 "warning is *substantively* equivalent" comparator — Levenshtein ≥ 0.98 — alongside the byte-equal one, with the byte-equal as the strict gate and the Levenshtein as a soft signal.

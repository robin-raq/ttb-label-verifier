# Real-label fixtures

This directory holds **real** (non-synthetic) label artefacts: bottle photos,
TTB-approved COLA PDFs that an analyst downloaded from a browser session, or
labels supplied by a vendor with explicit fixture permission. Populate it
with `scripts/fetch_real_labels.py`.

The directory is empty by default. The eval harness in
`tests/eval/test_eval.py` globs PNGs recursively, so anything dropped here
with a paired `expected.yaml` is picked up automatically — no code changes.

## Why this is a manual-input directory, not a scraper output

| Source | Why we don't auto-fetch from it |
|---|---|
| `ttbonline.gov/colasonline/` (TTB COLA Public Registry) | Cert chain doesn't validate against public CAs; session-bound search UI; PDF-only artefacts. Programmatic scraping is brittle and may violate ToS. |
| Wikimedia Commons bottle photos | Most product packaging is *copyrighted* — Commons explicitly notes this. We can't redistribute as test fixtures. |
| Random Google image search | License-unclear. Same issue. |
| Vendor-supplied labels | License-clear but only if the vendor granted permission for *fixture redistribution*, not just internal review. |

The defensible workflow is **analyst sources locally → script imports**.

## Adding a real fixture

```bash
# An approved COLA PDF the analyst downloaded from a ttbonline.gov session:
python scripts/fetch_real_labels.py ~/Downloads/cola-12345678.pdf --slug bourbon-12345678 --page 1

# A photo of an actual bottle:
python scripts/fetch_real_labels.py ~/Pictures/bottle.jpg --slug rye-photo-2026-05

# A vendor-supplied PNG with explicit fixture permission:
python scripts/fetch_real_labels.py ~/Inbox/acme-merlot-2024.png --slug merlot-acme-2024
```

Each invocation:
1. Normalises the input to PNG (PDFs go through `pypdfium2` at ~144 dpi).
2. Drops `<slug>.png` next to this README.
3. Scaffolds `<slug>.expected.yaml` with TODO markers for the form fields
   and expected verdicts.
4. The analyst fills the YAML in by reading the *original COLA application*
   (not by guessing from the label image — the form fields are the
   submitted application data, not what's printed on the bottle).

## License hygiene

- **Federal records (TTB-approved COLAs)** are public domain in the USA per
  17 U.S.C. § 105. Safe to commit to a public repo.
- **Vendor-supplied labels** are safe to commit ONLY with written fixture
  permission. Note the permission source in the YAML's `notes:` field.
- **Photographs of bottles you own** — your photo, your copyright, your
  permission to commit.
- **Anything else** — don't commit. Keep it local under `.gitignore` or a
  per-developer `~/ttb-fixtures/` directory you point the script at.

## What the eval harness does with these

- `make eval` (default mocked): structural-only check that each PNG has a
  paired YAML. No network calls.
- `RUN_LLM_TESTS=1 pytest tests/eval -q`: hits the real OpenAI vision client
  for every fixture, including these. Cost: a few cents per real fixture.

Real fixtures are the high-leverage eval signal: 12 synthetic + N real
demonstrates that the synthetic eval set is a
proxy, not the goalpost.

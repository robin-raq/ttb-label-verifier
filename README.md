# TTB Label Verifier

AI-powered prototype that helps TTB compliance agents verify alcohol-beverage label images against application form data.

> **Status:** Foundation scaffold (Phase A). Implementation lands in Phase B.

## Quick start

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # then fill in OPENAI_API_KEY
pytest -q
```

## Architecture

See `SPEC.md` (kept private) for the binding contract. High-level:

1. Agent uploads label image + form fields to `POST /verify`.
2. Backend calls OpenAI vision **once**, structured output → `LabelExtraction`.
3. Deterministic comparators (`app/comparators/`) compare extraction vs form / 27 CFR §16.21 statute.
4. Verdict precedence (`app/verdict.py`) yields `PASS` / `FAIL` / `NEEDS_REVIEW`.
5. Audit log appended (no image bytes; SHA-256 only).

Batch endpoint `POST /verify/batch` streams per-label results via SSE for 200–300-label uploads.

## Layout

```
app/
  constants/    # CANONICAL_WARNING (27 CFR §16.21)
  schemas/      # Pydantic models — LabelExtraction, VerifyRequest/Response
  comparators/  # Deterministic field comparison (Phase B1)
  extraction/   # OpenAI vision client (Phase B3)
  api/          # FastAPI routes + audit logger (Phase B2)
  audit/        # JSONL audit logger (Phase B2)
  verdict.py    # Overall verdict computation (foundation)
tests/
  comparators/      # Unit tests, ≥95% line cov (Phase B1)
  api/              # Integration with mocked OpenAI (Phase B2)
  contract/         # Response shape tests (Phase B2)
  adversarial/      # Prompt-injection, smart-quote, image-quality (Phase B2)
  performance/      # NFR-001 mocked latency gate (Phase B2)
  test_smoke.py     # Foundation canary
  conftest.py       # Shared fixtures (fake_openai_client, tiny_png)
```

## Test commands

| Target | Purpose |
|---|---|
| `make test` | Run all tests |
| `make ci-cov-comparators` | Comparator unit suite + 95% gate |
| `make ci-cov-verdict` | Verdict suite + 90% gate |
| `make ci-cov-api` | API + contract + adversarial + 80% gate |

## Limitations (v1 scope)

- **Distilled-spirits sample only.** v1 verifies brand, class/type, ABV, net contents, Government Warning. Bottler/producer name, address, and country of origin are **out of scope**.
- **No COLA integration.** Standalone proof-of-concept; future work in `ROADMAP.md`.
- **No authentication.** Open at the deployed URL.
- **No PII persisted.** Image bytes discarded after request; only SHA-256 logged.
- **Single-LLM dependency.** OpenAI only in v1; multi-provider fallback in `ROADMAP.md`.

## License

MIT — see `LICENSE`.

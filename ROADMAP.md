# Roadmap — TTB AI Label Verification Prototype

Tracked planning document. The "above the line" v1 milestone is complete; below-the-line entries are concrete enough to pick up cold.

---

## Shipped — v1 (take-home milestone)

All items from the original v1 scope landed. Evidence: PR #1 (`feat/post-feedback-hardening`, 25 commits, merged 2026-05-04) and the foundational commits before it.

### Backend
- [x] `pyproject.toml`, `ruff`, `mypy`, `pytest`, pinned `python = "3.12"`
- [x] FastAPI skeleton: `app/api/main.py`, CORS, secure-headers middleware, slowapi rate limit
- [x] `app/constants/ttb_warning.py` — 27 CFR §16.21 verbatim
- [x] `app/schemas/extraction.py` — Pydantic `LabelExtraction` with per-field confidences
- [x] `app/extraction/openai_vision.py` — single GPT-4o call, structured outputs, retry-once
- [x] `app/comparators/{text_match,numeric_match,volume_match,warning_match}.py`
- [x] `app/verdict.py` — combine field results
- [x] `app/audit/jsonl_logger.py` — append-only audit log (mode 0o600)
- [x] `app/api/routes.py` — `POST /verify` and `POST /verify/batch` (SSE; batch uses `asyncio.as_completed` + reorder buffer so rows stream while preserving ascending `index`)
- [x] `filetype` (replaced `python-magic`) file-type validation, 10 MiB cap, image format whitelist
- [x] `app/extraction/__init__.py` — `VisionClient` Protocol seam (the production-deployment swap point)
- [x] `app/api/deps.py` — env-var-driven factory (`VISION_PROVIDER`)
- [x] `app/__init__.py` — `load_dotenv()` at package init for local-dev convenience

### Frontend
- [x] Vite + React 18 + TypeScript scaffold
- [x] Single-label screen — drop-zone + form fields + result card
- [x] Batch screen — ZIP + `manifest.csv` (per-row payloads) + SSE progress + per-row results table
- [x] DOMPurify on extracted text rendering
- [x] "Disagree with verdict?" feedback affordance
- [x] Mock COLA queue (Screen 0) — 10 fixture-driven applications + pre-staged BATCH demo card

### Eval
- [x] **16 fixture images** — 12 synthetic happy/failure-mode + 4 adversarial (smart quotes, title-case prefix, missing warning, prompt-injection-in-image). Beats the original 12-fixture target.
- [x] Hand-labeled `expected.yaml` per fixture
- [x] `make eval` script + structural conformance test
- [x] Adversarial fixtures cover security-relevant comparator paths
- [x] **Real-label intake pipeline** (`scripts/fetch_real_labels.py`) + recursive eval glob — `tests/fixtures/labels/real/` is auto-included once populated

### Tests
- [x] Comparator unit tests (~95% line coverage)
- [x] API integration tests with mocked OpenAI
- [x] Adversarial test suite
- [x] Gated `tests/llm/` for end-to-end with real OpenAI
- [x] Path-traversal regression suite (`tests/api/test_frontend_path_traversal.py`)
- [x] Protocol conformance + MIME data-URL tests (`tests/extraction/`)
- [x] Batch audit + early-exit audit tests (`tests/api/test_batch_audit.py`, `test_batch_early_exit_audit.py`)

### Deploy
- [x] Multi-stage Dockerfile (Node frontend build → Python backend → slim runtime)
- [x] One-container, one-URL — FastAPI serves both `/verify*` API and the static React bundle
- [x] Railway project + auto-deploy from `main`
- [x] Env vars in Railway dashboard
- [x] Smoke test of deployed URL

### Docs
- [x] `README.md` — what / why / setup / run / deploy / eval / assumptions / limitations + Deployment constraints section pointing at the `VisionClient` swap seam
- [x] ASCII architecture diagram (Mermaid was the original aim; ASCII renders without JS in any markdown viewer)
- [x] `LICENSE` (MIT)
- [x] `.env.example`
- [x] `.gitignore`

### Submission
- [x] Public GitHub repo URL: https://github.com/robin-raq/ttb-label-verifier
- [x] Deployed URL: https://ttb-label-verifier-production-4436.up.railway.app
- [x] README "Approach / Tools / Assumptions" addresses the take-home brief

---

## Shipped — v1.1 hardening pass (PR #1, merged 2026-05-04)

The 25-commit pass that responded to the post-take-home feedback round. Notable beyond the checked items above:

- **Pipeline unified** — `/verify` and `/verify/batch` route through one `_process_single` returning `(response, sha256, extraction)`. Eliminates the duplicate-pipeline drift risk.
- **Audit-log fidelity** — every batch row writes a record (including the three early-exit failure paths that previously emitted SSE error events but skipped the audit log). `batch_id` UUID propagates through audit + every SSE frame for cross-row correlation.
- **MIME-aware vision data URL** — `filetype.guess()` drives the `data:image/jpeg|png|webp;base64,...` prefix; previously hardcoded PNG for every upload.
- **VisionClient Protocol seam** — production-deployment swap point in code, not just docs.
- **`.env` loads at package init** — uvicorn / pytest / standalone scripts all see the same configuration.
- **Security hardening** — SPA path-traversal fix + CORS `allow_credentials=False` (matches statelessness).
- **Accessibility** — tablist semantics, `aria-label`s on actions, `aria-busy` during async.
- **Performance** — chunked `fileToBase64` avoids stacking huge data-URL buffers for batch uploads.
- **Renderer fix** — `GOVERNMENT WARNING:` prefix renders inline with body (matches real labels), no longer trips the model into reading it as a heading.

---

## Below the line — post-v1 backlog

Each item is concrete enough to pick up cold. Effort estimates and "why deferred" included.

### Reliability & Resilience
- **Multi-LLM fallback / Azure OpenAI client.** Seam now exists (`VisionClient` Protocol + `VISION_PROVIDER` env var). Implementation work: drop an `AzureOpenAIVisionClient` next to the OpenAI one, add a branch in `get_vision_client`. ~1 day for Azure; ~half day each for Anthropic / Gemini behind the same seam.
- **Async-safe audit writes.** `write_audit_record` is a synchronous syscall called from the async event loop; with `BATCH_CONCURRENCY=25` and 500-item batches, sequential blocking writes can stall SSE delivery. Wrap in `run_in_executor` or use `anyio.to_thread`. ~1 hour. Caught in PR #1's review.
- **Retry on low extraction confidence.** Currently retries only on transport errors. Add: if any field's confidence < 0.5, re-call vision in `detail=high` mode and merge results. ~2 hours.
- **Image preprocessing pipeline.** OpenCV-based de-skew + glare reduction before vision call. Replicate's restoration models tested — too slow (5+ s). Try lightweight CV first. ~half day spike.

### Compliance & Production-readiness
- **FedRAMP compliance path.** Audit against NIST 800-53. Needs Azure Gov cloud, in-region Azure OpenAI, FIPS 140-2 crypto, key vault for `OPENAI_API_KEY`, immutable audit log to Azure Sentinel. **Big effort — 2–3 weeks of paperwork before any code.**
- **Privacy Act / PII review.** v1 explicitly avoids PII; production growth requires a Privacy Impact Assessment with TTB privacy office.
- **Document retention policy.** Current 7-day audit-log retention is arbitrary. Confirm legal retention period with TTB records management.
- **Apache-2.0 license switch.** Patent grant matters more than MIT's brevity if Treasury adoption gets serious.
- **Real authentication.** Prototype is open at the deployed URL; production rollout needs TTB SSO.

### Integration
- **COLA system bridge.** Read-only consumption of COLA application data via whatever API the .NET system exposes. Saves agents from re-typing. **Blocked on:** TTB authorization for COLA access.
- **Azure deployment path.** Railway → Azure App Service migration. Mostly mechanical (Dockerfile is portable). The `VisionClient` Protocol seam means `extraction/` is the only thing that materially changes.

### Eval & Observability
- **CI eval gate.** GitHub Action runs `make eval` on every PR; fails if accuracy drops below previous baseline. Needs: pinned baseline (`eval/baseline.json`), bot to update baseline on green main.
- **LangSmith / Logfire / Braintrust integration.** Real observability for prompt iteration. Defer until JSONL `grep` is painful — probably after first 100 real users.
- **Real labels under `tests/fixtures/labels/real/`.** Intake script exists; the directory is empty by default (license-clean sourcing requires the analyst to download from a `ttbonline.gov` browser session). Aim for ≥ 8 real fixtures spanning beer / wine / spirits / 5+ countries-of-origin.
- **Larger synthetic eval set.** 16 fixtures today. 100+ across beverage types is the long-term goal.
- **A/B prompt testing harness.** Run two prompt versions on the same fixtures; report per-version accuracy.

### UX
- **Drag-and-drop reordering of batch results.** Sort by verdict / confidence / field-failure-type so agents triage fast.
- **Inline image viewer.** Click a result row → see the label image with extracted bounding boxes overlaid (vision model can return them).
- **Keyboard shortcuts.** `j/k` to navigate batch results, `r` to flag, `enter` to approve. Matches existing COLA muscle memory.
- **Print-friendly result page.** CSS print stylesheet for a one-pager per label.
- **Live-region announcements.** When verification completes, announce the verdict via `aria-live="polite"` so screen readers don't have to be focused on the result card to hear it.

### Code quality
- **De-duplicate `tiny_png` fixture** — `test_batch_audit.py` reimplements the conftest fixture verbatim. Caught in PR #1's review.
- **Drop `extraction_failed` boolean** — redundant with `extraction is None` in `_process_single`.
- **Unify `_ALLOWED_MIMES`** — `routes.py` and `openai_vision.py` declare parallel constants with divergent semantics (route rejects unknown; client silently coerces to PNG).
- **Coverage gate at 90%** once the comparator suite stabilizes.
- **Property-based tests** on `volume_match` (Hypothesis library). Unit conversions are random-input-fuzzing's natural fit.
- **Mutation testing** on comparators (`mutmut`). Comparators are < 30 lines but they are the business logic.
- **Symlink test in path-traversal regression suite.** The fix uses `Path.resolve()` which follows symlinks; the suite never exercises that vector.

### Tooling investigated and rejected (don't re-spike)
- **CrewAI / AutoGen multi-agent.** 30-min spike: 200ms+ orchestration overhead per request, zero capability we couldn't get from one structured-output call.
- **Tesseract OCR as a fallback.** Quality on stylized fonts much worse than GPT-4o. Marcus's firewall scenario is better solved by Azure OpenAI in-region than by an OCR fallback.
- **Server-side image generation for fixtures.** Replicate's models are slow + cost more than DALL·E. Stick to manual generation.

---

## Notes & open questions

- **Prompt versioning.** System prompt lives in code, logged via `prompt_version` constant. When the eval set grows, version + commit-hash this so we can replay any historical decision.
- **What's the actual TTB target accuracy?** Sarah didn't give a number. Their existing manual rate has its own error bar. My guess: "≥ human accuracy" plus "no false approvals on warning/ABV." Confirm before any production conversation.
- **Bold detection reliability on GPT-4o.** PRESEARCH §10.7 treats `is_bold` as a model-reported boolean. Empirical question: verify this on the eval set; if noisy, fall back to "if 'GOVERNMENT WARNING:' is the same font weight as surrounding text → likely not bold."
- **Prompt-version semantics.** The `VisionClient.extract(image_bytes, prompt_version)` parameter is currently an audit passthrough — the actual prompt comes from the module-level `PROMPT_VERSION` constant. Documented but worth tightening so callers can't pass a value that diverges from what's actually sent. Caught in PR #1's review.

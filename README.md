# TTB Label Verifier

AI-powered prototype that helps TTB compliance agents verify alcohol-beverage label artwork against the structured application data already on file in COLAs Online.

| | |
|---|---|
| **Live demo** | https://ttb-label-verifier-production-4436.up.railway.app |
| **Source** | https://github.com/robin-raq/ttb-label-verifier |
| **License** | MIT |

---

## Try it (3 ways)

### 1. The mock-COLA queue (default screen on the live URL)
Click any application's **Review** button. The form auto-populates with the structured fields and the label image is auto-attached. Click **Verify Label** — results in ~2–3 seconds.

### 2. Single-label manual entry
Switch to the **Single Label** tab, upload a label image, type the form values, submit.

### 3. Hit the API directly
```bash
curl -X POST https://ttb-label-verifier-production-4436.up.railway.app/verify \
  -F "image=@/path/to/label.png;type=image/png" \
  -F 'payload={"brand":"OLD TOM DISTILLERY","class_type":"Kentucky Straight Bourbon Whiskey","abv_percent":45.0,"net_contents":"750 mL"}'
```

### 4. Batch — ZIP + `manifest.csv`
On the **Batch** tab, upload a ZIP containing a `manifest.csv` (root or any subfolder; the shallowest file wins) plus the image files referenced by each row. One row = one COLA-style application with its own brand, class/type, ABV, and net contents. Optional `cola_id` is passed through as `request_id` for tracing.

Example `manifest.csv` (see also `samples/example-manifest.csv`):

```csv
image_filename,brand,class_type,abv_percent,net_contents,cola_id
labels/sku-a.png,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45.0,750 mL,COLA-001
```

A TTB compliance batch is N *different* applications, so there's intentionally no "shared form" mode — applying one set of fields to many label images doesn't model the real job.

---

## TL;DR — what this does

A TTB compliance agent's job — per the discovery interviews — is **visual cross-referencing**. They open an application in COLA (which already has structured data: brand name, class/type, ABV, net contents) and the attached label artwork; their eyes go *form field → label image → match? check.* For 7 fields, 13 applications a day, sometimes 300 in a peak-season batch.

This prototype mechanizes the cross-reference. One OpenAI multimodal call extracts the visible label content as a typed JSON object; deterministic Python comparators decide PASS / FAIL / NEEDS_REVIEW per field; an overall verdict is composed and returned in under 5 seconds. The agent retains final authority — the tool is decision support, not decision automation.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ React (Vite) UI                                                 │
│   • Mock COLA queue (default)                                   │
│   • Single-label form                                           │
│   • Batch: ZIP + manifest.csv (per-row payloads) + SSE                  │
└────────────────┬────────────────────────────────────────────────┘
                 │ multipart POST /verify   |   POST /verify/batch (SSE)
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ FastAPI                                                          │
│   1. Validate upload (filetype sniff, ≤10 MiB) — FR-002         │
│   2. SHA-256 the image bytes                                    │
│   3. Call OpenAI vision ONCE with structured-output schema      │
│      └─► returns LabelExtraction (typed Pydantic)               │
│   4. Run deterministic comparators in parallel                  │
│      ├─ compare_brand    (rapidfuzz, ≥0.92 ratio)               │
│      ├─ compare_class_type (form ⊆ label substring)             │
│      ├─ compare_abv      (±0.1 %)                               │
│      ├─ compare_volume   (mL/L/fl-oz normalized, ≤1 mL diff)    │
│      └─ compare_warning  (text + caps + bold = 3 results)       │
│   5. Compose overall verdict (precedence + FR-017 gate)         │
│   6. Append audit record to JSONL (no image bytes)              │
│   7. Return VerifyResponse                                       │
└─────────────────────────────────────────────────────────────────┘
```

**One container, one URL.** The FastAPI process serves both the API and the pre-built React static bundle from `/app/frontend_dist/`. Multi-stage Dockerfile builds the frontend with Node, then the backend with Python, then a slim runtime. No frontend/backend split, no CORS dance.

---

## Deployment constraints

The v1 prototype on Railway calls **public OpenAI** server-side. That's fine for a demo URL hit from a reviewer's laptop, but TTB's internal network is known (per Marcus's discovery interview) to firewall most third-party ML endpoints — a prior scanning-vendor pilot shipped half-broken because outbound connections to the vendor's inference endpoints were blocked.

**Production rollout inside TTB needs a different vision provider, not a different app.** The pluggable seam is already in code:

- `app/extraction/__init__.py` defines a `VisionClient` Protocol — `async extract(image_bytes, prompt_version) -> LabelExtraction`.
- `app/extraction/openai_vision.py:OpenAIVisionClient` is the v1 implementation.
- `app/api/deps.py:get_vision_client` selects the implementation via the `VISION_PROVIDER` env var (default `openai`; `azure` is reserved and raises a clear `NotImplementedError` pointing at the swap location).

To run inside TTB's gov-cloud tenant, drop an `AzureOpenAIVisionClient` next to the OpenAI one, add a branch in `get_vision_client`, and set `VISION_PROVIDER=azure` plus the Azure-specific env vars. **No changes to routes, comparators, audit logging, or tests.** A protocol-conformance test (`tests/extraction/test_protocol.py`) fails fast if a new client diverges from the contract.

This is also why a single-vendor switch (e.g. swapping OpenAI for public Gemini) would not solve the firewall problem — both public APIs face the same egress wall. The right answer is in-network deployment via Azure OpenAI, which is `ROADMAP.md → Integration` v2 work.

---

## Key design decisions

### 1. Verification, not extraction — the form fields are the application data, not duplicate entry

**Decision:** the UI requires both a label image *and* the structured application fields (brand, class/type, ABV, net contents).

**Alternatives considered:**
- Extract-only: just OCR the label, show what's there.
- Auto-fill from an uploaded form document (PDF/image of TTB Form 5100.31).

**Why this:** the discovery research showed the application data is **not a paper form** the agent is holding — it's structured data already in COLAs Online. The agent sees a screen with brand name, ABV, etc. as typed fields, alongside the uploaded label artwork. Their job is to confirm the label *matches* the application. So our UI mirrors what's already there — form fields = the structured COLA data; label image = the artwork attachment. Without the form fields, there's nothing to verify *against* — only text to OCR.

**Tradeoff:** a producer pre-checking their own draft label can't use this without typing the values they're about to submit. That's a different (legitimate) use case captured in `ROADMAP.md` as "extract-only mode."

### 2. Mock COLA application queue is the default screen

**Decision:** the live demo opens on a queue of three pre-loaded applications. Clicking **Review** auto-populates the form with the application's structured data and auto-attaches its label image.

**Alternatives considered:**
- Default to manual single-label upload (the original design).
- A "Load sample application" button on the manual form.

**Why this:** the discovery interview explicitly notes agents *don't type* — they pull data from COLA. A mock queue is the most faithful prototype of that workflow: the agent picks an application, doesn't enter anything, gets a verdict. It also makes the demo a one-click affair for reviewers, eliminates the "why am I typing this?" cognitive friction that the form fields invite, and aligns the prototype's surface with how production COLA→our-tool integration would actually look.

**Tradeoff:** the queue is hard-coded — three fixed applications, not a real queue with auth or pagination. A reviewer who wants to test their own image still needs the manual single-label tab. Production swaps the JSON file for a real COLA API call; nothing else changes.

### 3. Single OpenAI multimodal call, not two-model handoff

**Decision:** GPT-4o reads the label image AND returns a typed `LabelExtraction` JSON in one call. Comparison logic is pure Python in our service, not an LLM.

**Alternatives considered:**
- Two models (vision → comparison) in separate API calls instead of one multimodal pass.
- Function-calling agent that orchestrates per-field tool calls.

**Why this:** two LLM calls double the network latency, double the failure surface, and require two API keys. One call returning structured JSON gives us the same data with half the round-trips. Comparison-as-LLM is also the wrong place for that logic — comparators must be unit-testable without burning OpenAI tokens, and federal-statute compliance (the warning text) cannot rest on a stochastic model's judgment.

**Tradeoff:** single-vendor dependency. If OpenAI is down, we're down. v2 fallback to Anthropic Claude or Google Gemini is in `ROADMAP.md`.

### 4. Deterministic comparators after extraction — LLM extracts, code judges

**Decision:** for every field comparison (brand, class/type, ABV, net contents, warning text/caps/bold), the LLM is the OCR; pure Python is the verdict.

**Alternatives considered:** ask the LLM "does this label match this form?" with a JSON answer.

**Why this:** verdicts must be reproducible, auditable, and unit-testable. Pure functions get `pytest --cov=app.comparators=100%` for free; LLM-judged comparisons get expensive non-determinism. The Government Warning specifically is a federal-statute byte-equality check (`27 CFR §16.21`); a stochastic model cannot be the judge.

**Tradeoff:** comparators must encode every legitimate variation explicitly (e.g. brand-name normalization for smart quotes, volume-unit normalization). If a real-world variant isn't in the comparator, it'll fail when an LLM might have been forgiving. We catch this with the `NEEDS_REVIEW` state — see decision #6.

### 5. No agent framework (LangChain / LangGraph / CrewAI)

**Decision:** plain Python pipeline. One async function: `validate → extract → compare → verdict → audit`.

**Alternatives considered:** LangChain (popular), LangGraph (state-machine), CrewAI (multi-agent).

**Why this:** agent frameworks earn their weight when an agent has to *plan* — pick which tool to call, reflect on errors, loop. This app does the same three steps in the same order every time. A framework would add overhead and tighten our 5-second SLA without adding capability.

**Tradeoff:** no easy upgrade path to multi-step reasoning (e.g. "if image is blurry, request a better one"). YAGNI for v1; defer until a real need.

### 6. Three verdict states: PASS / FAIL / NEEDS_REVIEW

**Decision:** every field result and the overall verdict has three states.

**Alternatives considered:** binary pass/fail.

**Why this:** false approvals (PASS when actually FAIL) are the most dangerous outcome — a non-compliant label reaches market. False rejections are merely annoying. The `NEEDS_REVIEW` state is the safety valve: when confidence is below threshold, the system tells the human "look at this one yourself." This directly addresses senior agent Dave's skepticism (*"you can't just pattern-match everything"*) — the tool flags, the human judges.

**Tradeoff:** more UX complexity (three colors). Worth it.

### 7. Hard-coded canonical TTB warning text — not LLM-judged

**Decision:** `app/constants/ttb_warning.py` contains the byte-perfect 27 CFR §16.21 text. The comparator normalizes whitespace and compares `==`. The LLM is never asked "is this warning valid?"

**Alternatives considered:** ask the LLM whether the warning matches the regulation.

**Why this:** the warning is a fixed federal statute. Every character matters. Letting a model decide if it matches would invite hallucinated approvals on subtly altered warnings — Jenny's quote in the discovery interview describes producers trying *exactly that* ("creative wording, smaller font, title case instead of all caps").

**Tradeoff:** OCR errors (e.g. "Sur9eon" for "Surgeon") cause false rejections. We mitigate by retrying with higher-detail vision when confidence is low, and route any below-0.95-confidence warning extraction to NEEDS_REVIEW.

### 8. Two-tier confidence thresholds: 0.95 for warning, 0.80 for fuzzy fields

**Decision:** warning text/caps/bold require `field_confidence ≥ 0.95` for PASS; brand, class/type, ABV, net contents require `≥ 0.80`.

**Alternatives considered:** single global threshold (0.85 was an early proposal).

**Why this:** federal-statute checks deserve a stricter bar than fuzzy fields like brand-name matching. The warning is non-negotiable; the brand match is tolerant of capitalization and punctuation variants.

**Tradeoff:** thresholds are empirically chosen; need calibration against a larger eval set. Captured in `ROADMAP.md`.

### 9. FR-017 image-quality gate — poor photos can't yield a clean PASS

**Decision:** after computing the field-level verdicts, if the LLM reports `image_quality = "poor"` and the provisional overall is PASS, downgrade to NEEDS_REVIEW. If the provisional is FAIL, leave it FAIL.

**Why this:** Jenny's quote: *"if an agent can't read the label they just reject it and ask for a better image."* A glare-obscured label may have looked like it passed only because the model couldn't read the failing field. Better to flag for human review than to auto-approve unread artwork.

**Tradeoff:** a definitely-wrong label still FAILs (we never *upgrade* on poor quality) — so the gate is asymmetric: it only downgrades PASS, never inflates FAIL. This matters for false-approval risk.

### 10. Async fan-out for batch (asyncio.Semaphore(25)), not a job queue

**Decision:** `POST /verify/batch` accepts up to 500 JSON items (`image_b64` + per-item `payload`), processes them concurrently via an `asyncio.Semaphore(25)`, and streams per-item results via SSE. The SPA unpacks **ZIP + `manifest.csv`** in the browser and builds that payload list — heterogeneous batches without COLA wiring. No Celery / RQ / job-queue infrastructure.

**Alternatives considered:** real task queue (Celery + Redis) with "submit job, poll for results."

**Why this:** a 300-label batch finishes in under 60 seconds with 25-way concurrency. The user can wait on the page (with a progress bar). A queue would add ops complexity and "submit job, come back later" UX — overkill at this scale.

**Tradeoff:** if the user closes the tab, the work is lost. Resumable batches → v2.

### 11. JSONL audit log on the container's `/data` directory

**Decision:** every verification appends a single JSON line to `/data/audit.jsonl` with timestamp, request ID, image SHA-256, model ID, prompt version, form fields, full extraction (including per-field confidences), per-field results, overall verdict, and latencies. **Image bytes are never persisted — only the SHA-256 hash.**

**Alternatives considered:** Postgres, SQLite, LangSmith / Logfire / Braintrust SaaS observability.

**Why this:** a JSONL file is grep-able, jq-able, has zero ops cost, and gives perfect-fidelity audit. A database is overkill at TTB's scale (~150K applications/year — decades of headroom in a single file). Federal compliance also discourages shipping every prompt to a third-party SaaS.

**Tradeoff:** Railway's free tier doesn't include a managed volume, so the audit log is currently ephemeral (lost on container restart). Promotion to a Railway-managed volume (mounted at `/data`) is a one-click change in the Railway dashboard — no code change needed.

### 12. Single-service Docker container, not two services

**Decision:** one Railway service runs both the API and the static frontend. Multi-stage Dockerfile: Node 20 builds Vite → Python 3.12 installs deps → slim runtime copies both.

**Alternatives considered:** separate frontend (static host) + backend (FastAPI) services.

**Why this:** one service = one URL = one set of env vars = no CORS dance = simpler reviewer experience. The static React bundle is small (~190 KB) so co-locating it with the API costs nothing.

**Tradeoff:** can't independently scale the two halves — irrelevant at prototype scale.

### 13. Python + FastAPI on the backend

**Decision:** Python 3.12 with FastAPI, Pydantic v2, and the OpenAI SDK.

**Alternatives considered:** Node + Express (single-language with the React frontend).

**Why this:** Python's image-handling and LLM ecosystem (Pydantic structured outputs, rapidfuzz, filetype, OpenAI SDK) is more mature and better-documented for this kind of work. FastAPI also offers free OpenAPI docs at `/docs`.

**Tradeoff:** two languages in the repo — minor friction at the boundary.

### 14. React + Vite + TypeScript on the frontend

**Decision:** React 18, Vite, TypeScript, DOMPurify, `@microsoft/fetch-event-source` for SSE-over-POST. No Tailwind, no MUI, no Redux.

**Why this:** minimal bundle for a minimal UI. Vite's dev server is fast; TS catches API contract drift; DOMPurify hardens against attacker-controlled extracted text rendering in JSX.

**Tradeoff:** hand-rolled CSS is more verbose than utility-class libraries, but the surface is small enough that it's fine.

### 15. Railway for hosting

**Decision:** Railway (auto-deploys from `main`, builds the Dockerfile, generates a public URL).

**Alternatives considered:** Fly.io, Render, Vercel.

**Why this:** Railway gives the smoothest deploy UX of the four; the auto-generated `*.up.railway.app` URL is both the deliverable URL and good enough as a demo origin.

**Tradeoff:** ❌ Vercel was a non-starter — its serverless model breaks our streaming-batch and long-lived-JSONL assumptions.

### 16. Programmatically rendered eval fixtures (Pillow), not real bottle photos

**Decision:** `tests/fixtures/labels/` contains three labels rendered with Pillow — happy path, ABV mismatch, glare overlay. Each has a paired `expected.yaml` ground-truth file.

**Alternatives considered:** AI-generated photo-realistic labels (DALL·E), real-world bottle photos.

**Why this:** programmatically rendered labels are deterministic (re-running the generator produces byte-identical PNGs), free (no LLM tokens for fixtures), and have real text the OCR can read. They exercise the full pipeline reliably.

**Tradeoff:** they look synthetic, not photographic. Specifically, the rendered "GOVERNMENT WARNING:" prefix sits on its own line, which the model occasionally misclassifies — so fixture #01 currently returns FAIL where we'd want PASS. This is a *prompt-tuning issue* exposed by the eval, not a pipeline defect; it's documented in `tests/fixtures/labels/README.md` and `ROADMAP.md` as v1.1 work.

### 17. MIT license, public GitHub

**Decision:** MIT, public.

**Alternatives considered:** Apache 2.0 (patent grant), private repo.

**Why this:** MIT is one line, maximum permissive, standard for take-home prototypes. Public so reviewers can browse without auth.

**Tradeoff:** if Treasury pursues productionization, Apache-2.0's patent grant is preferable — captured in `ROADMAP.md`.

---

## Tools and libraries

### Backend (`pyproject.toml`)
| Library | Why |
|---|---|
| `fastapi` | async-first HTTP framework with native Pydantic + automatic OpenAPI docs |
| `pydantic` v2 | typed models for request/response/extraction; powers OpenAI structured outputs |
| `openai` v1.55+ | official SDK with `response_format=json_schema` mode |
| `rapidfuzz` | brand-name fuzzy match (`fuzz.ratio`); chosen over fuzzywuzzy for speed and no-LGPL |
| `filetype` | pure-Python MIME sniffing (no `libmagic` system dep) |
| `python-multipart` | required by FastAPI for multipart form parsing |
| `secure` | HTTP security headers (FastAPI's Helmet equivalent) |
| `slowapi` | per-IP rate limiting (30 req/min default) |
| `sse-starlette` | SSE response helper for batch streaming |
| `uvicorn[standard]` | production ASGI server |

### Frontend (`frontend/package.json`)
| Library | Why |
|---|---|
| `react`, `react-dom` v18 | minimal SPA; no router (3 screens, simple state suffices) |
| `dompurify` | sanitize attacker-controllable extracted text before JSX rendering |
| `@microsoft/fetch-event-source` | SSE over POST (native `EventSource` only supports GET) |
| `jszip` | unpack ZIP + images client-side before batch POST |
| `papaparse` | parse `manifest.csv` rows with tolerant header handling |
| `vite` v6 | fast dev + small prod bundles |
| `typescript` v5 | catch API contract drift at compile time |

### Testing
| Library | Why |
|---|---|
| `pytest` | obvious choice |
| `pytest-asyncio` (auto mode) | async route tests via FastAPI's TestClient |
| `pytest-cov` | per-package coverage gates per SPEC §7.3 |
| `httpx` | TestClient transport |
| `Pillow`, `PyYAML` | fixture generator + expected.yaml parsing |

### Deploy
| Tool | Why |
|---|---|
| Docker (multi-stage) | Node-build frontend → Python-build backend → slim runtime |
| Railway | one-command deploy from GitHub; auto-rebuild on push |
| GitHub Actions | `pytest` on PRs (mocked LLM only — `RUN_LLM_TESTS=1` not in CI) |

---

## Assumptions made

These shape the v1 scope; each is captured explicitly so the take-home reviewer can sanity-check.

1. **Distilled-spirits sample only.** The take-home doc's worked example is a bourbon. The TTB regulations also require bottler/producer name and country-of-origin (for imports), but the worked example doesn't include them and the spec scope didn't either — so v1 verifies brand, class/type, ABV, net contents, and the Government Warning. Bottler and origin are explicitly out of scope.
2. **No COLA integration.** The mock queue stands in for COLA's real API. Marcus (IT) explicitly de-scoped integration for the prototype.
3. **No authentication.** The deployed URL is open to anyone with the link.
4. **Single LLM provider.** OpenAI only. No Anthropic / Google / open-source fallback.
5. **Ephemeral audit log on the prototype.** The `/data/audit.jsonl` file is wiped on container restart. Production needs a Railway-managed volume — one click.
6. **OpenAI does not train on API requests by default.** Per OpenAI's enterprise data policy (2023+). Documented as an assumption since v1 ships no separate data-handling agreement.
7. **The reviewer's network can reach OpenAI.** The discovery interview noted TTB's network blocks many outbound endpoints; the prototype runs *outside* that network, so this isn't a deployment problem here. Production rollout would swap in Azure OpenAI via the `VisionClient` Protocol seam — see **Deployment constraints** above.
8. **The 5-second SLA is per single-label call.** Batch is allowed to take longer in aggregate but each label finishes in ≤ 5 s.
9. **Fixtures aren't reviewed photos.** They're programmatic. Real-world labels would tune the prompt better.

---

## What's not implemented (limitations)

Honest list — the take-home asks for trade-offs and limitations.

- **Single-LLM dependency.** OpenAI down → app down.
- **No image preprocessing.** No de-skew, no glare reduction, no contrast normalization. Pass the image straight to GPT-4o.
- **OCR brittleness on stylized fonts.** Whisky labels with gothic/script type drop confidence; more cases hit `NEEDS_REVIEW`.
- **Confidence thresholds are empirical.** 0.95 / 0.80 was reasoned from PRESEARCH §3 but not calibrated against a large eval set.
- **No persistent state across container restarts.** Audit log lives on the container's filesystem; needs a Railway volume.
- **No real auth.** Anyone with the URL can submit.
- **ZIP is client-expanded only.** Large archives are fully loaded in-browser before POST; giant batches can stress memory versus a server-side ingestion job (`ROADMAP.md`).
- **Volume normalization is naive.** Handles mL ↔ L ↔ fl oz with ±1 mL tolerance; obscure units (e.g. `375 ml e` European convention) might fail.
- **Mock COLA queue is hard-coded.** Three fixed applications, no auth, no pagination. Real COLA integration is a v2 swap.
- **Fixture #01 currently returns FAIL on the live deploy** because the rendered "GOVERNMENT WARNING:" prefix sits on its own line and the model intermittently classifies it as a heading. Documented in `tests/fixtures/labels/README.md` — prompt-tuning fix for v1.1.

---

## Future work (ingestion beyond v1 ZIP + manifest)

Two follow-ups discussed in discovery that are intentionally **not** in this prototype beyond documenting the trajectory:

1. **Official COLA / TTB structured export.** When Treasury exposes a definitive export shape (canonical column names, encodings, or API payload), add a first-class importer that maps that format to `{ image, VerifyRequest }` per row — without agents hand-maintaining `manifest.csv` column aliases. Might include server-side ZIP ingest to avoid loading hundreds of megabytes into the browser tab.

2. **COLA integration + optional assisted parsing.** Marcus de-scoped direct COLA .NET/API access for this exercise (`ROADMAP.md`). A production path pulls application metadata and label attachments via read-only integration, then feeds the existing verify pipeline — still **extract → deterministic compare**, not LLM judging compliance. Optionally, where no machine-readable bundle exists, explore **assistive** PDF or form-image parsing (human-confirmed fields); that introduces non-determinism and heavier compliance review compared to manifests or API-sourced fields.

---

## Testing

```bash
make test                  # full suite (~194 collected; LLM-gated cases skipped by default)
make ci-cov-comparators    # comparators ≥95% line coverage gate
make ci-cov-verdict        # app.verdict via test_smoke verdict cases, ≥90% gate
make ci-cov-api            # api/ + contract/ + adversarial/ ≥80% gate
make eval                  # mocked eval harness (pipeline wiring)
RUN_LLM_TESTS=1 make eval-real    # eval against real OpenAI (burns tokens)
make regenerate-fixtures   # rebuild test labels from generate_fixtures.py
```

**Test inventory:**
- `tests/test_smoke.py` — foundation imports, canonical warning sanity, FR-017 precedence, `compute_overall_verdict` unit cases.
- `tests/comparators/` — unit tests (rapidfuzz / volume / warning), includes adversarial cases (smart quotes, title-case prefix, malformed numerics).
- `tests/api/` — FastAPI TestClient + mocked OpenAI client; covers FR-001/002/007/012/013/014/015/017 plus security headers, rate limiting, path traversal on static SPA, batch audit.
- `tests/contract/` — response-shape stability + `error.code` enum lock (silent vocabulary expansion fails the test).
- `tests/adversarial/` — prompt-injection-in-image, smart-apostrophe brand match.
- `tests/performance/` — NFR-001 mocked synthetic-latency gate (≤ 5000 ms).
- `tests/eval/` — fixture YAML integrity + (optional) real-LLM pipeline check when `RUN_LLM_TESTS=1`.
- `tests/llm/` — opt-in real-OpenAI smoke.

---

## Local development

```bash
# Backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # add your OPENAI_API_KEY
uvicorn app.api.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
# Vite dev server proxies API calls to localhost:8000
```

Visit http://localhost:5173 — the queue is the default screen.

---

## Repository layout

```
ttb-label-verifier/
├── app/                                  # Python backend
│   ├── api/
│   │   ├── main.py                       # FastAPI app, middleware, /health, static frontend mount
│   │   ├── routes.py                     # POST /verify, POST /verify/batch (SSE)
│   │   ├── deps.py                       # OpenAI client DI
│   │   └── security.py                   # secure-headers middleware
│   ├── audit/
│   │   └── jsonl_logger.py               # append-only audit log
│   ├── comparators/                      # deterministic field comparison
│   │   ├── text_match.py                 # brand fuzzy + class/type substring
│   │   ├── numeric_match.py              # ABV ±0.1 %
│   │   ├── volume_match.py               # mL/L/fl-oz with ≤1 mL tolerance
│   │   └── warning_match.py              # text + caps + bold (3 results)
│   ├── constants/
│   │   └── ttb_warning.py                # canonical 27 CFR §16.21 text
│   ├── extraction/
│   │   ├── openai_vision.py              # AsyncOpenAI + structured outputs
│   │   └── prompts.py                    # SYSTEM_PROMPT + PROMPT_VERSION
│   ├── schemas/
│   │   ├── api.py                        # VerifyRequest/Response, Verdict, ErrorCode
│   │   └── extraction.py                 # LabelExtraction, FieldConfidence
│   └── verdict.py                        # overall-verdict precedence + FR-017 gate
├── frontend/                             # React + Vite + TS
│   ├── src/
│   │   ├── components/
│   │   │   ├── ApplicationQueue.tsx      # mock COLA queue (default screen)
│   │   │   ├── SingleLabelForm.tsx       # manual + queue-prefilled form
│   │   │   ├── BatchUpload.tsx           # ZIP + manifest.csv → SSE batch
│   │   │   └── ResultCard.tsx            # per-field verdict pill
│   │   ├── utils/batchManifest.ts        # ZIP + manifest.csv → per-row payloads
│   │   ├── data/mockApplications.ts      # 3 fake COLA records
│   │   ├── api/
│   │   │   ├── client.ts                 # multipart + SSE-over-POST
│   │   │   └── types.ts                  # mirrors backend Pydantic models
│   │   ├── App.tsx                       # 3-tab shell
│   │   ├── main.tsx                      # React entry
│   │   └── styles.css                    # hand-rolled, no Tailwind
│   └── public/sample-labels/             # PNGs the queue references
├── samples/                              # docs-only examples (not used at runtime)
│   └── example-manifest.csv             # CSV template for ZIP batches
├── tests/
│   ├── comparators/                      # 78 unit tests
│   ├── api/                              # 30 integration tests (mocked OpenAI)
│   ├── contract/                         # response-shape + error-code-stability
│   ├── adversarial/                      # prompt-injection, smart-apostrophe
│   ├── performance/                      # NFR-001 latency gate
│   ├── eval/                             # pipeline-vs-fixtures (LLM-gated)
│   ├── fixtures/labels/                  # 3 PNGs + .expected.yaml + generator
│   └── conftest.py                       # FakeOpenAIClient, make_extraction, tiny_png
├── Dockerfile                            # multi-stage Node + Python build
├── railway.toml                          # single-service Railway config
├── Makefile                              # test / coverage / eval / regen targets
└── pyproject.toml                        # backend deps, ruff, pytest config
```

---

## License

MIT — see `LICENSE`.

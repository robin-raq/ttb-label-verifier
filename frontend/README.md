# TTB Label Verifier — Frontend

React 18 + TypeScript + Vite single-page app for the TTB label verification prototype.

## Dev setup

```bash
cp .env.example .env   # set VITE_API_URL if backend isn't on localhost:8000
npm install
npm run dev            # http://localhost:5173
```

The Vite dev server proxies `/verify` to `VITE_API_URL` so you don't need CORS config locally.

## Build

```bash
npm run build          # output → dist/
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Backend base URL (no trailing slash) |

## Architecture notes

- **No router** — two screens (Single / Batch) switched by simple React state.
- **SSE for batch** — uses `@microsoft/fetch-event-source` so we can POST with a JSON body (native `EventSource` is GET-only).
- **XSS hardening** — all API-supplied text (attacker-controllable via image content) is sanitized with `dompurify` before rendering. JSX interpolation only — no `innerHTML`.
- **No Tailwind / MUI** — plain CSS in `src/styles.css`. Keeps bundle tiny.

## Local dev CSP note

In local dev, Vite injects HMR scripts inline. Production deployments (Railway static host) serve the pre-built `dist/` which requires no `unsafe-inline` in CSP — this matches FR-015.

## Limitations

- Batch mode applies the same form values to every image (MVP). Per-row CSV override is in `ROADMAP.md`.
- No authentication — open-access prototype per spec.

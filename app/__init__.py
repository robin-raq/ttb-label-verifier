"""Top-level package init.

Loads `.env` from the repo root *before any submodule is imported*, so that
module-level `os.environ.get(...)` reads (e.g. ``MODEL_NAME`` in
``app.api.routes``, ``OPENAI_API_KEY`` in ``app.api.deps``) resolve from the
file when the host shell doesn't export them. Production deploys (Railway,
Azure App Service) inject env vars directly — ``override=False`` keeps any
shell-set value authoritative over what's in ``.env``.

Putting this here (rather than in ``app/api/main.py``) means the env is
loaded the same way regardless of *which* app entry point is invoked —
uvicorn, pytest, the standalone fixture generator, the COLA-fetcher script,
etc. all see the same configuration.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

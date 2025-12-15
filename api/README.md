# API Service

FastAPI backend for ingestion, normalization, and model delivery.

- Entry: `app/main.py` (uvicorn target).
- Keep routes thin; move logic into `app/services/` and `app/models/`.
- Tests live in `api/tests/` mirroring package paths.

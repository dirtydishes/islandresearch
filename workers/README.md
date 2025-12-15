# Workers

Background jobs for ingestion, parsing, and model updates.

- Jobs go in `workers/jobs/`; queue and scheduler config in `workers/queue.py` (to be added).
- Workers should be idempotent and safe to retry; persist provenance of transformations.

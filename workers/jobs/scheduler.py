import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from .backfill_all import backfill_all
from .backfill_recent import backfill_recent

logger = logging.getLogger(__name__)

DAY_MAP = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
    "SUN": 6,
}


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_time(value: str) -> Tuple[int, int]:
    parts = [part.strip() for part in value.split(":")]
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Time out of range: {value!r}")
    return hour, minute


def _parse_weekday(value: str) -> int:
    raw = value.strip().upper()
    if raw.isdigit():
        day = int(raw)
        if 0 <= day <= 6:
            return day
    key = raw[:3]
    if key in DAY_MAP:
        return DAY_MAP[key]
    raise ValueError(f"Invalid weekday: {value!r}")


def _parse_tickers(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    parsed = [t.strip() for t in value.split(",") if t.strip()]
    return parsed or None


def _next_daily_run(now: datetime, hour: int, minute: int) -> datetime:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _next_weekly_run(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - now.weekday()) % 7
    target += timedelta(days=days_ahead)
    if target <= now:
        target += timedelta(days=7)
    return target


def _run_nightly(limit: int, tickers: Optional[List[str]]) -> None:
    logger.info("Starting nightly incremental backfill (limit=%d).", limit)
    result = backfill_recent(limit=limit, tickers=tickers, strict_ties=False)
    logger.info(
        "Nightly backfill complete: %d success, %d failed.",
        result.get("success"),
        result.get("failed"),
    )


def _run_weekly(limit: int) -> None:
    logger.info("Starting weekly full backfill (limit=%d).", limit)
    result = backfill_all(limit=limit, strict_ties=True)
    logger.info(
        "Weekly backfill complete: %d success, %d failed.",
        result.get("success"),
        result.get("failed"),
    )


def _main() -> None:
    log_level = os.getenv("SCHEDULER_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    nightly_enabled = _env_bool("BACKFILL_NIGHTLY_ENABLED", True)
    weekly_enabled = _env_bool("BACKFILL_WEEKLY_ENABLED", True)
    if not nightly_enabled and not weekly_enabled:
        logger.warning("Scheduler disabled; no backfill tasks will run.")
        return

    nightly_time = os.getenv("BACKFILL_NIGHTLY_TIME_UTC", "02:00")
    weekly_day = os.getenv("BACKFILL_WEEKLY_DAY", "SUN")
    weekly_time = os.getenv("BACKFILL_WEEKLY_TIME_UTC", "03:00")
    nightly_limit = int(os.getenv("BACKFILL_NIGHTLY_LIMIT", "4"))
    weekly_limit = int(os.getenv("BACKFILL_WEEKLY_LIMIT", "8"))
    nightly_tickers = _parse_tickers(os.getenv("BACKFILL_NIGHTLY_TICKERS"))

    nightly_hour, nightly_minute = _parse_time(nightly_time)
    weekly_hour, weekly_minute = _parse_time(weekly_time)
    weekly_weekday = _parse_weekday(weekly_day)

    now = datetime.now(timezone.utc)
    next_nightly = (
        _next_daily_run(now, nightly_hour, nightly_minute) if nightly_enabled else None
    )
    next_weekly = (
        _next_weekly_run(now, weekly_weekday, weekly_hour, weekly_minute) if weekly_enabled else None
    )

    if next_nightly:
        logger.info("Next nightly backfill scheduled for %s UTC.", next_nightly.isoformat())
    if next_weekly:
        logger.info("Next weekly backfill scheduled for %s UTC.", next_weekly.isoformat())

    while True:
        now = datetime.now(timezone.utc)
        if next_nightly and now >= next_nightly:
            try:
                _run_nightly(nightly_limit, nightly_tickers)
            except Exception as exc:  # pragma: no cover - runtime safety
                logger.exception("Nightly backfill failed: %s", exc)
            next_nightly = _next_daily_run(datetime.now(timezone.utc), nightly_hour, nightly_minute)
            logger.info("Next nightly backfill scheduled for %s UTC.", next_nightly.isoformat())

        if next_weekly and now >= next_weekly:
            try:
                _run_weekly(weekly_limit)
            except Exception as exc:  # pragma: no cover - runtime safety
                logger.exception("Weekly backfill failed: %s", exc)
            next_weekly = _next_weekly_run(datetime.now(timezone.utc), weekly_weekday, weekly_hour, weekly_minute)
            logger.info("Next weekly backfill scheduled for %s UTC.", next_weekly.isoformat())

        next_runs = [run for run in [next_nightly, next_weekly] if run is not None]
        if not next_runs:
            logger.warning("No scheduled tasks; scheduler exiting.")
            return
        sleep_seconds = (min(next_runs) - datetime.now(timezone.utc)).total_seconds()
        time.sleep(max(1, int(sleep_seconds)))


if __name__ == "__main__":
    _main()

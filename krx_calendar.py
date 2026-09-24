"""Small deterministic KRX trading-calendar helpers for static snapshots."""

from __future__ import annotations

from datetime import date, timedelta


# KRX closes on government holidays, May 1, and the final weekday of the year.
# Keep this explicit list synchronized with the annual KRX/KASI calendar notice.
KRX_HOLIDAYS = frozenset({
    date(2026, 1, 1),
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
    date(2026, 3, 2),
    date(2026, 5, 1), date(2026, 5, 5), date(2026, 5, 25),
    date(2026, 6, 3),
    date(2026, 8, 17),
    date(2026, 9, 24), date(2026, 9, 25),
    date(2026, 10, 5), date(2026, 10, 9),
    date(2026, 12, 25), date(2026, 12, 31),
})


def is_krx_trading_day(day: date) -> bool:
    """Return whether KRX is expected to hold a regular session on ``day``."""
    return day.weekday() < 5 and day not in KRX_HOLIDAYS


def future_trading_period(base_date: str, trading_days: int) -> dict:
    """Return the next inclusive KRX session range after an ISO close date."""
    count = int(trading_days)
    if count <= 0:
        raise ValueError("trading_days must be positive")

    cursor = date.fromisoformat(str(base_date)[:10]) + timedelta(days=1)
    sessions = []
    while len(sessions) < count:
        if is_krx_trading_day(cursor):
            sessions.append(cursor)
        cursor += timedelta(days=1)

    return {
        "periodStart": sessions[0].isoformat(),
        "periodEnd": sessions[-1].isoformat(),
        "tradingDays": count,
    }

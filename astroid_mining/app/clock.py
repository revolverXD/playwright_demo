"""One source of time for the service: the host system clock, in UTC.

Nothing here is a simulation clock — the fleet lives in real time. Timestamps carry milliseconds and
end in `Z`, which keeps SQLite text comparisons (`expires_at > now`) valid. Rows written before
milliseconds existed can sort apart from newer ones by under a second, inside the same second.
"""

import time
from datetime import datetime, timedelta, timezone

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"  # milliseconds: a 1 s OSPF dead interval needs them
STARTED_AT = datetime.now(timezone.utc)
_MONOTONIC_ORIGIN = time.monotonic()


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(at: datetime | None = None) -> str:
    return (at or now()).strftime(TIMESTAMP_FORMAT)[:-3] + "Z"


def iso_in(seconds: int) -> str:
    return iso(now() + timedelta(seconds=seconds))


def parse(stamp: str | None) -> datetime | None:
    """Read a timestamp this module (or an older build) wrote. None if it is unreadable."""
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def age_of(stamp: str | None) -> float | None:
    """Seconds since `stamp`; None when there is nothing to compare against."""
    moment = parse(stamp)
    return (now() - moment).total_seconds() if moment else None


def uptime_s() -> float:
    """Monotonic, so a jump in the system clock cannot make the service look negative."""
    return round(time.monotonic() - _MONOTONIC_ORIGIN, 1)

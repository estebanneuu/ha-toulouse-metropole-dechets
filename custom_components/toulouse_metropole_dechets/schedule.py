"""Strict, Home Assistant independent collection schedule calculations.

Explicit exclusions and the optional official annual closures affect holidays.
No postponed collection is inferred from a weekday rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

_WEEKDAYS = (
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)
_DAY_PATTERN = "(?:" + "|".join(_WEEKDAYS) + ")"
_RULE_PATTERN = re.compile(
    rf"(?:le )?(?P<days>{_DAY_PATTERN}(?:, ?{_DAY_PATTERN})*"
    rf"(?: et {_DAY_PATTERN})?)(?: semaine (?P<parity>impaire|paire))?"
)
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


@dataclass(frozen=True)
class Rule:
    """Weekdays use Monday=0; parity is ISO week modulo two, or every week."""

    weekdays: tuple[int, ...]
    parity: int | None = None

    def __post_init__(self) -> None:
        """Reject invalid rules before iterating over a calendar."""
        if not self.weekdays or any(day not in range(7) for day in self.weekdays):
            raise ValueError("Une règle doit contenir des jours de 0 à 6")
        if self.parity not in (None, 0, 1):
            raise ValueError("La parité doit être 0, 1 ou None")


def parse_rule(text: str) -> Rule:
    """Parse supported official descriptions; reject ambiguous road sides.

    Matching the complete string avoids silently interpreting an advisory text
    or two different sides of a road as one collection schedule.
    """
    normalized = " ".join(text.casefold().split())
    if re.fullmatch(r"7 jours\s*/\s*7", normalized):
        return Rule(tuple(range(7)))
    match = _RULE_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(f"Règle de collecte inconnue ou ambiguë : {text!r}")
    day_names = re.findall(_DAY_PATTERN, match["days"])
    weekdays = tuple(sorted({_WEEKDAYS.index(day) for day in day_names}))
    parity_text = match["parity"]
    parity = None if parity_text is None else int(parity_text == "impaire")
    return Rule(weekdays, parity)


def dates_between(
    rule: Rule,
    start: date,
    end: date,
    excluded: set[date] | None = None,
) -> list[date]:
    """Return collection dates in the half-open range [start, end)."""
    excluded = excluded or set()
    dates: list[date] = []
    day = start
    while day < end:
        if (
            day.weekday() in rule.weekdays
            and (rule.parity is None or day.isocalendar().week % 2 == rule.parity)
            and day not in excluded
        ):
            dates.append(day)
        day += timedelta(days=1)
    return dates


def parse_dates(text: str) -> list[date]:
    """Read comma/newline separated ISO dates, sorted and deduplicated.

    Blank lines are accepted. Empty comma-separated entries and non ISO dates
    are rejected, including dates that Python accepts in compact ISO format.
    """
    dates: set[date] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        for value in line.split(","):
            value = value.strip()
            if _DATE_PATTERN.fullmatch(value) is None:
                raise ValueError(f"Date attendue au format AAAA-MM-JJ : {value!r}")
            dates.add(date.fromisoformat(value))
    return sorted(dates)


def schedule_dates(config: dict[str, Any], start: date, end: date) -> list[date]:
    """Calculate an explicit/manual or recurring schedule.

    Exclusions take precedence over extra dates. Drop-off, appointment-only and
    unavailable modes deliberately produce no invented collection dates.
    """
    mode = config.get("mode", "unavailable")
    if mode in ("drop_off", "appointment", "unavailable"):
        return []
    if mode not in ("manual", "recurring"):
        raise ValueError(f"Mode de collecte inconnu : {mode!r}")
    excluded = set(parse_dates(config.get("excluded_dates", "")))
    if mode == "manual":
        base = {
            day for day in parse_dates(config.get("dates", "")) if start <= day < end
        }
    else:
        rule = parse_rule(config["rule"])
        closures = set()
        if config.get("exclude_public_shutdowns", False):
            # OM and tri official closures: https://metropole.toulouse.fr/communes/toulouse
            # Extra dates represent explicit confirmations and can override these.
            closures = {
                date(year, month, day)
                for year in range(start.year, end.year + 1)
                for month, day in ((1, 1), (5, 1), (12, 25))
            }
        base = set(dates_between(rule, start, end, excluded | closures))
    extra = {
        day for day in parse_dates(config.get("extra_dates", "")) if start <= day < end
    }
    return sorted((base | extra) - excluded)

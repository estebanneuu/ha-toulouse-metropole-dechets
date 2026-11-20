"""Calendar edge cases without requiring a running Home Assistant instance."""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "toulouse_metropole_dechets"
    / "schedule.py"
)
_SPEC = importlib.util.spec_from_file_location("toulouse_schedule_test", _MODULE_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
Rule = _MODULE.Rule
parse_rule = _MODULE.parse_rule
parse_dates = _MODULE.parse_dates
dates_between = _MODULE.dates_between
schedule_dates = _MODULE.schedule_dates


@pytest.mark.parametrize(
    ("text", "weekdays", "parity"),
    [
        ("7 jours / 7", tuple(range(7)), None),
        ("Jeudi", (3,), None),
        ("Le lundi et jeudi", (0, 3), None),
        ("Le lundi, mercredi et vendredi", (0, 2, 4), None),
        ("Le mardi et vendredi", (1, 4), None),
        ("Jeudi semaine impaire", (3,), 1),
        ("Jeudi semaine paire", (3,), 0),
        ("  MERCREDI  semaine  paire\n", (2,), 0),
    ],
)
def test_supported_official_descriptions(text, weekdays, parity):
    assert parse_rule(text) == Rule(weekdays, parity)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Lundi d’un côté de la voie ; Mardi de l’autre",
        "Lundi d'un côté de la voie ; Lundi de l'autre",
        "Pour plus d’informations : contacter Toulouse Métropole",
        "Mardi sauf jours fériés",
        "Mardi ou jeudi",
        "Mercredi une semaine sur deux",
        "Le lundi et jeudi semaine impaire ou paire",
    ],
)
def test_unsupported_or_ambiguous_descriptions_are_rejected(text):
    with pytest.raises(ValueError):
        parse_rule(text)


def test_iso_week_53_and_week_1_are_both_odd():
    rule = parse_rule("Vendredi semaine impaire")
    assert dates_between(rule, date(2020, 12, 28), date(2021, 1, 16)) == [
        date(2021, 1, 1),
        date(2021, 1, 8),
    ]


def test_iso_week_two_is_even():
    rule = parse_rule("Vendredi semaine paire")
    assert dates_between(rule, date(2020, 12, 28), date(2021, 1, 16)) == [
        date(2021, 1, 15)
    ]


def test_range_is_half_open_and_holidays_are_not_assumed():
    rule = parse_rule("Vendredi")
    assert dates_between(rule, date(2026, 12, 25), date(2027, 1, 1)) == [
        date(2026, 12, 25)
    ]
    assert dates_between(rule, date(2026, 12, 25), date(2026, 12, 25)) == []


def test_explicit_exclusion_does_not_invent_a_postponement():
    rule = parse_rule("7 jours / 7")
    assert dates_between(
        rule,
        date(2026, 12, 24),
        date(2026, 12, 27),
        {date(2026, 12, 25)},
    ) == [date(2026, 12, 24), date(2026, 12, 26)]


def test_parse_dates_sorts_deduplicates_and_accepts_crlf():
    assert parse_dates("2026-12-25, 2026-01-01\r\n\n2026-12-25\n") == [
        date(2026, 1, 1),
        date(2026, 12, 25),
    ]
    assert parse_dates("\n \n") == []


@pytest.mark.parametrize(
    "value",
    [
        "2026-2-01",
        "20260201",
        "01/02/2026",
        "2026-02-29",
        "2026-13-01",
        "2026-01-01T00:00:00",
        "2026-01-01,,2026-02-01",
        "2026-01-01;2026-02-01",
        "demain",
    ],
)
def test_invalid_date_lists_are_rejected(value):
    with pytest.raises(ValueError):
        parse_dates(value)


def test_recurring_exceptions_and_additions_are_bounded_and_exclusion_wins():
    config = {
        "mode": "recurring",
        "rule": "Vendredi",
        "excluded_dates": "2026-12-25",
        "extra_dates": "2026-12-26,2026-12-25,2027-01-02,2026-12-01",
    }
    assert schedule_dates(config, date(2026, 12, 24), date(2027, 1, 2)) == [
        date(2026, 12, 26),
        date(2027, 1, 1),
    ]


def test_manual_dates_apply_half_open_range():
    config = {"mode": "manual", "dates": "2026-11-20,2026-11-21,2026-11-22"}
    assert schedule_dates(config, date(2026, 11, 21), date(2026, 11, 22)) == [
        date(2026, 11, 21)
    ]


@pytest.mark.parametrize("mode", ["drop_off", "appointment", "unavailable"])
def test_non_scheduled_modes_do_not_produce_collection_dates(mode):
    assert schedule_dates({"mode": mode}, date(2026, 1, 1), date(2027, 1, 1)) == []


def test_unknown_mode_is_not_silently_ignored():
    with pytest.raises(ValueError):
        schedule_dates({"mode": "surprise"}, date(2026, 1, 1), date(2027, 1, 1))


def test_official_shutdowns_across_years_keep_other_holidays():
    config = {
        "mode": "recurring",
        "rule": "7 jours / 7",
        "exclude_public_shutdowns": True,
    }
    dates = schedule_dates(config, date(2026, 1, 1), date(2028, 1, 2))
    for year in (2026, 2027):
        assert date(year, 1, 1) not in dates
        assert date(year, 5, 1) not in dates
        assert date(year, 12, 25) not in dates
        assert date(year, 7, 14) in dates
        assert date(year, 11, 11) in dates
    assert date(2028, 1, 1) not in dates


def test_confirmed_extra_can_override_official_shutdown_but_not_explicit_exclusion():
    config = {
        "mode": "recurring",
        "rule": "7 jours / 7",
        "exclude_public_shutdowns": True,
        "extra_dates": "2026-12-25,2027-01-01",
        "excluded_dates": "2027-01-01",
    }
    dates = schedule_dates(config, date(2026, 12, 24), date(2027, 1, 2))
    assert date(2026, 12, 25) in dates
    assert date(2027, 1, 1) not in dates


def test_manual_dates_use_exceptions_and_ignore_automatic_shutdowns():
    config = {
        "mode": "manual",
        "dates": "2026-12-24,2026-12-25",
        "extra_dates": "2026-12-26,2026-12-27",
        "excluded_dates": "2026-12-24,2026-12-27",
        "exclude_public_shutdowns": True,
    }
    assert schedule_dates(config, date(2026, 12, 24), date(2026, 12, 28)) == [
        date(2026, 12, 25),
        date(2026, 12, 26),
    ]

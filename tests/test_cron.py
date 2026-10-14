import datetime as dt

import pytest

from urh.cron import Cron


def ts(*a):
    return dt.datetime(*a, tzinfo=dt.UTC).timestamp()


def at(t):
    return dt.datetime.fromtimestamp(t, dt.UTC).strftime("%Y-%m-%d %H:%M %a")


def test_next_after_basic_fields():
    assert at(Cron.parse("*/15 * * * *").next_after(ts(2026, 10, 14, 1, 7))) == "2026-10-14 01:15 Wed"
    assert at(Cron.parse("0 9 * * 1-5").next_after(ts(2026, 10, 16, 9, 0))) == "2026-10-19 09:00 Mon"
    assert at(Cron.parse("@monthly").next_after(ts(2026, 12, 31, 23, 59))) == "2027-01-01 00:00 Fri"
    assert at(Cron.parse("0 0 29 2 *").next_after(ts(2026, 3, 1))) == "2028-02-29 00:00 Tue"


def test_strictly_after_and_sunday_as_seven():
    c = Cron.parse("30 12 * * 7")
    assert at(c.next_after(ts(2026, 10, 18, 12, 30))) == "2026-10-25 12:30 Sun"
    assert at(c.next_after(ts(2026, 10, 18, 12, 29, 59))) == "2026-10-18 12:30 Sun"


def test_both_day_fields_restricted_means_either():
    c = Cron.parse("0 0 1 * 1")  # the 1st of the month OR any Monday
    assert at(c.next_after(ts(2026, 10, 14))) == "2026-10-19 00:00 Mon"
    assert at(c.next_after(ts(2026, 10, 27))) == "2026-11-01 00:00 Sun"


@pytest.mark.parametrize("bad", ["* * * *", "60 * * * *", "*/0 * * * *", "5-1 * * * *", "0 0 31 2 *"])
def test_rejects_bad_or_impossible_expressions(bad):
    with pytest.raises(ValueError):
        Cron.parse(bad).next_after(ts(2026, 1, 1))

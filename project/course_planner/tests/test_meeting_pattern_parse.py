"""Meeting pattern parsing: Thursday tokens and multi-hyphen time ranges."""

from utils.meeting_pattern_parse import parse_schedule


def test_classic_space_separated():
    out = parse_schedule("M W F | 11:45 AM - 12:50 PM")
    assert out is not None
    assert out["days"] == ["M", "W", "F"]
    assert out["start"] == "11:45 AM"
    assert out["end"] == "12:50 PM"


def test_r_is_thursday_with_tuesday():
    out = parse_schedule("T R | 10:00 AM - 11:00 AM")
    assert out is not None
    assert out["days"] == ["T", "R"]


def test_contiguous_days_tth():
    out = parse_schedule("MTThF | 1:00 PM - 2:00 PM")
    assert out is not None
    assert out["days"] == ["M", "T", "Th", "F"]


def test_double_hyphen_between_times():
    out = parse_schedule("MWF|9:00 AM--10:15 AM")
    assert out is not None
    assert out["start"] == "9:00 AM"
    assert out["end"] == "10:15 AM"


def test_extra_hyphen_segments_use_first_and_last_clock_times():
    out = parse_schedule("M W F | 10:00 AM - 11:15 AM - reserved - 12:00 PM")
    assert out is not None
    assert out["start"] == "10:00 AM"
    assert out["end"] == "12:00 PM"


def test_compact_times_no_space_before_am():
    out = parse_schedule("TR|9:00am-10:15am")
    assert out is not None
    assert out["days"] == ["T", "R"]
    assert "9:00" in out["start"] and "am" in out["start"].lower()
    assert "10:15" in out["end"]


def test_missing_bar_returns_none():
    assert parse_schedule("M W F 11-12") is None

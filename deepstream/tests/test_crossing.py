"""Unit tests for pure line-crossing logic. Uses synthetic coordinates (labelled fixtures),
which validate the algorithm only - NOT the DeepStream runtime."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from vds.crossing import AttributeBook, Line, LineCrossingDetector, UNTRACKED_ID  # noqa: E402

HLINE = Line(0, 100, 200, 100)  # horizontal; y>100 is the "left" (+) side in image coords? see below


def det(**kw):
    return LineCrossingDetector(HLINE, margin=2, **kw)


def run(d, tid, ys, x=100):
    return [d.update(tid, x, y, i) for i, y in enumerate(ys)]


def test_direction_is_consistent_and_opposite():
    a = run(det(), 1, [50, 80, 99, 110, 150])
    b = run(det(), 1, [150, 110, 101, 90, 50])
    da = [e for e in a if e]
    db = [e for e in b if e]
    assert len(da) == 1 and len(db) == 1
    assert {da[0], db[0]} == {"in", "out"}


def test_single_event_for_many_frames_after_crossing():
    d = det()
    events = run(d, 7, [50, 90, 110] + [120 + i for i in range(100)])
    assert sum(1 for e in events if e) == 1


def test_jitter_inside_dead_band_does_not_count():
    d = det()
    events = run(d, 3, [90, 99, 101, 99, 100.5, 99.2, 90])
    assert not any(events)


def test_jitter_across_band_edges_counts_once_per_direction():
    d = det()
    ys = [90, 110, 90, 110, 90, 110]  # large oscillation: in/out/in/out...
    events = [e for e in run(d, 3, ys) if e]
    assert len(events) == 2 and events[0] != events[1]  # one of each direction, never repeated


def test_untracked_objects_ignored():
    d = det()
    assert d.update(UNTRACKED_ID, 100, 50, 0) is None
    assert d.update(UNTRACKED_ID, 100, 150, 1) is None
    assert len(d) == 0


def test_independent_tracks():
    d = det()
    e1 = run(d, 1, [50, 150])
    e2 = run(d, 2, [150, 50])
    assert e1[-1] and e2[-1] and e1[-1] != e2[-1]


def test_first_observation_across_line_not_counted():
    d = det()
    assert run(d, 9, [150, 160, 170]) == [None, None, None]


def test_crossing_outside_segment_not_counted():
    d = det()
    assert d.update(1, 500, 50, 0) is None
    assert d.update(1, 500, 150, 1) is None  # x=500 is beyond the 0..200 segment


def test_occlusion_gap_still_counts_once():
    d = det()
    assert d.update(1, 100, 60, 0) is None
    assert d.update(1, 100, 140, 20) in ("in", "out")  # 20 frames missing
    assert d.update(1, 100, 150, 21) is None


def test_stale_track_eviction_bounds_memory():
    d = LineCrossingDetector(HLINE, ttl_frames=10)
    for t in range(100):
        d.update(t, 100, 50, 0)
    assert len(d) == 100
    assert d.evict_stale(50) == 100 and len(d) == 0


def test_zero_length_line_rejected():
    with pytest.raises(ValueError):
        Line(1, 1, 1, 1).signed_distance(0, 0)


def test_attribute_book_keeps_most_confident():
    b = AttributeBook()
    b.observe_color(1, "red", 0.6)
    b.observe_color(1, "blue", 0.4)
    b.observe_color(1, None, 0.99)
    assert b.color(1) == ("red", 0.6)
    b.observe_color(1, "maroon", 0.9)
    assert b.color(1) == ("maroon", 0.9)
    assert b.color(2) == (None, None)


def test_independent_counting_lines():
    line_a = Line(0, 100, 200, 100, "lane-a")
    line_b = Line(0, 200, 200, 200, "lane-b")
    a = LineCrossingDetector(line_a, margin=2)
    b = LineCrossingDetector(line_b, margin=2)

    # Track starts above both lines, then crosses line A.
    assert a.update(42, 100, 50, 0) is None
    assert b.update(42, 100, 50, 0) is None
    event_a = a.update(42, 100, 120, 1)
    assert event_a in ("in", "out")
    assert b.update(42, 100, 120, 1) is None

    # The same track later crosses line B; its state is independent.
    event_b = b.update(42, 100, 220, 2)
    assert event_b in ("in", "out")
    assert len(a) == 1
    assert len(b) == 1

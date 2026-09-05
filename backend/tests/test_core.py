from app.services.geometry import point_in_rect, segment_line_intersection, signed_line_distance
from app.services.runtime import RuntimeConfig


def test_segment_crosses_finite_line():
    crossing = segment_line_intersection((5.0, 0.0), (5.0, 10.0), ((0, 5), (10, 5)))
    assert crossing == (5.0, 5.0)


def test_crossing_outside_line_segment_is_rejected():
    crossing = segment_line_intersection((20.0, 0.0), (20.0, 10.0), ((0, 5), (10, 5)))
    assert crossing is None


def test_point_in_gate():
    assert point_in_rect((12.0, 15.0), (10, 10, 20, 20))
    assert not point_in_rect((40.0, 15.0), (10, 10, 20, 20))


def test_signed_line_distance_changes_side():
    line = ((0, 5), (10, 5))
    assert signed_line_distance((5, 0), line) > 0
    assert signed_line_distance((5, 10), line) < 0


def test_config_accepts_frontend_percentages():
    config = RuntimeConfig()
    config.update_from_dict({"area_tolerance": 50, "threshold_fraction": 55})
    assert config.area_tolerance == 0.50
    assert config.threshold_fraction == 0.55
    assert config.frontend_dict()["area_tolerance"] == 50
    assert config.frontend_dict()["threshold_fraction"] == 55

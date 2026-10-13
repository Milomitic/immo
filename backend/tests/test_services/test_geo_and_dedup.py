import pytest

from app.services.dedup_service import compute_similarity, haversine
from app.services.listing_service import parse_polygon, point_in_polygon, polygon_bbox

# A square around central Bari, and an L-shaped (concave) polygon.
SQUARE = [(41.10, 16.85), (41.10, 16.90), (41.14, 16.90), (41.14, 16.85)]
L_SHAPE = [(0, 0), (0, 2), (1, 2), (1, 1), (2, 1), (2, 0)]


class TestParsePolygon:
    def test_valid(self):
        assert parse_polygon("41.1,16.85;41.1,16.9;41.14,16.9") == [
            (41.1, 16.85), (41.1, 16.9), (41.14, 16.9),
        ]

    def test_tolerates_trailing_separator(self):
        assert len(parse_polygon("1,1;1,2;2,2;")) == 3

    @pytest.mark.parametrize("raw", [None, "", "1,1;2,2", "a,b;c,d;e,f", "1;2;3"])
    def test_invalid_or_too_short(self, raw):
        assert parse_polygon(raw) is None


def test_polygon_bbox():
    assert polygon_bbox(SQUARE) == (41.10, 16.85, 41.14, 16.90)


class TestPointInPolygon:
    def test_inside_square(self):
        assert point_in_polygon(41.12, 16.87, SQUARE)

    def test_outside_square(self):
        assert not point_in_polygon(41.20, 16.87, SQUARE)

    def test_concave_notch_is_outside(self):
        # (1.5, 1.5) is inside the L's bounding box but in the cut-out corner.
        assert not point_in_polygon(1.5, 1.5, L_SHAPE)

    def test_concave_arm_is_inside(self):
        assert point_in_polygon(0.5, 1.5, L_SHAPE)
        assert point_in_polygon(1.5, 0.5, L_SHAPE)


def test_haversine_known_distance():
    # Bari → Molfetta is ~25 km as the crow flies.
    d = haversine(41.1171, 16.8719, 41.2007, 16.5978)
    assert 23_000 < d < 27_000


class TestComputeSimilarity:
    BASE = ("via roma 10 bari", 200000, 80, 3, 41.12, 16.87)

    def test_identical_listing_scores_one(self):
        assert compute_similarity(*self.BASE, *self.BASE) == pytest.approx(1.0)

    def test_different_listing_scores_low(self):
        other = ("corso cavour 99 bari", 450000, 160, 6, 41.13, 16.89)
        assert compute_similarity(*self.BASE, *other) < 0.5

    def test_no_comparable_fields_scores_zero(self):
        empty = (None, None, None, None, None, None)
        assert compute_similarity(*empty, *empty) == 0.0

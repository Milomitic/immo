from datetime import datetime, timedelta, timezone

import pytest

from scraper.utils.html_extract import (
    clamp_italy_coords,
    clamp_publication_date,
    map_property_type,
    parse_float_text,
    parse_int,
    parse_italian_date,
)


class TestClampItalyCoords:
    def test_in_bounds_passes_through(self):
        assert clamp_italy_coords(41.12, 16.87) == (41.12, 16.87)

    def test_swapped_pair_is_recovered(self):
        # Some agency JSON-LD has latitude/longitude flipped.
        assert clamp_italy_coords(16.87, 41.12) == (41.12, 16.87)

    def test_out_of_italy_is_dropped(self):
        assert clamp_italy_coords(55.75, 37.62) == (None, None)  # Moscow

    def test_zero_zero_is_dropped(self):
        assert clamp_italy_coords(0, 0) == (None, None)

    def test_string_inputs_are_coerced(self):
        assert clamp_italy_coords("41.12", "16.87") == (41.12, 16.87)

    def test_garbage_is_dropped(self):
        assert clamp_italy_coords("abc", 16.87) == (None, None)

    def test_missing_values_pass_through_as_none(self):
        assert clamp_italy_coords(None, None) == (None, None)


class TestClampPublicationDate:
    def test_past_date_unchanged(self):
        assert clamp_publication_date("2024-05-15") == "2024-05-15"

    def test_iso_datetime_reduced_to_date(self):
        assert clamp_publication_date("2024-05-15T10:00:00Z") == "2024-05-15"

    # The function reasons in UTC; using local date.today() here would make
    # these tests fail between midnight and 02:00 Italian time.
    def test_near_future_clamped_to_today(self):
        today = datetime.now(timezone.utc).date()
        tomorrow = (today + timedelta(days=1)).isoformat()
        assert clamp_publication_date(tomorrow) == today.isoformat()

    def test_far_future_rejected(self):
        far = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
        assert clamp_publication_date(far) is None

    @pytest.mark.parametrize("raw", [None, "", "not-a-date"])
    def test_invalid_inputs(self, raw):
        assert clamp_publication_date(raw) is None


class TestParseItalianDate:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("12 aprile 2026", "2026-04-12"),
            ("12 apr 2026", "2026-04-12"),
            ("12/04/2026", "2026-04-12"),
            ("12-04-26", "2026-04-12"),
            ("2026-04-12", "2026-04-12"),
            ("Pubblicato il 3 marzo 2025", "2025-03-03"),
        ],
    )
    def test_formats(self, raw, expected):
        assert parse_italian_date(raw) == expected

    def test_impossible_date_rejected(self):
        assert parse_italian_date("31/02/2026") is None


class TestMapPropertyType:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Appartamento", "apartment"),
            ("Villa unifamiliare", "villa"),
            ("Villetta a schiera", "house"),
            ("Terreno edificabile", "land"),
            ("Edificabile", "land"),
            ("Monolocale", "studio"),
            ("Ufficio", "commercial"),
            (None, "apartment"),
        ],
    )
    def test_mapping(self, raw, expected):
        assert map_property_type(raw) == expected


def test_parse_int_and_float():
    assert parse_int("3 locali") == 3
    assert parse_int(None) is None
    assert parse_float_text("1.250,50 €") == 1250.5
    assert parse_float_text("85 m²") == 85.0

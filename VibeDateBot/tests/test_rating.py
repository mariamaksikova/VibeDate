from __future__ import annotations

from app.services.rating import calc_behavior_rating, calc_combined_rating, calc_primary_rating


def test_primary_rating_grows_with_photos_and_completeness() -> None:
    base = calc_primary_rating(25, "a,b", "City", "a", 0, 50)
    with_photos = calc_primary_rating(25, "a,b", "City", "a", 5, 50)
    assert with_photos > base


def test_behavior_rating_respects_like_ratio() -> None:
    low = calc_behavior_rating(likes_received=1, skips_received=9, matches_count=0, dialogs_started=0)
    high = calc_behavior_rating(likes_received=9, skips_received=1, matches_count=0, dialogs_started=0)
    assert high > low


def test_combined_is_weighted_plus_referral() -> None:
    c = calc_combined_rating(1000, 1000, referral_bonus=10)
    assert c == 1000 + 10

from __future__ import annotations

from app.services.rating import (
    calc_behavior_rating,
    calc_combined_rating,
    calc_primary_rating,
    calc_referral_bonus,
)


def test_primary_rating_all_level1_fields() -> None:
    full = calc_primary_rating(25, "m", "Moscow", "a,b", "a", 18, 30, 3, 100)
    empty = calc_primary_rating(None, None, None, None, None, None, None, 0, 0)
    assert full > empty


def test_behavior_rating_activity_bonus() -> None:
    low_activity = calc_behavior_rating(5, 5, 1, 1, activity_peak_share=0.2)
    high_activity = calc_behavior_rating(5, 5, 1, 1, activity_peak_share=0.9)
    assert high_activity > low_activity


def test_combined_with_referral() -> None:
    base = calc_combined_rating(1000, 1000, referral_bonus=0)
    with_ref = calc_combined_rating(1000, 1000, referral_bonus=calc_referral_bonus(3))
    assert with_ref > base


def test_referral_bonus_caps() -> None:
    assert calc_referral_bonus(100) == calc_referral_bonus(20)

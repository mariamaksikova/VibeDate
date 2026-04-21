from __future__ import annotations


def calc_primary_rating(
    age: int | None,
    interests: str | None,
    city: str | None,
    looking_for: str | None,
    photo_count: int,
    profile_completeness: int,
) -> int:
    score = 900
    if age is not None:
        score += 15
    if city:
        score += 15
    if interests:
        score += 30
    if looking_for:
        score += 20
    score += min(max(photo_count, 0), 5) * 8
    score += min(max(profile_completeness, 0), 100) // 4
    return score


def calc_behavior_rating(
    likes_received: int,
    skips_received: int,
    matches_count: int,
    dialogs_started: int,
) -> int:
    total_reactions = max(likes_received + skips_received, 1)
    like_ratio = likes_received / total_reactions
    score = 900
    score += int(like_ratio * 120)
    score += min(matches_count, 100) * 3
    score += min(dialogs_started, 100) * 2
    return score


def calc_combined_rating(
    primary_rating: int,
    behavior_rating: int,
    referral_bonus: int = 0,
) -> int:
    return int(primary_rating * 0.6 + behavior_rating * 0.4) + max(referral_bonus, 0)

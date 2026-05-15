from __future__ import annotations


def calc_primary_rating(
    age: int | None,
    gender: str | None,
    city: str | None,
    interests: str | None,
    looking_for: str | None,
    min_age: int | None,
    max_age: int | None,
    photo_count: int,
    profile_completeness: int,
) -> int:
    """Уровень 1: анкета, предпочтения, фото, заполненность."""
    score = 900
    if age is not None:
        score += 15
    if gender:
        score += 10
    if city:
        score += 15
    if interests:
        score += 30
    if looking_for:
        score += 20
    if min_age is not None and max_age is not None:
        score += 15
    score += min(max(photo_count, 0), 5) * 8
    score += min(max(profile_completeness, 0), 100) // 4
    return score


def calc_behavior_rating(
    likes_received: int,
    skips_received: int,
    matches_count: int,
    dialogs_started: int,
    activity_peak_share: float,
) -> int:
    """Уровень 2: лайки, ratio, мэтчи, диалоги, активность по часам."""
    total_reactions = max(likes_received + skips_received, 1)
    like_ratio = likes_received / total_reactions
    score = 900
    score += int(like_ratio * 120)
    score += min(matches_count, 100) * 3
    score += min(dialogs_started, 100) * 2
    score += int(min(max(activity_peak_share, 0.0), 1.0) * 50)
    return score


def calc_combined_rating(
    primary_rating: int,
    behavior_rating: int,
    referral_bonus: int = 0,
) -> int:
    """Уровень 3: весовая модель + реферальный бонус."""
    return int(primary_rating * 0.6 + behavior_rating * 0.4) + max(referral_bonus, 0)


def calc_referral_bonus(referrals_count: int) -> int:
    return min(max(referrals_count, 0), 20) * 5

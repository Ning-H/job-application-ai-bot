from datetime import datetime, timedelta
from typing import Any

from src.config_loader import config


def _value(job: Any, key: str, default=None):
    if isinstance(job, dict):
        return job.get(key, default)
    return getattr(job, key, default)


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def is_hidden_job(job: Any) -> bool:
    return bool(_value(job, "hidden")) or bool(_value(job, "not_fit"))


def is_new_job(job: Any, now: datetime | None = None) -> bool:
    now = now or datetime.utcnow()
    first_seen = _value(job, "first_seen_at") or _value(job, "discovered_date")
    if not first_seen:
        return False
    reviewed_at = _value(job, "reviewed_at")
    freshness_window_hours = 24
    if reviewed_at:
        return False
    return first_seen >= now - timedelta(hours=freshness_window_hours)


def role_alignment_bonus(title: str) -> float:
    title_text = normalize_text(title)
    bonus = 0.0

    if any(token in title_text for token in ["director", "vp ", "vice president", "head of"]):
        bonus -= 0.08

    if "data engineer" in title_text:
        bonus += 0.18
    if "analytics engineer" in title_text:
        bonus += 0.16
    if any(token in title_text for token in ["data platform", "data infrastructure", "data infra"]):
        bonus += 0.13
    if any(token in title_text for token in ["ml platform", "machine learning platform", "ai platform", "ai engineer", "applied ai"]):
        bonus += 0.10
    if "machine learning engineer" in title_text or "ml engineer" in title_text:
        bonus += 0.02
    if any(token in title_text for token in ["software engineer, data", "software engineer - data", "platform engineer, data"]):
        bonus += 0.08
    if "applied scientist" in title_text and "engineer" not in title_text:
        bonus -= 0.10
    if any(token in title_text for token in ["frontend", "front-end", "ios", "android", "product manager"]):
        bonus -= 0.18
    if any(token in title_text for token in ["ads", "auction", "perception", "simulation", "autonomy", "vision"]):
        bonus -= 0.15
    return bonus


def board_rank_score(job: Any, now: datetime | None = None) -> float:
    now = now or datetime.utcnow()
    overall = float(_value(job, "overall_score") or 0.0)
    title_bonus = role_alignment_bonus(_value(job, "title"))
    freshness_bonus = 0.0

    if is_new_job(job, now):
        freshness_bonus += 0.06

    last_seen = _value(job, "last_seen_at") or _value(job, "discovered_date")
    if last_seen:
        hours_since_seen = max((now - last_seen).total_seconds() / 3600, 0)
        if hours_since_seen <= config.get_crawl_frequency_hours() + 1:
            freshness_bonus += 0.03
        elif hours_since_seen <= 24:
            freshness_bonus += 0.01

    preference = _value(job, "user_preference_score")
    preference_adjustment = 0.0
    if preference is not None:
        preference_adjustment = ((float(preference) / 5.0) - 0.6) * 0.25

    review_penalty = -0.02 if _value(job, "reviewed_at") else 0.0
    applied_penalty = -1.0 if _value(job, "applied") else 0.0
    hidden_penalty = -1.0 if is_hidden_job(job) else 0.0

    return round(overall + title_bonus + freshness_bonus + preference_adjustment + review_penalty + applied_penalty + hidden_penalty, 4)


def fit_score(job: Any, now: datetime | None = None) -> float:
    return max(0.0, min(1.0, board_rank_score(job, now)))


def relative_time(value: datetime | None, now: datetime | None = None) -> str:
    if not value:
        return "unknown"

    now = now or datetime.utcnow()
    delta = now - value
    seconds = max(int(delta.total_seconds()), 0)
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    if hours < 24:
        return f"{hours}h ago"
    if days == 1:
        return "1d ago"
    return f"{days}d ago"

from datetime import datetime, timedelta
import re
from typing import Any, Dict, List

from src.config_loader import config

# Minimum overall score to keep a job (LLM-scored 0–1)
MIN_SKILLS_MATCH = 0.45

# Only consider jobs posted within this many days
MAX_JOB_AGE_DAYS = 14

REMOTE_KEYWORDS = ["remote", "anywhere", "work from home", "wfh"]
PREFERRED_LOCATION_KEYWORDS = [
    "alexandria", "arlington", "washington", "virginia", "maryland", "dc",
    "san francisco", "bay area", "palo alto", "mountain view", "sunnyvale", "san jose",
]
NON_US_KEYWORDS = [
    "united kingdom", "uk", "england", "london", "manchester",
    "canada", "toronto", "vancouver", "montreal",
    "germany", "berlin", "munich", "france", "paris",
    "netherlands", "amsterdam", "sweden", "stockholm",
    "australia", "sydney", "melbourne",
    "india", "bangalore", "bengaluru", "hyderabad",
    "singapore", "japan", "tokyo", "israel", "ireland", "dublin",
    "spain", "poland", "warsaw", "switzerland", "seoul", "taipei",
    "brazil", "mexico", "argentina", "chile",
    "emea", "apac", "latam", "europe",
]
NEGATIVE_TITLE_KEYWORDS = [
    "frontend", "front-end", "full stack designer", "designer", "product manager",
    "ios", "android", "mobile", "qa ", "quality assurance", "test engineer",
    "customer success", "sales", "account executive", "support engineer",
]
ROLE_PATTERNS = [
    re.compile(r"\bdata engineer\b"),
    re.compile(r"\banalytics engineer\b"),
    re.compile(r"\b(machine learning|ml|ai) engineer\b"),
    re.compile(r"\bdata (platform|infrastructure|infra|warehouse|warehousing)\b"),
    re.compile(r"\b(machine learning|ml|ai) (platform|infrastructure|infra)\b"),
    re.compile(r"\bdata pipeline\b"),
    re.compile(r"\blakehouse\b"),
    re.compile(r"\bsoftware engineer\b.*\b(data|analytics|ml|machine learning|ai)\b"),
    re.compile(r"\bplatform engineer\b.*\b(data|analytics|ml|machine learning|ai)\b"),
]
US_STATE_PATTERN = re.compile(
    r",\s*(AL|AK|AZ|AR|CA|CO|CT|DC|DE|FL|GA|HI|IA|ID|IL|IN|KS|KY|LA|MA|MD|ME|MI|MN|MO|MS|MT|NC|ND|NE|NH|NJ|NM|NV|NY|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VA|VT|WA|WI|WV|WY)\b",
    re.IGNORECASE,
)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _looks_non_us_location(location: str) -> bool:
    loc = _normalize_text(location)
    if not loc:
        return False

    if any(token in loc for token in REMOTE_KEYWORDS) and any(
        token in loc for token in ["us", "usa", "united states", "u.s."]
    ):
        return False

    if US_STATE_PATTERN.search(loc):
        return False

    if any(token in loc for token in PREFERRED_LOCATION_KEYWORDS):
        return False

    return any(token in loc for token in NON_US_KEYWORDS)


def _is_supported_location(job: Dict[str, Any]) -> bool:
    """Reject only clearly non-US roles. US remote and non-preferred metros still pass and get ranked later."""
    location = _normalize_text(job.get("location"))
    if not location:
        return True
    return not _looks_non_us_location(location)


class JobFilter:
    def __init__(self):
        self.target_titles = [title.lower() for title in config.get_target_titles()]
        self.location_prefs = config.get_location_preferences()
        self.skill_keywords = sorted(
            {
                token.lower()
                for token in (
                    config.get_skills()
                    + [
                        "data platform", "data infra", "data infrastructure", "data pipeline",
                        "analytics", "warehouse", "lakehouse", "elt", "etl", "dbt",
                        "spark", "airflow", "snowflake", "databricks", "kafka",
                        "machine learning", "ml", "ai", "llm", "genai",
                    ]
                )
                if len(token) >= 2
            }
        )

    def matches_title(self, job_title: str, description: str = "") -> bool:
        title = _normalize_text(job_title)
        desc = _normalize_text(description)
        haystack = f"{title}\n{desc}"

        if not title:
            return False

        if any(keyword in title for keyword in NEGATIVE_TITLE_KEYWORDS):
            return False

        score = 0.0

        if any(target in title for target in self.target_titles):
            score += 2.5

        if any(pattern.search(title) for pattern in ROLE_PATTERNS):
            score += 2.5

        if any(keyword in title for keyword in ["manager", "lead", "staff", "principal", "senior"]):
            score += 0.4

        if "scientist" in title and "engineer" not in title:
            score -= 1.0

        if any(keyword in title for keyword in ["ads", "auction", "perception", "vision", "autonomy", "simulation"]):
            score -= 0.5

        stack_matches = sum(1 for keyword in self.skill_keywords if keyword in haystack)
        if stack_matches >= 2:
            score += 1.0
        elif stack_matches == 1:
            score += 0.4

        return score >= 2.5

    def meets_salary_requirements(self, job: Dict[str, Any]) -> bool:
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")
        if salary_min is None and salary_max is None:
            return True

        salary = salary_max if salary_max else salary_min
        location = _normalize_text(job.get("location"))

        if job.get("is_remote") or any(keyword in location for keyword in REMOTE_KEYWORDS):
            threshold = self.location_prefs["preferences"][0]["min_salary"]
        elif any(keyword in location for keyword in ["san francisco", "palo alto", "mountain view", "sunnyvale", "san jose", "bay area"]):
            threshold = next((p["min_salary"] for p in self.location_prefs["preferences"] if p["type"] == "bay_area"), 300000)
        elif any(keyword in location for keyword in ["alexandria", "arlington", "washington", "dc", "maryland", "virginia"]):
            threshold = next((p["min_salary"] for p in self.location_prefs["preferences"] if p["type"] == "dmv"), 230000)
        else:
            threshold = next((p["min_salary"] for p in self.location_prefs["preferences"] if p["type"] == "other"), 250000)

        return salary >= threshold

    def filter_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cutoff = datetime.utcnow() - timedelta(days=MAX_JOB_AGE_DAYS)
        filtered = []

        for job in jobs:
            if not self.matches_title(job.get("title", ""), job.get("description", "")):
                continue
            if not _is_supported_location(job):
                continue
            if not self.meets_salary_requirements(job):
                continue

            posted = job.get("posted_date")
            if posted and isinstance(posted, datetime) and posted < cutoff:
                continue

            filtered.append(job)

        return filtered

    def apply_score_threshold(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove jobs below the minimum overall score."""
        return [job for job in jobs if (job.get("overall_score") or 0) >= MIN_SKILLS_MATCH]

from typing import List, Dict, Any
from src.config_loader import config
from datetime import datetime, timedelta
import re

# Minimum overall score to keep a job (LLM-scored 0–1)
MIN_SKILLS_MATCH = 0.45

# Only consider jobs posted within this many days
MAX_JOB_AGE_DAYS = 14

# Whitelisted location keywords — only jobs in these locations are kept
REMOTE_KEYWORDS = ["remote", "anywhere", "work from home", "wfh"]

CALIFORNIA_KEYWORDS = [
    "california", " ca,", ", ca", "-ca-", " ca ", "(ca)",
    "san francisco", " sf,", "bay area", "silicon valley",
    "palo alto", "mountain view", "sunnyvale", "san jose",
    "menlo park", "santa clara", "san mateo", "redwood city",
    "foster city", "burlingame", "south san francisco",
    "los angeles", " la,", "san diego", "irvine", "santa monica",
]

DMV_KEYWORDS = [
    "washington, dc", "washington dc", " dc,", ", dc", "(dc)",
    "virginia", " va,", ", va", "(va)",
    "maryland", " md,", ", md", "(md)",
    "alexandria", "arlington", "reston", "tysons", "mclean",
    "herndon", "bethesda", "silver spring", "rockville",
    "fairfax", "falls church", "annandale", "vienna",
]

# Explicitly excluded — non-US countries and unwanted US metros
EXCLUDED_KEYWORDS = [
    # Non-US countries and cities
    "united kingdom", "london", "manchester", "england",
    "canada", "toronto", "vancouver", "montreal",
    "germany", "berlin", "munich", "france", "paris",
    "netherlands", "amsterdam", "sweden", "stockholm",
    "australia", "sydney", "melbourne", "india", "bangalore",
    "bengaluru", "hyderabad", "singapore", "japan", "tokyo",
    "israel", "ireland", "dublin", "spain", "poland", "warsaw", "switzerland",
    "south korea", "korea", "seoul", "taiwan", "taipei",
    "brazil", "mexico", "argentina", "chile",
    "europe", "emea", "apac", "latam",
    # Country code patterns in Ashby/Greenhouse locations (e.g. "Remote - FR", "Remote - UK")
    "- uk", "- gb", "- de", "- fr", "- nl", "- se", "- au", "- in", "- sg",
    "- pl", "- ie", "- es", "- ch", "- ca\n", "- ca ", "- ca,",
    "-pl-", "-uk-", "-de-", "-fr-", "-nl-", "-se-", "-au-", "-in-", "-sg-",
    "-ie-", "-es-", "-ch-",
    # Excluded US metros
    "new york", "nyc", " ny,", ", ny", "brooklyn", "manhattan",
    "seattle", " wa,", ", wa",
    "chicago", " il,", ", il",
    "austin", "dallas", "houston", " tx,", ", tx",
    "denver", " co,", ", co",
    "boston", " ma,", ", ma",
    "atlanta", " ga,", ", ga",
    "miami", "orlando", " fl,", ", fl",
    "phoenix", " az,", ", az",
    "portland", " or,", ", or",
    "minneapolis", " mn,", ", mn",
    "nashville", " tn,", ", tn",
    "charlotte", "raleigh", " nc,", ", nc",
    "pittsburgh", "philadelphia", " pa,", ", pa",
    "detroit", "cleveland", " oh,", ", oh",
    "salt lake", " ut,", ", ut",
    "kansas city", "st. louis", " mo,", ", mo",
    "las vegas", " nv,", ", nv",
    "new orleans", " la,", ", la",
    " ar,", ", ar",   # Arkansas (Bentonville, etc.)
]

# Locations that are explicitly US-wide (not tied to a specific city)
US_WIDE_KEYWORDS = ["united states", " us,", ", us", "(us)", "usa", "u.s."]


def _is_preferred_location(job: Dict[str, Any]) -> bool:
    """Keep ONLY: Remote-US, California/Bay Area, and DMV-area jobs."""
    location = (job.get("location") or "").lower().strip()

    # Empty location — keep (LLM will judge)
    if not location:
        return True

    # EXCLUSIONS FIRST — catches non-US countries and bad US metros
    for kw in EXCLUDED_KEYWORDS:
        if kw in location:
            return False

    # Remote — keep only if no non-US country indicator remains after exclusion pass
    for kw in REMOTE_KEYWORDS:
        if kw in location:
            return True

    # California / Bay Area
    for kw in CALIFORNIA_KEYWORDS:
        if kw in location:
            return True

    # DMV
    for kw in DMV_KEYWORDS:
        if kw in location:
            return True

    # Explicitly US-wide (e.g. "United States", "US", "USA")
    if location in ("us", "usa", "u.s.", "u.s.a."):
        return True
    for kw in US_WIDE_KEYWORDS:
        if kw in location:
            return True

    # Default: exclude — unknown/unrecognized location is likely not in our targets
    return False


class JobFilter:
    def __init__(self):
        self.target_titles = config.get_target_titles()
        self.location_prefs = config.get_location_preferences()

    def matches_title(self, job_title: str) -> bool:
        job_title_lower = job_title.lower()
        for target in self.target_titles:
            if target.lower() in job_title_lower:
                return True
        return False

    def meets_salary_requirements(self, job: Dict[str, Any]) -> bool:
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")
        if not salary_min and not salary_max:
            return True  # no salary listed — keep, filter later by score
        salary = salary_max if salary_max else salary_min
        if job.get("is_remote"):
            return salary >= self.location_prefs["preferences"][0]["min_salary"]
        location = job.get("location", "").lower()
        if any(c in location for c in ["san francisco", "palo alto", "mountain view", "sunnyvale", "san jose", "bay area"]):
            return salary >= next((p["min_salary"] for p in self.location_prefs["preferences"] if p["type"] == "bay_area"), 300000)
        if any(c in location for c in ["alexandria", "arlington", "washington", "dc", "maryland", "virginia"]):
            return salary >= next((p["min_salary"] for p in self.location_prefs["preferences"] if p["type"] == "dmv"), 230000)
        return salary >= next((p["min_salary"] for p in self.location_prefs["preferences"] if p["type"] == "other"), 250000)

    def filter_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cutoff = datetime.utcnow() - timedelta(days=MAX_JOB_AGE_DAYS)
        filtered = []
        for job in jobs:
            if not self.matches_title(job.get("title", "")):
                continue
            if not _is_preferred_location(job):
                continue
            if not self.meets_salary_requirements(job):
                continue
            # Drop jobs older than MAX_JOB_AGE_DAYS (keeps unknown posted_date)
            posted = job.get("posted_date")
            if posted and isinstance(posted, datetime) and posted < cutoff:
                continue
            filtered.append(job)
        return filtered

    def apply_score_threshold(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove jobs below the minimum overall score."""
        return [j for j in jobs if (j.get("overall_score") or 0) >= MIN_SKILLS_MATCH]

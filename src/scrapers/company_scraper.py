from typing import List, Dict, Any, Optional
import re
import html as html_lib
import aiohttp
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper


GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs?content=true"
LEVER_API      = "https://api.lever.co/v0/postings/{board_id}?mode=json&limit=500"
ASHBY_API      = "https://api.ashbyhq.com/posting-api/job-board/{board_id}?includeCompensation=true"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── helpers ───────────────────────────────────────────────────────────────────

def _strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


def _extract_salary(text: str) -> Optional[str]:
    """Pull a salary range string out of job description text, if present."""
    if not text:
        return None
    patterns = [
        # $200,000 - $300,000 (with optional /yr etc.)
        r'\$[\d,]+\s*[-–—to]+\s*\$[\d,]+(?:\s*(?:per year|\/yr|\/year|annually))?',
        # $200K - $300K
        r'\$[\d,]+[Kk]\s*[-–—to]+\s*\$[\d,]+[Kk]',
        # USD 200,000 - 300,000
        r'USD\s*[\d,]+\s*[-–—to]+\s*[\d,]+',
        # pay/salary/compensation range: $X to $Y
        r'(?:pay|salary|compensation|base)[^\n]{0,80}\$[\d,]+[Kk]?\s*[-–—to]+\s*\$[\d,]+[Kk]?',
        # The range for this role is $X - $Y
        r'range[^\n]{0,40}\$[\d,]+[Kk]?\s*[-–—]+\s*\$[\d,]+[Kk]?',
        # Single value: $200,000/yr or $200K/yr
        r'\$[\d,]+[Kk]?\s*(?:per year|\/yr|\/year|annually)',
        # Fallback: any $ followed by 6+ digit number
        r'\$[\d,]{6,}',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def _iso_to_date(s: str) -> Optional[str]:
    """Return YYYY-MM-DD from an ISO-8601 string, or None."""
    if not s:
        return None
    return s[:10]  # "2024-03-15T00:00:00Z" → "2024-03-15"


def _ms_to_date(ms) -> Optional[str]:
    """Convert Lever's createdAt (milliseconds epoch) to YYYY-MM-DD."""
    if not ms:
        return None
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


# ── scraper ───────────────────────────────────────────────────────────────────

class CompanyScraper(BaseScraper):

    async def scrape_greenhouse(self, board_id: str, company_name: str) -> List[Dict[str, Any]]:
        url = GREENHOUSE_API.format(board_id=board_id)
        jobs = []
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        print(f"  Greenhouse {company_name}: HTTP {resp.status}")
                        return []
                    data = await resp.json()

            for job in data.get("jobs", []):
                # Location — prefer offices list, fall back to location dict
                locs = job.get("offices") or []
                if locs:
                    location = ", ".join(o.get("name", "") for o in locs if o.get("name"))
                else:
                    loc = job.get("location") or {}
                    location = loc.get("name", "") if isinstance(loc, dict) else str(loc)

                # Greenhouse double-encodes HTML — unescape first, then strip tags
                description = _strip_html(html_lib.unescape(job.get("content", "")))
                jobs.append({
                    "title":       job.get("title", ""),
                    "company":     company_name,
                    "location":    location,
                    "url":         job.get("absolute_url", ""),
                    "description": description,
                    "posted_date": _iso_to_date(job.get("updated_at")),
                    "salary":      _extract_salary(description),
                })
        except Exception as e:
            print(f"  Greenhouse error for {company_name}: {e}")
        return jobs

    async def scrape_lever(self, board_id: str, company_name: str) -> List[Dict[str, Any]]:
        url = LEVER_API.format(board_id=board_id)
        jobs = []
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        print(f"  Lever {company_name}: HTTP {resp.status}")
                        return []
                    data = await resp.json()

            for job in data:
                cats = job.get("categories", {})
                location = cats.get("location") or cats.get("allLocations") or ""
                if isinstance(location, list):
                    location = ", ".join(location)

                description = (
                    _strip_html(job.get("description", ""))
                    or job.get("descriptionPlain", "")
                )
                # Lever additional fields
                lists = job.get("lists", [])
                if lists:
                    for lst in lists:
                        description += "\n" + lst.get("text", "") + ": " + _strip_html(lst.get("content", ""))

                # Use native salaryRange field if available
                salary_str = None
                sal = job.get("salaryRange") or {}
                if sal.get("min") and sal.get("max"):
                    salary_str = f"${sal['min']}-${sal['max']}"
                elif sal.get("min"):
                    salary_str = f"${sal['min']}"
                if not salary_str:
                    salary_str = _extract_salary(description)
                jobs.append({
                    "title":       job.get("text", ""),
                    "company":     company_name,
                    "location":    location,
                    "url":         job.get("hostedUrl", ""),
                    "description": description,
                    "posted_date": _ms_to_date(job.get("createdAt")),
                    "salary":      salary_str,
                })
        except Exception as e:
            print(f"  Lever error for {company_name}: {e}")
        return jobs

    async def scrape_ashby(self, board_id: str, company_name: str) -> List[Dict[str, Any]]:
        url = ASHBY_API.format(board_id=board_id)
        jobs = []
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        print(f"  Ashby {company_name}: HTTP {resp.status}")
                        return []
                    data = await resp.json(content_type=None)

            for job in data.get("jobs", []):
                loc = job.get("location") or {}
                if isinstance(loc, dict):
                    location = loc.get("name", "")
                else:
                    location = str(loc)

                # Ashby has both isRemote flag and address
                if job.get("isRemote") and "remote" not in location.lower():
                    location = ("Remote - " + location).strip(" -") if location else "Remote"

                description = _strip_html(
                    job.get("descriptionHtml", "") or job.get("description", "")
                )
                # Extract salary from structured compensation field (more reliable than regex)
                salary_str = None
                comp = job.get("compensation") or {}
                for component in comp.get("summaryComponents", []):
                    if component.get("compensationType") == "Salary":
                        lo = component.get("minValue")
                        hi = component.get("maxValue")
                        if lo and hi:
                            salary_str = f"${lo}-${hi}"
                        elif lo:
                            salary_str = f"${lo}"
                        break
                if not salary_str:
                    salary_str = _extract_salary(description)
                jobs.append({
                    "title":       job.get("title", ""),
                    "company":     company_name,
                    "location":    location,
                    "url":         job.get("jobUrl", "") or job.get("applyUrl", ""),
                    "description": description,
                    "posted_date": _iso_to_date(job.get("publishedAt") or job.get("publishedDate")),
                    "salary":      salary_str,
                })
        except Exception as e:
            print(f"  Ashby error for {company_name}: {e}")
        return jobs

    async def scrape(self, url: str = None, company_name: str = None,
                     ats_type: str = None, board_id: str = None, **kwargs) -> List[Dict[str, Any]]:
        if ats_type == "greenhouse":
            raw_jobs = await self.scrape_greenhouse(board_id, company_name)
        elif ats_type == "lever":
            raw_jobs = await self.scrape_lever(board_id, company_name)
        elif ats_type == "ashby":
            raw_jobs = await self.scrape_ashby(board_id, company_name)
        else:
            raw_jobs = []

        return [self.normalize_job_data(j, f"{ats_type}:{company_name}") for j in raw_jobs]

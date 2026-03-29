"""
Scrapers for companies that don't use standard ATS APIs.

The direct-company layer now prefers embedded JSON and server-rendered HTML,
and only falls back to browser rendering when a site still needs it.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin

import aiohttp
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, get_openai_client
from .company_scraper import CompanyScraper, _extract_salary


SEARCH_QUERIES = [
    "data engineer",
    "machine learning engineer",
    "AI engineer",
    "analytics engineer",
    "data engineering manager",
]

QUERY_HINTS = {
    "data engineer": [
        "data engineer",
        "data engineering",
        "data platform",
        "data pipeline",
        "etl",
        "data warehouse",
        "big data",
        "data analytics",
    ],
    "machine learning engineer": [
        "machine learning engineer",
        "ml engineer",
        "machine learning",
        "mlops",
        "ai/ml",
        "applied scientist",
    ],
    "ai engineer": [
        "ai engineer",
        "artificial intelligence",
        "generative ai",
        "llm",
        "applied ai",
        "machine learning",
    ],
    "analytics engineer": [
        "analytics engineer",
        "analytics",
        "business intelligence",
        "bi engineer",
        "reporting",
        "semantic layer",
    ],
    "data engineering manager": [
        "data engineering manager",
        "engineering manager, data",
        "manager, data engineering",
        "head of data engineering",
        "analytics engineering manager",
    ],
}

QUERY_NEGATIVE_HINTS = {
    "data engineer": [
        "data center",
        "mechanical engineer",
        "electrical engineer",
        "civil engineer",
    ],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _strip_html_text(value: str) -> str:
    if not value:
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _make_soup(value: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(value, "lxml")
    except Exception:
        return BeautifulSoup(value, "html.parser")


def _absolute_url(base_url: str, maybe_relative_url: str) -> str:
    if not maybe_relative_url:
        return ""
    return urljoin(base_url, maybe_relative_url)


def _has_alnum(value: str) -> bool:
    return any(char.isalnum() for char in value)


def _clean_location_text(value: Any) -> str:
    cleaned = _clean_text(value)
    cleaned = re.sub(r"^[;,\-:|/\\\s]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _merge_locations(first: str, second: str) -> str:
    parts = []
    for value in [first, second]:
        if not value:
            continue
        parts.extend(_clean_text(part) for part in value.split(";") if _clean_text(part))
    return "; ".join(dict.fromkeys(parts))


def _dedup(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for job in jobs:
        key = job.get("url") or job.get("title")
        if not key:
            continue

        current = deduped.get(key)
        if current is None:
            deduped[key] = job
            continue

        current["location"] = _merge_locations(current.get("location", ""), job.get("location", ""))
        if len(_clean_text(job.get("description", ""))) > len(_clean_text(current.get("description", ""))):
            current["description"] = job.get("description", "")
        if not current.get("posted_date") and job.get("posted_date"):
            current["posted_date"] = job.get("posted_date")
        if not current.get("salary") and job.get("salary"):
            current["salary"] = job.get("salary")
        metadata = current.get("metadata") or {}
        metadata.update(job.get("metadata") or {})
        if metadata:
            current["metadata"] = metadata

    return list(deduped.values())


async def _fetch_text(url: str, timeout_seconds: int = 30) -> Optional[str]:
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    print(f"    HTTP {response.status} for {url}")
                    return None
                return await response.text()
    except Exception as exc:
        print(f"    Request error for {url}: {exc}")
        return None


def _parse_json_script(html: str, script_id: str = "__NEXT_DATA__") -> Optional[Dict[str, Any]]:
    soup = _make_soup(html)
    script = soup.find("script", id=script_id)
    if not script or not script.string:
        return None
    try:
        return json.loads(script.string)
    except json.JSONDecodeError:
        return None


def _parse_location_name(location: Dict[str, Any]) -> str:
    name = _clean_location_text(location.get("name"))
    if name:
        return name

    city = _clean_location_text(location.get("city"))
    state = _clean_location_text(location.get("state") or location.get("stateCode") or location.get("stateProvince"))
    country = _clean_location_text(location.get("country") or location.get("countryName"))
    parts = [part for part in [city, state, country] if part]
    return ", ".join(parts)


def _build_description(*parts: str) -> str:
    unique_parts = []
    for part in parts:
        cleaned = _clean_text(part)
        if cleaned and cleaned not in unique_parts:
            unique_parts.append(cleaned)
    return "\n".join(unique_parts)


def _normalize_posted_date(value: Any) -> Optional[str]:
    text = _clean_text(value)
    if not text:
        return None
    if re.match(r"\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    return text


def _tokenize(value: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _phrase_in_text(text: str, phrase: str) -> bool:
    normalized_text = _clean_text(text).lower()
    normalized_phrase = _clean_text(phrase).lower()
    if not normalized_text or not normalized_phrase:
        return False

    pattern = r"(?<![a-z0-9])" + re.escape(normalized_phrase).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def _job_matches_query(job: Dict[str, Any], query: str) -> bool:
    title = _clean_text(job.get("title", "")).lower()
    haystack = _clean_text(" ".join([
        job.get("title", ""),
        job.get("description", ""),
    ])).lower()
    if not title and not haystack:
        return False

    hints = QUERY_HINTS.get(query.lower(), [query.lower()])
    if any(_phrase_in_text(haystack, hint) for hint in hints):
        return True

    negative_hints = QUERY_NEGATIVE_HINTS.get(query.lower(), [])
    if any(_phrase_in_text(haystack, hint) for hint in negative_hints):
        return False

    query_tokens = {
        token for token in _tokenize(query)
        if token not in {"and", "or", "the", "for", "with", "to", "of", "a", "an"}
    }
    if not query_tokens:
        return True

    title_tokens = set(_tokenize(title))
    role_tokens = {"engineer", "engineering", "manager", "scientist", "developer", "architect", "analyst"}
    query_role_tokens = query_tokens & role_tokens
    query_domain_tokens = query_tokens - role_tokens

    if query_domain_tokens and not (query_domain_tokens & title_tokens):
        return False
    if query_role_tokens and not (query_role_tokens & title_tokens):
        return False

    return bool((query_domain_tokens | query_role_tokens) & title_tokens)


def _job_matches_any_query(job: Dict[str, Any]) -> bool:
    return any(_job_matches_query(job, query) for query in SEARCH_QUERIES)


# ── Google Careers ────────────────────────────────────────────────────────────

GOOGLE_SEARCH_URL = (
    "https://www.google.com/about/careers/applications/jobs/results/"
    "?q={query}&location=United+States"
)
GOOGLE_BASE_URL = "https://www.google.com/about/careers/applications/"


async def _scrape_google_html(query: str) -> List[Dict[str, Any]]:
    url = GOOGLE_SEARCH_URL.format(query=quote_plus(query))
    html = await _fetch_text(url)
    if not html:
        return []

    soup = _make_soup(html)
    jobs = []

    for card in soup.select("div.sMn82b"):
        title_el = card.select_one("h3.QJPWVe") or card.find(["h2", "h3"])
        link_el = card.select_one("a[href*='jobs/results/']")
        if not title_el or not link_el:
            continue

        locations = [
            _clean_location_text(span.get_text(" ", strip=True))
            for span in card.select("span.r0wTof")
            if _has_alnum(_clean_location_text(span.get_text(" ", strip=True)))
        ]
        detail_text = ""
        detail_el = card.select_one("div.Xsxa1e")
        if detail_el:
            detail_text = _clean_text(detail_el.get_text(" ", strip=True))

        description = _build_description(detail_text)
        jobs.append({
            "title": _clean_text(title_el.get_text(" ", strip=True)),
            "company": "Google",
            "location": "; ".join(dict.fromkeys(locations)),
            "url": _absolute_url(GOOGLE_BASE_URL, link_el.get("href", "")),
            "description": description,
            "posted_date": None,
            "salary": _extract_salary(description),
        })

    return [job for job in jobs if _job_matches_query(job, query)]


# ── Meta Careers ───────────────────────────────────────────────────────────────

META_SEARCH_URL = "https://www.metacareers.com/jobs/?q={query}"

# US state 2-letter codes for location filtering
_US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}

def _meta_location_is_us(loc: str) -> bool:
    """Return True if a Meta location string is in the US."""
    if not loc:
        return False
    # "Remote, US" or "Remote, US" patterns
    if loc.strip().upper() in ("US", "USA", "REMOTE, US", "REMOTE - US"):
        return True
    if ", US" in loc or "(US)" in loc.upper():
        return True
    # "City, ST" pattern — check state abbreviation
    parts = loc.rsplit(",", 1)
    if len(parts) == 2:
        state = parts[1].strip().upper()
        if state in _US_STATES:
            return True
    return False


async def _scrape_meta_playwright(query: str) -> List[Dict]:
    """
    Scrape Meta Careers via Playwright.
    Intercepts the GraphQL response containing all_jobs.
    """
    url = META_SEARCH_URL.format(query=quote_plus(query))
    all_jobs_raw: Optional[list] = None
    html = ""

    try:
        from playwright.async_api import async_playwright
        loop = asyncio.get_running_loop()
        jobs_seen = loop.create_future()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="en-US",
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            async def handle_response(resp):
                nonlocal all_jobs_raw
                if "metacareers.com/graphql" in resp.url and resp.status == 200:
                    try:
                        text = await resp.text()
                        data = json.loads(text)
                        jobs_list = (
                            data.get("data", {})
                            .get("job_search_with_featured_jobs", {})
                            .get("all_jobs")
                        )
                        if jobs_list and len(jobs_list) > (all_jobs_raw or []).__len__():
                            all_jobs_raw = jobs_list
                            if not jobs_seen.done():
                                jobs_seen.set_result(True)
                    except Exception:
                        pass

            def on_response(resp):
                asyncio.create_task(handle_response(resp))

            page.on("response", on_response)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            except Exception:
                pass
            try:
                await asyncio.wait_for(jobs_seen, timeout=12)
            except Exception:
                pass
            await page.wait_for_timeout(3000)
            html = await page.content()
            await browser.close()
    except Exception as e:
        print(f"    Meta Playwright error: {e}")
        return []

    if not all_jobs_raw and html:
        soup = _make_soup(html)
        fallback_jobs = []
        for link in soup.select("a[href*='/jobs/']"):
            href = link.get("href", "")
            title = _clean_text(link.get_text(" ", strip=True))
            if not title or len(title) < 5:
                continue
            fallback_jobs.append({
                "title": title,
                "company": "Meta",
                "location": "United States",
                "url": _absolute_url("https://www.metacareers.com", href),
                "description": "",
                "posted_date": None,
                "salary": None,
            })
        return _dedup(fallback_jobs)

    if not all_jobs_raw:
        return []

    jobs = []
    for j in all_jobs_raw:
        locations = j.get("locations", [])
        # Keep if any location is in US (or locations list is empty — assume US)
        us_locs = [loc for loc in locations if _meta_location_is_us(loc)]
        if locations and not us_locs:
            continue
        location = "; ".join(us_locs) if us_locs else (locations[0] if locations else "United States")
        job_id = j.get("id", "")
        jobs.append({
            "title": j.get("title", ""),
            "company": "Meta",
            "location": location,
            "url": f"https://www.metacareers.com/jobs/{job_id}/",
            "description": "",
            "posted_date": None,
            "salary": None,
        })

    return [job for job in jobs if _job_matches_query(job, query)]


# ── Amazon Jobs ────────────────────────────────────────────────────────────────

AMAZON_BASE = "https://www.amazon.jobs"

async def _scrape_amazon_api(query: str) -> List[Dict[str, Any]]:
    api_url = (
        "https://www.amazon.jobs/en/search.json"
        "?radius=24km"
        "&facets%5B%5D=normalized_country_code&facets%5B%5D=normalized_state_name"
        "&offset=0&result_limit=50&sort=recent"
        f"&base_query={quote_plus(query)}"
        "&country=&region=&county=&query_options="
    )
    payload = await _fetch_text(api_url)
    if not payload:
        return []

    jobs = []
    try:
        data = json.loads(payload)
        for job in data.get("jobs", []):
            if job.get("country_code", "").upper() not in {"USA", "US"}:
                continue

            description = _build_description(
                _strip_html_text(job.get("description", "")),
                _strip_html_text(job.get("basic_qualifications", "")),
            )
            location = _clean_location_text(", ".join(part for part in [job.get("city", ""), job.get("state", "")] if part))
            jobs.append({
                "title": _clean_text(job.get("title", "")),
                "company": _clean_text(job.get("company_name", "Amazon")) or "Amazon",
                "location": location or "United States",
                "url": _absolute_url(AMAZON_BASE, job.get("job_path", "")),
                "description": description,
                "posted_date": _normalize_posted_date(job.get("posted_date")),
                "salary": _extract_salary(description),
            })
    except Exception as exc:
        print(f"    Amazon JSON parse error: {exc}")

    return [job for job in jobs if _job_matches_query(job, query)]


# ── Apple Jobs ─────────────────────────────────────────────────────────────────

APPLE_SEARCH_URL = (
    "https://jobs.apple.com/en-us/search"
    "?search={query}&sort=newest&filters=countryID%3DUSA"
)

def _parse_apple_hydration_data(html: str) -> Optional[Dict[str, Any]]:
    needle = 'window.__staticRouterHydrationData = JSON.parse("'
    start = html.find(needle)
    if start == -1:
        return None

    start += len(needle)
    end = html.find('");</script>', start)
    if end == -1:
        return None

    raw = html[start:end]
    try:
        decoded = json.loads(f'"{raw}"')
        return json.loads(decoded)
    except json.JSONDecodeError:
        return None


async def _scrape_apple_html(query: str) -> List[Dict[str, Any]]:
    url = APPLE_SEARCH_URL.format(query=quote_plus(query))
    html = await _fetch_text(url)
    if not html:
        return []

    jobs = []

    hydration_data = _parse_apple_hydration_data(html)
    if hydration_data:
        search_results = (
            hydration_data.get("loaderData", {})
            .get("search", {})
            .get("searchResults", [])
        )
        for item in search_results:
            us_locations = [
                _parse_location_name(location)
                for location in item.get("locations") or []
                if (location.get("countryID") or "").upper().endswith("USA")
            ]
            us_locations = [location for location in us_locations if location]
            if not us_locations:
                continue

            transformed_title = item.get("transformedPostingTitle") or ""
            req_id = item.get("reqId") or item.get("positionId") or ""
            team_code = _clean_text((item.get("team") or {}).get("teamCode"))
            detail_path = f"/en-us/details/{req_id}/{transformed_title}" if req_id and transformed_title else ""
            if detail_path and team_code:
                detail_path = f"{detail_path}?team={team_code}"

            description = _clean_text(item.get("jobSummary", ""))
            jobs.append({
                "title": _clean_text(item.get("postingTitle", "")),
                "company": "Apple",
                "location": "; ".join(dict.fromkeys(us_locations)),
                "url": _absolute_url(url, detail_path),
                "description": description,
                "posted_date": _normalize_posted_date(item.get("postingDate") or item.get("postDateInGMT")),
                "salary": _extract_salary(description),
            })
    else:
        soup = _make_soup(html)
        for card in soup.select("li.rc-accordion-item"):
            title_el = card.select_one("h3 a[href]")
            if not title_el:
                continue

            location_el = card.select_one(".job-title-location span[id*='search-store-name-container']")
            posted_el = card.select_one(".job-posted-date")
            summary_el = card.select_one("[id*='job-summary'] span")
            description = _clean_text(summary_el.get_text(" ", strip=True)) if summary_el else ""

            jobs.append({
                "title": _clean_text(title_el.get_text(" ", strip=True)),
                "company": "Apple",
                "location": _clean_location_text(location_el.get_text(" ", strip=True)) if location_el else "United States",
                "url": _absolute_url(url, title_el.get("href", "")),
                "description": description,
                "posted_date": _normalize_posted_date(posted_el.get_text(" ", strip=True)) if posted_el else None,
                "salary": _extract_salary(description),
            })

    return [job for job in jobs if _job_matches_query(job, query)]


# ── Microsoft Jobs ─────────────────────────────────────────────────────────────

MSFT_SEARCH_URL = (
    "https://apply.careers.microsoft.com/careers/jobs"
    "?query={query}&domain=microsoft.com"
)

def _parse_microsoft_links(html: str, base_url: str) -> List[Dict[str, Any]]:
    soup = _make_soup(html)
    jobs = []
    for link in soup.select("a[href*='/careers/job']"):
        title = _clean_text(link.get_text(" ", strip=True))
        href = link.get("href", "")
        if not title or not href:
            continue

        container = link.find_parent(["article", "li", "div"])
        context_text = _clean_text(container.get_text(" ", strip=True)) if container else ""
        jobs.append({
            "title": title,
            "company": "Microsoft",
            "location": "United States",
            "url": _absolute_url(base_url, href),
            "description": context_text,
            "posted_date": None,
            "salary": _extract_salary(context_text),
        })
    return _dedup([job for job in jobs if _job_matches_any_query(job)])


# ── Rippling Careers ───────────────────────────────────────────────────────────

RIPPLING_BOARD_URL = "https://ats.rippling.com/rippling/jobs"


async def _scrape_rippling_board() -> List[Dict[str, Any]]:
    html = await _fetch_text(RIPPLING_BOARD_URL)
    if not html:
        return []

    data = _parse_json_script(html)
    if not data:
        return []

    items = (
        data.get("props", {})
        .get("pageProps", {})
        .get("jobs", {})
        .get("items", [])
    )

    jobs_by_url: Dict[str, Dict[str, Any]] = {}
    for item in items:
        url = item.get("url", "")
        if not url:
            continue

        us_locations = [
            _parse_location_name(location)
            for location in item.get("locations") or []
            if (location.get("countryCode") or "").upper() == "US"
        ]
        us_locations = [location for location in us_locations if location]
        if not us_locations:
            continue

        description = _build_description(
            _strip_html_text(item.get("jobSummary", "")),
            _clean_text((item.get("department") or {}).get("name")),
        )

        current = jobs_by_url.get(url)
        if current is None:
            jobs_by_url[url] = {
                "title": _clean_text(item.get("name", "")),
                "company": "Rippling",
                "location": "; ".join(dict.fromkeys(us_locations)),
                "url": url,
                "description": description,
                "posted_date": _normalize_posted_date(item.get("postedDate") or item.get("createdAt")),
                "salary": _extract_salary(description),
                "metadata": {
                    "department": _clean_text((item.get("department") or {}).get("name")),
                },
            }
            continue

        current["location"] = _merge_locations(current.get("location", ""), "; ".join(us_locations))
        if len(description) > len(current.get("description", "")):
            current["description"] = description

    return list(jobs_by_url.values())


# ── Main DirectScraper class ───────────────────────────────────────────────────

class DirectScraper(BaseScraper):
    """
    Scraper for companies with no standard ATS.
    Routes Databricks/Snowflake/Waymo to their existing ATS APIs.
    Uses direct HTML/API parsing where possible and falls back to browser/LLM extraction.
    """

    def __init__(self):
        super().__init__()
        self._company_scraper = CompanyScraper()

    async def _fallback_scrape_search_page(
        self,
        company_name: str,
        query: str,
        search_url: str,
    ) -> List[Dict[str, Any]]:
        try:
            get_openai_client()
        except Exception:
            return []

        result = await self.claw.scrape(
            url=search_url,
            instructions=(
                f"Extract open {company_name} job listings from this careers search page. "
                f"The search query is '{query}'. Only include actual jobs that match or closely relate "
                "to the search query. Ignore navigation links, share buttons, and duplicates. "
                "For each job return: title, company, location, salary, url, description, posted_date."
            ),
        )
        raw_jobs = result.get("jobs") or []
        cleaned_jobs = []
        for job in raw_jobs:
            if not isinstance(job, dict) or not job.get("title"):
                continue
            job["company"] = job.get("company") or company_name
            job["url"] = _absolute_url(search_url, job.get("url", ""))
            job["description"] = _clean_text(job.get("description", ""))
            if not job.get("salary"):
                job["salary"] = _extract_salary(job["description"])
            cleaned_jobs.append(job)
        return cleaned_jobs

    async def _scrape_microsoft(self, query: str) -> List[Dict[str, Any]]:
        search_url = MSFT_SEARCH_URL.format(query=quote_plus(query))
        html = await _fetch_text(search_url)
        if html:
            parsed_jobs = _parse_microsoft_links(html, search_url)
            filtered_jobs = [job for job in parsed_jobs if _job_matches_query(job, query)]
            if filtered_jobs:
                return filtered_jobs

        fallback_jobs = await self._fallback_scrape_search_page("Microsoft", query, search_url)
        return [job for job in fallback_jobs if _job_matches_query(job, query)]

    async def scrape(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        name = company_config.get("company", "")
        ats_type = company_config.get("ats_type", "")

        # ── route known-ATS companies back to their APIs ───────────────────────
        if ats_type == "direct_databricks_careers":
            return await self._company_scraper.scrape(
                company_name="Databricks", ats_type="greenhouse", board_id="databricks"
            )
        if ats_type == "direct_snowflake_careers":
            return await self._company_scraper.scrape(
                company_name="Snowflake", ats_type="ashby", board_id="snowflake"
            )
        if ats_type == "direct_waymo_careers":
            return await self._company_scraper.scrape(
                company_name="Waymo", ats_type="greenhouse", board_id="waymo"
            )

        if ats_type == "direct_rippling_ats":
            try:
                raw_jobs = [
                    job for job in await _scrape_rippling_board()
                    if _job_matches_any_query(job)
                ]
            except Exception as exc:
                print(f"    [{name}] Error scraping board: {exc}")
                raw_jobs = []
            deduped = _dedup(raw_jobs)
            return [
                self.normalize_job_data(job, f"direct:{name.lower().replace(' ', '_')}")
                for job in deduped
                if job.get("title")
            ]

        search_scraper = {
            "direct_google_careers": _scrape_google_html,
            "direct_meta_careers": _scrape_meta_playwright,
            "direct_amazon_jobs": _scrape_amazon_api,
            "direct_apple_jobs": _scrape_apple_html,
        }.get(ats_type)

        all_raw: List[Dict[str, Any]] = []

        if ats_type == "direct_microsoft_careers":
            for query in SEARCH_QUERIES:
                try:
                    all_raw.extend(await self._scrape_microsoft(query))
                except Exception as exc:
                    print(f"    [{name}] Error scraping '{query}': {exc}")
                await asyncio.sleep(1)
        elif search_scraper is not None:
            for query in SEARCH_QUERIES:
                try:
                    results = await search_scraper(query)
                    if not results:
                        fallback_url = {
                            "direct_google_careers": GOOGLE_SEARCH_URL.format(query=quote_plus(query)),
                            "direct_meta_careers": META_SEARCH_URL.format(query=quote_plus(query)),
                            "direct_amazon_jobs": (
                                "https://www.amazon.jobs/en/search"
                                f"?base_query={quote_plus(query)}&loc_query=United+States"
                            ),
                            "direct_apple_jobs": APPLE_SEARCH_URL.format(query=quote_plus(query)),
                        }.get(ats_type)
                        if fallback_url:
                            results = await self._fallback_scrape_search_page(name, query, fallback_url)
                    results = [job for job in results if _job_matches_query(job, query)]
                    all_raw.extend(results)
                except Exception as exc:
                    print(f"    [{name}] Error scraping '{query}': {exc}")
                await asyncio.sleep(1)
        else:
            print(f"    [{name}] No scraper for ats_type={ats_type!r} — skipping")
            return []

        deduped = _dedup(all_raw)
        return [
            self.normalize_job_data(j, f"direct:{name.lower().replace(' ', '_')}")
            for j in deduped
            if j.get("title")
        ]

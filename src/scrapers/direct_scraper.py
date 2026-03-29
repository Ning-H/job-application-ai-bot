"""
Scrapers for companies that don't use standard ATS (Greenhouse/Lever/Ashby).

Strategy:
  - Databricks / Snowflake / Waymo: already on GH/Ashby — routed there directly
  - Google, Meta, Apple, Amazon, Microsoft: use Playwright (headless Chromium)
    because their career sites have Cloudflare / bot detection
  - Rippling: no accessible ATS found — skipped with a log message
"""

from __future__ import annotations

import json
import re
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper
from .company_scraper import CompanyScraper


SEARCH_QUERIES = [
    "data engineer",
    "machine learning engineer",
    "AI engineer",
    "analytics engineer",
    "data engineering manager",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── helpers ────────────────────────────────────────────────────────────────────

def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _dedup(jobs: List[Dict]) -> List[Dict]:
    seen: set[str] = set()
    out = []
    for j in jobs:
        key = j.get("url", "") or j.get("title", "")
        if key and key not in seen:
            seen.add(key)
            out.append(j)
    return out


# ── Playwright-based scraper for bot-protected sites ──────────────────────────

async def _playwright_fetch_json(url: str, timeout_ms: int = 45_000) -> Optional[str]:
    """Load a URL in headless Chromium and return page HTML."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()
            # Use "load" (not "networkidle") so we don't wait for infinite XHR polling
            try:
                await page.goto(url, wait_until="load", timeout=timeout_ms)
            except Exception:
                # Some pages never fire "load" cleanly — try domcontentloaded fallback
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                except Exception:
                    pass
            # Give JS a moment to render job cards
            await page.wait_for_timeout(3000)
            content = await page.content()
            await browser.close()
            return content
    except Exception as e:
        print(f"    Playwright error: {e}")
        return None


# ── Google Careers ─────────────────────────────────────────────────────────────

GOOGLE_SEARCH_URL = (
    "https://www.google.com/about/careers/applications/jobs/results/"
    "?q={query}&location=United+States"
)
GOOGLE_JOB_BASE = "https://www.google.com/about/careers/applications/"

async def _scrape_google_playwright(query: str) -> List[Dict]:
    """
    Scrape Google Careers. Loads a React SPA — wait for .sMn82b job cards.
    Google careers.google.com redirects to google.com/about/careers/applications/.
    """
    url = GOOGLE_SEARCH_URL.format(query=query.replace(" ", "+"))
    html = ""

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="en-US",
                timezone_id="America/New_York",
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="commit", timeout=45_000)
            except Exception:
                pass
            # Wait for job cards to render
            try:
                await page.wait_for_selector(".sMn82b", timeout=15_000)
            except Exception:
                pass
            await page.wait_for_timeout(2000)
            html = await page.content()
            await browser.close()
    except Exception as e:
        print(f"    Google Playwright error: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for card in soup.find_all("div", class_="sMn82b"):
        title_el = card.find("h3", class_="QJPWVe") or card.find("h3") or card.find("h2")
        link_el = card.find("a", href=True)
        loc_spans = card.find_all("span", class_="r0wTof")

        title = title_el.get_text(strip=True) if title_el else ""
        loc_texts = list(dict.fromkeys(s.get_text(strip=True) for s in loc_spans if s.get_text(strip=True)))
        location = "; ".join(loc_texts) if loc_texts else ""
        href = link_el["href"] if link_el else ""
        job_url = (GOOGLE_JOB_BASE + href) if href and not href.startswith("http") else href

        if title:
            jobs.append({
                "title": title,
                "company": "Google",
                "location": location,
                "url": job_url,
                "description": "",  # detail page fetch would need another Playwright call
                "posted_date": None,
                "salary": None,
            })

    return jobs


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
    url = META_SEARCH_URL.format(query=query.replace(" ", "+"))
    all_jobs_raw: Optional[list] = None

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="en-US",
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            async def on_response(resp):
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
                    except Exception:
                        pass

            page.on("response", on_response)
            try:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
            except Exception:
                pass
            await page.wait_for_timeout(2000)
            await browser.close()
    except Exception as e:
        print(f"    Meta Playwright error: {e}")
        return []

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

    return jobs


# ── Amazon Jobs ────────────────────────────────────────────────────────────────

AMAZON_SEARCH_URL = (
    "https://www.amazon.jobs/en/search"
    "?base_query={query}&loc_query=United+States"
    "&country=US&result_limit=50&sort=recent"
)
AMAZON_BASE = "https://www.amazon.jobs"

async def _scrape_amazon_playwright(query: str) -> List[Dict]:
    """
    Scrape Amazon Jobs via Playwright.
    Loads the main page to acquire bot-bypass cookies, then uses page.evaluate()
    to call the search.json API. Post-filters to US jobs only.
    Note: country=US param breaks the API — filter by country_code=="USA" instead.
    """
    import urllib.parse
    api_url = (
        "https://www.amazon.jobs/en/search.json"
        "?radius=24km"
        "&facets%5B%5D=normalized_country_code&facets%5B%5D=normalized_state_name"
        "&offset=0&result_limit=50&sort=recent"
        f"&base_query={urllib.parse.quote(query)}"
        "&country=&region=&county=&query_options="
    )

    captured_json: Optional[str] = None

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="en-US",
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            # Load the main jobs page to acquire cookies / pass bot checks
            try:
                await page.goto(
                    "https://www.amazon.jobs/en/search",
                    wait_until="domcontentloaded",
                    timeout=45_000,
                )
            except Exception:
                pass
            await page.wait_for_timeout(2000)

            # Fetch the API from within the browser context (reuses session cookies)
            result = await page.evaluate(
                """async (url) => {
                    try {
                        const resp = await fetch(url, {
                            headers: {
                                "Accept": "application/json, text/javascript, */*; q=0.01",
                                "X-Requested-With": "XMLHttpRequest"
                            },
                            credentials: "include"
                        });
                        return await resp.text();
                    } catch(e) {
                        return null;
                    }
                }""",
                api_url,
            )
            captured_json = result
            await browser.close()
    except Exception as e:
        print(f"    Amazon Playwright error: {e}")
        return []

    if not captured_json:
        return []

    jobs = []
    try:
        data = json.loads(captured_json)
        for j in data.get("jobs", []):
            # Post-filter: US jobs only
            if j.get("country_code", "").upper() not in ("USA", "US"):
                continue
            job_path = j.get("job_path", "")
            job_url = (AMAZON_BASE + job_path) if job_path else ""
            city = j.get("city", "")
            state = j.get("state", "")
            location = f"{city}, {state}".strip(", ") if city or state else "United States"
            jobs.append({
                "title": j.get("title", ""),
                "company": j.get("company_name", "Amazon"),
                "location": location,
                "url": job_url,
                "description": j.get("description", "") or j.get("basic_qualifications", ""),
                "posted_date": (j.get("posted_date") or "")[:10] or None,
                "salary": None,
            })
    except Exception as e:
        print(f"    Amazon JSON parse error: {e}")

    return jobs


# ── Apple Jobs ─────────────────────────────────────────────────────────────────

APPLE_SEARCH_URL = (
    "https://jobs.apple.com/en-us/search"
    "?team=machine-learning-and-ai"
    "&team=engineering-software"
    "&team=information-systems-and-technology"
)

APPLE_QUERIES = ["data engineer", "machine learning", "AI engineer"]

async def _scrape_apple_playwright(query: str) -> List[Dict]:
    """Scrape Apple Jobs via Playwright."""
    url = f"https://jobs.apple.com/en-us/search?search={query.replace(' ', '+')}&sort=newest&filters=countryID%3DUSA"
    html = await _playwright_fetch_json(url, timeout_ms=30_000)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                items = data
            elif data.get("@type") in ("ItemList", "JobPosting"):
                items = [data] if data.get("@type") == "JobPosting" else [
                    e.get("item", e) for e in data.get("itemListElement", [])
                ]
            else:
                items = []
            for item in items:
                if item.get("@type") != "JobPosting":
                    continue
                loc = item.get("jobLocation", {})
                if isinstance(loc, list):
                    loc = loc[0] if loc else {}
                addr = loc.get("address", {})
                location = (
                    addr.get("addressLocality", "")
                    + (", " + addr.get("addressRegion", "") if addr.get("addressRegion") else "")
                )
                jobs.append({
                    "title": item.get("title", ""),
                    "company": "Apple",
                    "location": location or "United States",
                    "url": item.get("url", ""),
                    "description": BeautifulSoup(item.get("description", ""), "html.parser").get_text(" ", strip=True),
                    "posted_date": (item.get("datePosted") or "")[:10] or None,
                    "salary": None,
                })
        except Exception:
            continue

    return jobs


# ── Microsoft Jobs ─────────────────────────────────────────────────────────────

MSFT_SEARCH_URL = (
    "https://jobs.careers.microsoft.com/global/en/search"
    "?q={query}&lc=en-us&d=Software+Engineering&d=Data+Sciences"
)

async def _scrape_microsoft_playwright(query: str) -> List[Dict]:
    """Scrape Microsoft Careers via Playwright."""
    url = MSFT_SEARCH_URL.format(query=query.replace(" ", "+"))
    html = await _playwright_fetch_json(url, timeout_ms=30_000)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") != "JobPosting":
                    continue
                loc = item.get("jobLocation", {})
                if isinstance(loc, list):
                    loc = loc[0] if loc else {}
                addr = loc.get("address", {})
                location = (
                    addr.get("addressLocality", "")
                    + (", " + addr.get("addressRegion", "") if addr.get("addressRegion") else "")
                )
                jobs.append({
                    "title": item.get("title", ""),
                    "company": "Microsoft",
                    "location": location or "United States",
                    "url": item.get("url", ""),
                    "description": BeautifulSoup(item.get("description", ""), "html.parser").get_text(" ", strip=True),
                    "posted_date": (item.get("datePosted") or "")[:10] or None,
                    "salary": None,
                })
        except Exception:
            continue

    return jobs


# ── Main DirectScraper class ───────────────────────────────────────────────────

class DirectScraper(BaseScraper):
    """
    Scraper for companies with no standard ATS.
    Routes Databricks/Snowflake to their existing ATS APIs.
    Uses Playwright for Google/Meta/Amazon/Apple/Microsoft.
    """

    def __init__(self):
        super().__init__()
        self._company_scraper = CompanyScraper()

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

        # ── Playwright-based scrapers ──────────────────────────────────────────
        scraper_fn = {
            "direct_google_careers": _scrape_google_playwright,
            "direct_meta_careers":   _scrape_meta_playwright,
            "direct_amazon_jobs":    _scrape_amazon_playwright,
            "direct_apple_jobs":     _scrape_apple_playwright,
            "direct_microsoft_careers": _scrape_microsoft_playwright,
        }.get(ats_type)

        if scraper_fn is None:
            print(f"    [{name}] No scraper for ats_type={ats_type!r} — skipping")
            return []

        all_raw: List[Dict] = []
        for query in SEARCH_QUERIES:
            try:
                results = await scraper_fn(query)
                all_raw.extend(results)
            except Exception as e:
                print(f"    [{name}] Error scraping '{query}': {e}")
            await asyncio.sleep(2)  # polite pause between queries

        deduped = _dedup(all_raw)
        return [
            self.normalize_job_data(j, f"direct:{name.lower().replace(' ', '_')}")
            for j in deduped
            if j.get("title")
        ]

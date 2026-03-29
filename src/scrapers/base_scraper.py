from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import asyncio
import hashlib
import json
import os
from datetime import datetime
from openai import AsyncOpenAI, RateLimitError
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

_openai_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


class CrawlerWrapper:
    """
    Uses Playwright to render pages and OpenAI to extract structured job data.
    Provides the same interface as the old Claw client:
        result = await self.claw.scrape(url=..., instructions=...)
        jobs = result.get('jobs', [])
    """

    async def _fetch_html(self, url: str) -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_extra_http_headers({
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                })
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                # Give JS-heavy pages a moment to render
                await page.wait_for_timeout(3000)
                content = await page.content()
                return content
            except Exception as e:
                print(f"  Playwright error fetching {url}: {e}")
                return ""
            finally:
                await browser.close()

    async def _extract_jobs(self, html: str, instructions: str) -> List[Dict]:
        # Strip to avoid token limits — 60k chars covers most job listing pages
        html_snippet = html[:60000]

        client = get_openai_client()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a job listing extractor. Given raw HTML from a careers page, "
                    "extract job listings and return them as a JSON object with a 'jobs' key "
                    "containing an array. Each job object should have these fields: "
                    "title (string), company (string), location (string), "
                    "salary (string or null), url (string or null), "
                    "description (string or null), posted_date (string or null). "
                    "Return ONLY valid JSON, no explanation."
                ),
            },
            {
                "role": "user",
                "content": f"{instructions}\n\nHTML:\n{html_snippet}",
            },
        ]

        for attempt in range(5):
            try:
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                content = response.choices[0].message.content
                data = json.loads(content)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "jobs" in data:
                    return data["jobs"]
                return []
            except RateLimitError as e:
                wait = 10 * (attempt + 1)
                print(f"  Rate limit hit, retrying in {wait}s... (attempt {attempt + 1}/5)")
                await asyncio.sleep(wait)
        return []

    async def scrape(self, url: str, instructions: str) -> Dict[str, Any]:
        try:
            html = await self._fetch_html(url)
            if not html:
                return {"jobs": []}
            jobs = await self._extract_jobs(html, instructions)
            return {"jobs": jobs}
        except Exception as e:
            print(f"  Scrape error for {url}: {e}")
            return {"jobs": []}


class BaseScraper(ABC):
    def __init__(self):
        self.claw = CrawlerWrapper()

    @abstractmethod
    async def scrape(self, url: str, **kwargs) -> List[Dict[str, Any]]:
        pass

    def generate_job_id(self, company: str, title: str, url: str) -> str:
        unique_string = f"{company}_{title}_{url}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def parse_salary(self, salary_text: str) -> tuple:
        if not salary_text:
            return None, None

        salary_text = (
            salary_text.replace(",", "")
            .replace("$", "")
            .replace("k", "000")
            .replace("K", "000")
        )

        try:
            # Normalize em dash and en dash to hyphen
            salary_text = salary_text.replace("–", "-").replace("—", "-")
            if "-" in salary_text:
                parts = salary_text.split("-")
                min_sal = int("".join(filter(str.isdigit, parts[0])))
                max_sal = int("".join(filter(str.isdigit, parts[1])))
                return min_sal, max_sal
            else:
                salary = int("".join(filter(str.isdigit, salary_text)))
                return salary, salary
        except Exception:
            return None, None

    def parse_date(self, date_str) -> datetime | None:
        if not date_str or not isinstance(date_str, str):
            return None
        date_str = date_str.strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(date_str[:26], fmt)
            except ValueError:
                continue
        # fallback: just parse YYYY-MM-DD prefix
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            return None

    def is_remote(self, location: str) -> bool:
        if not location:
            return False
        return any(
            kw in location.lower()
            for kw in ["remote", "anywhere", "work from home", "wfh"]
        )

    def normalize_job_data(self, raw_job: Dict[str, Any], source: str) -> Dict[str, Any]:
        job_id = self.generate_job_id(
            raw_job.get("company", ""),
            raw_job.get("title", ""),
            raw_job.get("url", ""),
        )
        salary_min, salary_max = self.parse_salary(raw_job.get("salary", ""))

        return {
            "job_id": job_id,
            "title": raw_job.get("title", ""),
            "company": raw_job.get("company", ""),
            "location": raw_job.get("location", ""),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "description": raw_job.get("description", ""),
            "url": raw_job.get("url", ""),
            "source": source,
            "posted_date": self.parse_date(raw_job.get("posted_date")),
            "is_remote": self.is_remote(raw_job.get("location", "")),
            "extra_data": raw_job.get("metadata", {}),
        }

from typing import List, Dict, Any
from .base_scraper import BaseScraper
from bs4 import BeautifulSoup
import aiohttp
import asyncio

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# f_TPR=r604800  = last 7 days
# f_TPR=r1209600 = last 14 days
LINKEDIN_SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    "?keywords={keywords}&location=United+States&f_TPR=r1209600&start={start}"
)

# Public job detail endpoint — no auth needed, returns HTML with description
LINKEDIN_JOB_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_num_id}"


def _extract_linkedin_job_id(url: str) -> str | None:
    """Extract numeric job ID from a LinkedIn job URL."""
    import re
    # Matches /view/1234567 OR /view/some-slug-1234567
    m = re.search(r"/view/(?:[^/]*?-)?(\d+)(?:[/?]|$)", url)
    return m.group(1) if m else None


class JobBoardScraper(BaseScraper):

    async def _fetch_linkedin_description(
        self, session: aiohttp.ClientSession, job: Dict[str, Any]
    ) -> str:
        """Fetch full description for one LinkedIn job via public detail API."""
        job_num_id = _extract_linkedin_job_id(job.get("url", ""))
        if not job_num_id:
            return ""
        url = LINKEDIN_JOB_URL.format(job_num_id=job_num_id)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return ""
                html = await resp.text()
            soup = BeautifulSoup(html, "lxml")
            desc_el = soup.find("div", class_="show-more-less-html__markup")
            if desc_el:
                return desc_el.get_text(separator="\n", strip=True)
            # Fallback: grab description container by common class
            desc_el = soup.find("div", {"class": lambda c: c and "description" in c})
            return desc_el.get_text(separator="\n", strip=True) if desc_el else ""
        except Exception:
            return ""

    async def scrape_linkedin(self, search_params: Dict[str, str]) -> List[Dict[str, Any]]:
        keywords = search_params.get("keywords", "").replace(" ", "+")
        jobs = []

        async with aiohttp.ClientSession(headers=HEADERS) as session:
            for start in range(0, 75, 25):  # fetch up to 75 results per keyword (3 pages)
                url = LINKEDIN_SEARCH_URL.format(keywords=keywords, start=start)
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            break
                        html = await resp.text()

                    soup = BeautifulSoup(html, "lxml")
                    cards = soup.find_all("li")
                    if not cards:
                        break

                    for card in cards:
                        title_el = card.find("h3", class_="base-search-card__title")
                        company_el = card.find("h4", class_="base-search-card__subtitle")
                        location_el = card.find("span", class_="job-search-card__location")
                        link_el = card.find("a", class_="base-card__full-link")
                        date_el = card.find("time")

                        title = title_el.get_text(strip=True) if title_el else ""
                        company = company_el.get_text(strip=True) if company_el else ""
                        location = location_el.get_text(strip=True) if location_el else ""
                        url_job = link_el["href"].split("?")[0] if link_el and link_el.get("href") else ""
                        posted = date_el.get("datetime") if date_el else None

                        if title and url_job:
                            jobs.append({
                                "title": title,
                                "company": company,
                                "location": location,
                                "url": url_job,
                                "description": "",
                                "posted_date": posted,
                                "salary": None,
                            })
                except Exception as e:
                    print(f"  LinkedIn fetch error: {e}")
                    break

                await asyncio.sleep(1)  # be polite

            # Fetch descriptions concurrently in batches of 10
            print(f"  Fetching descriptions for {len(jobs)} LinkedIn jobs...")
            sem = asyncio.Semaphore(10)

            async def fetch_with_sem(job):
                async with sem:
                    desc = await self._fetch_linkedin_description(session, job)
                    job["description"] = desc
                    await asyncio.sleep(0.3)

            await asyncio.gather(*[fetch_with_sem(j) for j in jobs])

        filled = sum(1 for j in jobs if j["description"])
        print(f"  LinkedIn descriptions: {filled}/{len(jobs)} fetched")
        return jobs

    async def scrape(self, board_name: str, search_params: Dict[str, str], **kwargs) -> List[Dict[str, Any]]:
        if board_name.lower() == "linkedin":
            raw_jobs = await self.scrape_linkedin(search_params)
        else:
            return []

        return [self.normalize_job_data(j, f"job_board_{board_name.lower()}") for j in raw_jobs]

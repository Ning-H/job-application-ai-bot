from typing import List, Dict, Any
import asyncio
from datetime import datetime
from src.scrapers.company_scraper import CompanyScraper
from src.scrapers.job_board_scraper import JobBoardScraper
from src.filters import JobFilter
from src.llm_scorer import LLMScorer
from src.models import Job, CrawlLog, get_session
from src.config_loader import config
from src.scrapers.base_scraper import get_openai_client
from sqlalchemy.exc import IntegrityError


class JobCrawler:
    def __init__(self):
        self.company_scraper = CompanyScraper()
        self.job_board_scraper = JobBoardScraper()
        self.job_filter = JobFilter()
        self.llm_scorer = LLMScorer()
        self.session = get_session()

    # ── company crawling ──────────────────────────────────────────────────────

    async def crawl_greenhouse(self, company: Dict) -> List[Dict[str, Any]]:
        name = company["name"]
        print(f"  [Greenhouse] {name}...")
        try:
            jobs = await self.company_scraper.scrape(
                company_name=name,
                ats_type="greenhouse",
                board_id=company["board_id"],
            )
            print(f"  → {len(jobs)} jobs at {name}")
            return jobs
        except Exception as e:
            print(f"  Error {name}: {e}")
            return []

    async def crawl_lever(self, company: Dict) -> List[Dict[str, Any]]:
        name = company["name"]
        print(f"  [Lever] {name}...")
        try:
            jobs = await self.company_scraper.scrape(
                company_name=name,
                ats_type="lever",
                board_id=company["board_id"],
            )
            print(f"  → {len(jobs)} jobs at {name}")
            return jobs
        except Exception as e:
            print(f"  Error {name}: {e}")
            return []

    async def crawl_ashby(self, company: Dict) -> List[Dict[str, Any]]:
        name = company["name"]
        print(f"  [Ashby] {name}...")
        try:
            jobs = await self.company_scraper.scrape(
                company_name=name,
                ats_type="ashby",
                board_id=company["board_id"],
            )
            print(f"  → {len(jobs)} jobs at {name}")
            return jobs
        except Exception as e:
            print(f"  Error {name}: {e}")
            return []

    async def crawl_all_companies(self) -> List[Dict[str, Any]]:
        all_companies = config.config.get("target_companies", {})
        all_jobs = []

        # Greenhouse — run concurrently (API calls, fast)
        greenhouse_list = all_companies.get("greenhouse", [])
        if greenhouse_list:
            print(f"\nCrawling {len(greenhouse_list)} Greenhouse companies...")
            results = await asyncio.gather(
                *[self.crawl_greenhouse(c) for c in greenhouse_list],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, list):
                    all_jobs.extend(r)

        # Lever — run concurrently
        lever_list = all_companies.get("lever", [])
        if lever_list:
            print(f"\nCrawling {len(lever_list)} Lever companies...")
            results = await asyncio.gather(
                *[self.crawl_lever(c) for c in lever_list],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, list):
                    all_jobs.extend(r)

        # Ashby — run concurrently
        ashby_list = all_companies.get("ashby", [])
        if ashby_list:
            print(f"\nCrawling {len(ashby_list)} Ashby companies...")
            results = await asyncio.gather(
                *[self.crawl_ashby(c) for c in ashby_list],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, list):
                    all_jobs.extend(r)

        return all_jobs

    # ── job board crawling ────────────────────────────────────────────────────

    async def crawl_linkedin(self) -> List[Dict[str, Any]]:
        target_titles = config.get_target_titles()
        all_jobs = []

        print(f"\nCrawling LinkedIn for {len(target_titles)} job titles...")
        for title in target_titles:
            print(f"  LinkedIn: '{title}'...")
            try:
                jobs = await self.job_board_scraper.scrape(
                    "LinkedIn", {"keywords": title}
                )
                print(f"  → {len(jobs)} results")
                all_jobs.extend(jobs)
            except Exception as e:
                print(f"  LinkedIn error for '{title}': {e}")
            await asyncio.sleep(2)  # rate limit courtesy

        return all_jobs

    # ── db ────────────────────────────────────────────────────────────────────

    def save_jobs_to_db(self, jobs: List[Dict[str, Any]]) -> tuple:
        new_jobs = 0
        for job_data in jobs:
            try:
                if self.session.query(Job).filter_by(job_id=job_data["job_id"]).first():
                    continue
                self.session.add(Job(**job_data))
                self.session.commit()
                new_jobs += 1
            except IntegrityError:
                self.session.rollback()
            except Exception as e:
                print(f"  DB save error: {e}")
                self.session.rollback()
        return new_jobs, len(jobs)

    async def generate_summaries(self):
        """Generate 2-3 sentence AI summaries for scored jobs that don't have one yet."""
        from src.filters import MIN_SKILLS_MATCH
        jobs_without_summary = self.session.query(Job).filter(
            Job.summary == None,
            Job.description != None,
            Job.description != "",
            Job.overall_score != None,
            Job.skills_match_score >= MIN_SKILLS_MATCH,
        ).limit(50).all()

        if not jobs_without_summary:
            return

        client = get_openai_client()

        async def summarize(job: Job):
            try:
                resp = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{
                        "role": "user",
                        "content": (
                            f"Job title: {job.title}\nCompany: {job.company}\n\n"
                            f"Description:\n{(job.description or '')[:3000]}\n\n"
                            "Write 2-3 sentences summarizing: what this role does day-to-day, "
                            "what team/department it sits in, and the main technical focus. "
                            "Be specific and concise. No filler phrases."
                        )
                    }],
                    max_tokens=150,
                    temperature=0.3,
                )
                job.summary = resp.choices[0].message.content.strip()
                self.session.commit()
            except Exception as e:
                print(f"  Summary error for {job.title}: {e}")

        # Process in batches of 10 to avoid rate limits
        for i in range(0, len(jobs_without_summary), 10):
            batch = jobs_without_summary[i:i+10]
            await asyncio.gather(*[summarize(j) for j in batch])
            if i + 10 < len(jobs_without_summary):
                await asyncio.sleep(2)

        print(f"  Summaries generated for {len(jobs_without_summary)} jobs")

    async def backfill_linkedin_descriptions(self):
        """Fetch descriptions for LinkedIn jobs in DB that have empty descriptions."""
        from src.scrapers.job_board_scraper import _extract_linkedin_job_id
        jobs_missing = self.session.query(Job).filter(
            Job.source.like("%linkedin%"),
            (Job.description == None) | (Job.description == ""),
        ).all()
        if not jobs_missing:
            return
        print(f"  Backfilling descriptions for {len(jobs_missing)} LinkedIn jobs...")
        import aiohttp
        from bs4 import BeautifulSoup
        HEADERS = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        LINKEDIN_JOB_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_num_id}"
        sem = asyncio.Semaphore(10)
        updated = 0

        async def fetch_one(job, session):
            nonlocal updated
            job_num_id = _extract_linkedin_job_id(job.url or "")
            if not job_num_id:
                return
            url = LINKEDIN_JOB_URL.format(job_num_id=job_num_id)
            async with sem:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            return
                        html = await resp.text()
                    await asyncio.sleep(0.3)
                except Exception:
                    return
            soup = BeautifulSoup(html, "lxml")
            desc_el = soup.find("div", class_="show-more-less-html__markup")
            if not desc_el:
                desc_el = soup.find("div", {"class": lambda c: c and "description" in c})
            if desc_el:
                job.description = desc_el.get_text(separator="\n", strip=True)
                updated += 1

        async with aiohttp.ClientSession(headers=HEADERS) as http_session:
            await asyncio.gather(*[fetch_one(j, http_session) for j in jobs_missing])

        if updated:
            self.session.commit()
            print(f"  LinkedIn descriptions backfilled: {updated}/{len(jobs_missing)}")

    async def backfill_salaries(self):
        """Re-extract salary from description for DB jobs that are missing salary data."""
        from src.scrapers.company_scraper import _extract_salary
        jobs_missing_salary = self.session.query(Job).filter(
            Job.salary_min == None,
            Job.description != None,
            Job.description != "",
        ).all()
        if not jobs_missing_salary:
            return
        updated = 0
        for job in jobs_missing_salary:
            salary_text = _extract_salary(job.description)
            if salary_text:
                from src.scrapers.base_scraper import BaseScraper
                # Use a temp instance just for parse_salary
                class _P(BaseScraper):
                    async def scrape(self, url, **kw): return []
                parser = _P()
                sal_min, sal_max = parser.parse_salary(salary_text)
                if sal_min:
                    job.salary_min = sal_min
                    job.salary_max = sal_max
                    updated += 1
        if updated:
            self.session.commit()
            print(f"  Salary backfilled for {updated} jobs")

    def log_crawl(self, source: str, jobs_found: int, new_jobs: int,
                  success: bool = True, error: str = None):
        log = CrawlLog(
            source=source,
            jobs_found=jobs_found,
            new_jobs=new_jobs,
            success=success,
            error_message=error,
        )
        self.session.add(log)
        self.session.commit()

    # ── main ──────────────────────────────────────────────────────────────────

    async def run_full_crawl(self):
        print("\n" + "=" * 55)
        print("JOB CRAWL STARTED —", datetime.now().strftime("%Y-%m-%d %H:%M"))
        print("=" * 55)

        company_jobs = await self.crawl_all_companies()
        print(f"\nTotal from companies: {len(company_jobs)}")

        linkedin_jobs = await self.crawl_linkedin()
        print(f"Total from LinkedIn: {len(linkedin_jobs)}")

        all_jobs = company_jobs + linkedin_jobs
        print(f"\nTotal collected: {len(all_jobs)}")

        print("\nFiltering...")
        filtered = self.job_filter.filter_jobs(all_jobs)
        print(f"After filter: {len(filtered)}")

        print("Scoring with LLM...")
        ranked = await self.llm_scorer.score_jobs(filtered)

        print("Applying score threshold...")
        ranked = self.job_filter.apply_score_threshold(ranked)
        print(f"After score threshold: {len(ranked)}")

        print("Saving to DB...")
        new_count, total = self.save_jobs_to_db(ranked)
        print(f"New jobs saved: {new_count} / {total}")

        await self.backfill_linkedin_descriptions()
        await self.backfill_salaries()

        self.log_crawl("full_crawl", total, new_count)

        print("\n" + "=" * 55)
        if ranked:
            print("TOP 5 JOBS:")
            for i, job in enumerate(ranked[:5], 1):
                flag = " ★ REVIEW" if job.get("requires_human_review") else ""
                print(f"\n{i}. {job['title']} @ {job['company']}{flag}")
                print(f"   Score: {job['overall_score']:.2f}  |  {job['location']}")
                print(f"   {job['url']}")

        return ranked

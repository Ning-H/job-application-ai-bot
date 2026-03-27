from typing import List, Dict, Any
import asyncio
from datetime import datetime
from src.scrapers.company_scraper import CompanyScraper
from src.scrapers.job_board_scraper import JobBoardScraper
from src.filters import JobFilter
from src.ranker import JobRanker
from src.models import Job, Company, CrawlLog, get_session
from src.config_loader import config
from sqlalchemy.exc import IntegrityError

class JobCrawler:
    def __init__(self):
        self.company_scraper = CompanyScraper()
        self.job_board_scraper = JobBoardScraper()
        self.job_filter = JobFilter()
        self.job_ranker = JobRanker()
        self.session = get_session()
    
    async def crawl_company(self, company: Dict[str, str]) -> List[Dict[str, Any]]:
        company_name = company.get('name')
        careers_url = company.get('careers_url')
        
        print(f"Crawling {company_name}...")
        
        try:
            jobs = await self.company_scraper.scrape(careers_url, company_name=company_name)
            print(f"Found {len(jobs)} jobs at {company_name}")
            return jobs
        except Exception as e:
            print(f"Error crawling {company_name}: {e}")
            return []
    
    async def crawl_job_board(self, board: Dict[str, Any], title: str) -> List[Dict[str, Any]]:
        board_name = board.get('name')
        
        print(f"Crawling {board_name} for '{title}'...")
        
        try:
            search_params = {
                'keywords': title,
                'location': 'United States'
            }
            jobs = await self.job_board_scraper.scrape(board_name, search_params)
            print(f"Found {len(jobs)} jobs on {board_name}")
            return jobs
        except Exception as e:
            print(f"Error crawling {board_name}: {e}")
            return []
    
    async def crawl_all_companies(self) -> List[Dict[str, Any]]:
        companies = config.get_all_companies()
        all_jobs = []
        
        tasks = [self.crawl_company(company) for company in companies]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                all_jobs.extend(result)
        
        return all_jobs
    
    async def crawl_all_job_boards(self) -> List[Dict[str, Any]]:
        job_boards = config.get_job_boards()
        target_titles = config.get_target_titles()
        all_jobs = []
        
        tasks = []
        for board in job_boards:
            for title in target_titles[:3]:
                tasks.append(self.crawl_job_board(board, title))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                all_jobs.extend(result)
        
        return all_jobs
    
    def save_jobs_to_db(self, jobs: List[Dict[str, Any]]) -> tuple:
        new_jobs = 0
        total_jobs = len(jobs)
        
        for job_data in jobs:
            try:
                existing_job = self.session.query(Job).filter_by(job_id=job_data['job_id']).first()
                
                if existing_job:
                    continue
                
                job = Job(**job_data)
                self.session.add(job)
                self.session.commit()
                new_jobs += 1
                
            except IntegrityError:
                self.session.rollback()
                continue
            except Exception as e:
                print(f"Error saving job: {e}")
                self.session.rollback()
                continue
        
        return new_jobs, total_jobs
    
    def log_crawl(self, source: str, jobs_found: int, new_jobs: int, success: bool = True, error: str = None):
        log = CrawlLog(
            source=source,
            jobs_found=jobs_found,
            new_jobs=new_jobs,
            success=success,
            error_message=error
        )
        self.session.add(log)
        self.session.commit()
    
    async def run_full_crawl(self):
        print("Starting full job crawl...")
        print("=" * 50)
        
        company_jobs = await self.crawl_all_companies()
        print(f"\nTotal jobs from companies: {len(company_jobs)}")
        
        job_board_jobs = await self.crawl_all_job_boards()
        print(f"Total jobs from job boards: {len(job_board_jobs)}")
        
        all_jobs = company_jobs + job_board_jobs
        print(f"\nTotal jobs collected: {len(all_jobs)}")
        
        print("\nFiltering jobs...")
        filtered_jobs = self.job_filter.filter_jobs(all_jobs)
        print(f"Jobs after filtering: {len(filtered_jobs)}")
        
        print("\nRanking jobs...")
        ranked_jobs = self.job_ranker.rank_jobs(filtered_jobs)
        
        print("\nSaving jobs to database...")
        new_jobs, total_jobs = self.save_jobs_to_db(ranked_jobs)
        print(f"New jobs saved: {new_jobs} out of {total_jobs}")
        
        self.log_crawl('full_crawl', total_jobs, new_jobs, success=True)
        
        print("\n" + "=" * 50)
        print("Crawl completed!")
        
        if ranked_jobs:
            print("\nTop 5 jobs:")
            for i, job in enumerate(ranked_jobs[:5], 1):
                print(f"\n{i}. {job['title']} at {job['company']}")
                print(f"   Score: {job['overall_score']:.2f}")
                print(f"   Location: {job['location']}")
                print(f"   URL: {job['url']}")
                if job.get('requires_human_review'):
                    print("   ⭐ REQUIRES HUMAN REVIEW")
                elif job.get('auto_apply_eligible'):
                    print("   ✓ Auto-apply eligible")
        
        return ranked_jobs

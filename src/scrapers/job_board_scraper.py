from typing import List, Dict, Any
from .base_scraper import BaseScraper
import asyncio

class JobBoardScraper(BaseScraper):
    async def scrape_linkedin(self, search_params: Dict[str, str]) -> List[Dict[str, Any]]:
        jobs = []
        try:
            keywords = search_params.get('keywords', 'Principal Data Engineer')
            location = search_params.get('location', 'United States')
            
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={keywords}&location={location}"
            
            result = await self.claw.scrape(
                url=search_url,
                instructions=f"Extract job listings for '{keywords}' positions. Get job title, company name, location, salary if shown, job URL, and brief description. Focus on senior and principal level positions."
            )
            
            for job in result.get('jobs', []):
                jobs.append({
                    'title': job.get('title'),
                    'company': job.get('company'),
                    'location': job.get('location'),
                    'salary': job.get('salary'),
                    'url': job.get('url'),
                    'description': job.get('description', ''),
                    'posted_date': job.get('posted_date'),
                })
        except Exception as e:
            print(f"Error scraping LinkedIn: {e}")
        
        return jobs
    
    async def scrape_indeed(self, search_params: Dict[str, str]) -> List[Dict[str, Any]]:
        jobs = []
        try:
            keywords = search_params.get('keywords', 'Principal Data Engineer')
            location = search_params.get('location', 'United States')
            
            search_url = f"https://www.indeed.com/jobs?q={keywords}&l={location}"
            
            result = await self.claw.scrape(
                url=search_url,
                instructions=f"Extract job postings for '{keywords}'. Collect job title, company, location, salary range if available, job URL, and description snippet."
            )
            
            for job in result.get('jobs', []):
                jobs.append({
                    'title': job.get('title'),
                    'company': job.get('company'),
                    'location': job.get('location'),
                    'salary': job.get('salary'),
                    'url': job.get('url'),
                    'description': job.get('description', ''),
                    'posted_date': job.get('posted_date'),
                })
        except Exception as e:
            print(f"Error scraping Indeed: {e}")
        
        return jobs
    
    async def scrape_glassdoor(self, search_params: Dict[str, str]) -> List[Dict[str, Any]]:
        jobs = []
        try:
            keywords = search_params.get('keywords', 'Principal Data Engineer')
            location = search_params.get('location', 'United States')
            
            search_url = f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={keywords}&locT=N&locId=1"
            
            result = await self.claw.scrape(
                url=search_url,
                instructions=f"Extract job listings for '{keywords}' roles. Get title, company, location, salary estimate, job link, and description."
            )
            
            for job in result.get('jobs', []):
                jobs.append({
                    'title': job.get('title'),
                    'company': job.get('company'),
                    'location': job.get('location'),
                    'salary': job.get('salary'),
                    'url': job.get('url'),
                    'description': job.get('description', ''),
                    'posted_date': job.get('posted_date'),
                })
        except Exception as e:
            print(f"Error scraping Glassdoor: {e}")
        
        return jobs
    
    async def scrape(self, board_name: str, search_params: Dict[str, str], **kwargs) -> List[Dict[str, Any]]:
        if board_name.lower() == 'linkedin':
            raw_jobs = await self.scrape_linkedin(search_params)
        elif board_name.lower() == 'indeed':
            raw_jobs = await self.scrape_indeed(search_params)
        elif board_name.lower() == 'glassdoor':
            raw_jobs = await self.scrape_glassdoor(search_params)
        else:
            return []
        
        normalized_jobs = []
        for job in raw_jobs:
            normalized_job = self.normalize_job_data(job, f"job_board_{board_name.lower()}")
            normalized_jobs.append(normalized_job)
        
        return normalized_jobs

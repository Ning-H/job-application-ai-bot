from typing import List, Dict, Any
from .base_scraper import BaseScraper
from bs4 import BeautifulSoup
import asyncio

class CompanyScraper(BaseScraper):
    async def scrape_google(self, url: str) -> List[Dict[str, Any]]:
        jobs = []
        try:
            result = await self.claw.scrape(
                url=url,
                instructions="Extract all job listings with title, location, and job posting URL. Focus on data engineering and AI roles."
            )
            
            for job in result.get('jobs', []):
                jobs.append({
                    'title': job.get('title'),
                    'company': 'Google',
                    'location': job.get('location'),
                    'url': job.get('url'),
                    'description': job.get('description', ''),
                    'posted_date': job.get('posted_date'),
                })
        except Exception as e:
            print(f"Error scraping Google careers: {e}")
        
        return jobs
    
    async def scrape_meta(self, url: str) -> List[Dict[str, Any]]:
        jobs = []
        try:
            result = await self.claw.scrape(
                url=url,
                instructions="Extract all job listings including title, location, and apply URL. Look for data engineering and AI positions."
            )
            
            for job in result.get('jobs', []):
                jobs.append({
                    'title': job.get('title'),
                    'company': 'Meta',
                    'location': job.get('location'),
                    'url': job.get('url'),
                    'description': job.get('description', ''),
                    'posted_date': job.get('posted_date'),
                })
        except Exception as e:
            print(f"Error scraping Meta careers: {e}")
        
        return jobs
    
    async def scrape_generic_company(self, company_name: str, url: str) -> List[Dict[str, Any]]:
        jobs = []
        try:
            result = await self.claw.scrape(
                url=url,
                instructions=f"Extract all job listings from {company_name} careers page. Get job title, location, salary if available, job URL, and description. Focus on senior data engineering and AI roles."
            )
            
            for job in result.get('jobs', []):
                jobs.append({
                    'title': job.get('title'),
                    'company': company_name,
                    'location': job.get('location'),
                    'salary': job.get('salary'),
                    'url': job.get('url'),
                    'description': job.get('description', ''),
                    'posted_date': job.get('posted_date'),
                })
        except Exception as e:
            print(f"Error scraping {company_name} careers: {e}")
        
        return jobs
    
    async def scrape(self, url: str, company_name: str = None, **kwargs) -> List[Dict[str, Any]]:
        if 'google.com' in url:
            raw_jobs = await self.scrape_google(url)
        elif 'meta' in url.lower():
            raw_jobs = await self.scrape_meta(url)
        else:
            raw_jobs = await self.scrape_generic_company(company_name or 'Unknown', url)
        
        normalized_jobs = []
        for job in raw_jobs:
            normalized_job = self.normalize_job_data(job, f"company_{company_name or 'unknown'}")
            normalized_jobs.append(normalized_job)
        
        return normalized_jobs

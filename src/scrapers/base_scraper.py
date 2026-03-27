from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import datetime
import hashlib
from claw import Claw

class BaseScraper(ABC):
    def __init__(self):
        self.claw = Claw()
    
    @abstractmethod
    async def scrape(self, url: str, **kwargs) -> List[Dict[str, Any]]:
        pass
    
    def generate_job_id(self, company: str, title: str, url: str) -> str:
        unique_string = f"{company}_{title}_{url}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def parse_salary(self, salary_text: str) -> tuple:
        if not salary_text:
            return None, None
        
        salary_text = salary_text.replace(',', '').replace('$', '').replace('k', '000').replace('K', '000')
        
        try:
            if '-' in salary_text:
                parts = salary_text.split('-')
                min_sal = int(''.join(filter(str.isdigit, parts[0])))
                max_sal = int(''.join(filter(str.isdigit, parts[1])))
                return min_sal, max_sal
            else:
                salary = int(''.join(filter(str.isdigit, salary_text)))
                return salary, salary
        except:
            return None, None
    
    def is_remote(self, location: str) -> bool:
        if not location:
            return False
        location_lower = location.lower()
        return any(keyword in location_lower for keyword in ['remote', 'anywhere', 'work from home', 'wfh'])
    
    def normalize_job_data(self, raw_job: Dict[str, Any], source: str) -> Dict[str, Any]:
        job_id = self.generate_job_id(
            raw_job.get('company', ''),
            raw_job.get('title', ''),
            raw_job.get('url', '')
        )
        
        salary_min, salary_max = self.parse_salary(raw_job.get('salary', ''))
        
        return {
            'job_id': job_id,
            'title': raw_job.get('title', ''),
            'company': raw_job.get('company', ''),
            'location': raw_job.get('location', ''),
            'salary_min': salary_min,
            'salary_max': salary_max,
            'description': raw_job.get('description', ''),
            'url': raw_job.get('url', ''),
            'source': source,
            'posted_date': raw_job.get('posted_date'),
            'is_remote': self.is_remote(raw_job.get('location', '')),
            'metadata': raw_job.get('metadata', {})
        }

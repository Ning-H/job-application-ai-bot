from typing import List, Dict, Any
from src.config_loader import config
import re

class JobFilter:
    def __init__(self):
        self.target_titles = config.get_target_titles()
        self.location_prefs = config.get_location_preferences()
    
    def matches_title(self, job_title: str) -> bool:
        job_title_lower = job_title.lower()
        
        for target_title in self.target_titles:
            target_lower = target_title.lower()
            
            if target_lower in job_title_lower:
                return True
            
            keywords = target_lower.split()
            if all(keyword in job_title_lower for keyword in keywords):
                return True
        
        return False
    
    def meets_salary_requirements(self, job: Dict[str, Any]) -> bool:
        salary_min = job.get('salary_min')
        salary_max = job.get('salary_max')
        
        if not salary_min and not salary_max:
            return True
        
        salary = salary_max if salary_max else salary_min
        
        if job.get('is_remote'):
            min_required = self.location_prefs['preferences'][0]['min_salary']
            return salary >= min_required if salary else True
        
        location = job.get('location', '').lower()
        
        if any(city in location for city in ['san francisco', 'palo alto', 'mountain view', 'sunnyvale', 'san jose', 'bay area']):
            min_required = next((p['min_salary'] for p in self.location_prefs['preferences'] if p['type'] == 'bay_area'), 300000)
            return salary >= min_required if salary else True
        
        if any(city in location for city in ['alexandria', 'arlington', 'washington', 'dc', 'maryland', 'virginia']):
            min_required = next((p['min_salary'] for p in self.location_prefs['preferences'] if p['type'] == 'dmv'), 230000)
            return salary >= min_required if salary else True
        
        min_required = next((p['min_salary'] for p in self.location_prefs['preferences'] if p['type'] == 'other'), 250000)
        return salary >= min_required if salary else True
    
    def filter_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered_jobs = []
        
        for job in jobs:
            if not self.matches_title(job.get('title', '')):
                continue
            
            if not self.meets_salary_requirements(job):
                continue
            
            filtered_jobs.append(job)
        
        return filtered_jobs

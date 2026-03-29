from typing import List, Dict, Any
from src.config_loader import config
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import re

class JobRanker:
    def __init__(self):
        self.skills = [skill.lower() for skill in config.get_skills()]
        self.ranking_weights = config.get_ranking_weights()
        self.location_prefs = config.get_location_preferences()
        self.home_address = self.location_prefs.get('home_address', '801 N Fairfax St, Alexandria, VA')
        self.geolocator = Nominatim(user_agent="job_search_app")
        
        self.company_reputation_scores = {
            'google': 1.0, 'meta': 0.95, 'facebook': 0.95, 'amazon': 0.9, 'microsoft': 0.95,
            'apple': 0.95, 'netflix': 0.9, 'databricks': 0.85, 'snowflake': 0.85,
            'openai': 0.95, 'anthropic': 0.9, 'scale ai': 0.85, 'confluent': 0.8,
            'airbnb': 0.85, 'uber': 0.8, 'lyft': 0.75, 'stripe': 0.9, 'square': 0.8,
        }
    
    def calculate_skills_match(self, job: Dict[str, Any]) -> float:
        description = ((job.get('description') or '') + ' ' + (job.get('title') or '')).lower()
        
        matched_skills = 0
        for skill in self.skills:
            if skill in description:
                matched_skills += 1
        
        if len(self.skills) == 0:
            return 0.5
        
        return matched_skills / len(self.skills)
    
    def calculate_salary_score(self, job: Dict[str, Any]) -> float:
        salary_min = job.get('salary_min')
        salary_max = job.get('salary_max')
        
        if not salary_min and not salary_max:
            return 0.5
        
        salary = salary_max if salary_max else salary_min
        
        if job.get('is_remote'):
            min_required = 200000
            if salary >= 250000:
                return 1.0
            elif salary >= min_required:
                return 0.7 + (salary - min_required) / (250000 - min_required) * 0.3
            else:
                return 0.3
        
        location = job.get('location', '').lower()
        
        if any(city in location for city in ['san francisco', 'bay area', 'palo alto', 'mountain view']):
            min_required = 300000
            if salary >= 400000:
                return 1.0
            elif salary >= min_required:
                return 0.7 + (salary - min_required) / (400000 - min_required) * 0.3
            else:
                return 0.3
        
        if any(city in location for city in ['alexandria', 'arlington', 'washington', 'dc']):
            min_required = 230000
            if salary >= 300000:
                return 1.0
            elif salary >= min_required:
                return 0.7 + (salary - min_required) / (300000 - min_required) * 0.3
            else:
                return 0.3
        
        min_required = 250000
        if salary >= 350000:
            return 1.0
        elif salary >= min_required:
            return 0.7 + (salary - min_required) / (350000 - min_required) * 0.3
        else:
            return 0.3
    
    def calculate_company_score(self, job: Dict[str, Any]) -> float:
        company_name = job.get('company', '').lower()
        
        for company, score in self.company_reputation_scores.items():
            if company in company_name:
                return score
        
        return 0.5
    
    def calculate_location_score(self, job: Dict[str, Any]) -> float:
        if job.get('is_remote'):
            return 1.0
        
        location = job.get('location', '').lower()
        
        if any(city in location for city in ['alexandria', 'arlington', 'washington', 'dc', 'virginia', 'maryland']):
            return 0.8
        
        if any(city in location for city in ['san francisco', 'bay area', 'palo alto', 'mountain view', 'san jose']):
            return 0.6
        
        return 0.3
    
    def calculate_overall_score(self, job: Dict[str, Any]) -> Dict[str, float]:
        skills_score = self.calculate_skills_match(job)
        salary_score = self.calculate_salary_score(job)
        company_score = self.calculate_company_score(job)
        location_score = self.calculate_location_score(job)
        
        overall_score = (
            skills_score * self.ranking_weights.get('skills_match', 0.35) +
            salary_score * self.ranking_weights.get('salary_fit', 0.25) +
            company_score * self.ranking_weights.get('company_reputation', 0.20) +
            location_score * self.ranking_weights.get('location_preference', 0.20)
        )
        
        return {
            'skills_match_score': skills_score,
            'salary_score': salary_score,
            'company_score': company_score,
            'location_score': location_score,
            'overall_score': overall_score
        }
    
    def rank_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for job in jobs:
            scores = self.calculate_overall_score(job)
            job.update(scores)
            
            job['requires_human_review'] = scores['overall_score'] >= config.human_review_threshold
            job['auto_apply_eligible'] = config.auto_apply_threshold <= scores['overall_score'] < config.human_review_threshold
        
        jobs.sort(key=lambda x: x.get('overall_score', 0), reverse=True)
        
        return jobs

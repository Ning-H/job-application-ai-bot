import yaml
import os
from typing import Dict, List, Any
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self, config_path: str = 'config.yaml'):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.user_profile = self.config.get('user_profile', {})
        self.target_companies = self.config.get('target_companies', {})
        self.job_boards = self.config.get('job_boards', [])
        self.crawl_settings = self.config.get('crawl_settings', {})
        self.ranking_weights = self.config.get('ranking_weights', {})
        self.auto_apply_threshold = self.config.get('auto_apply_threshold', 0.6)
        self.human_review_threshold = self.config.get('human_review_threshold', 0.75)
    
    def get_target_titles(self) -> List[str]:
        return self.user_profile.get('target_titles', [])
    
    def get_skills(self) -> List[str]:
        return self.user_profile.get('skills', [])
    
    def get_location_preferences(self) -> Dict[str, Any]:
        return self.user_profile.get('location_preferences', {})
    
    def get_all_companies(self) -> List[Dict[str, str]]:
        companies = []
        for category, company_list in self.target_companies.items():
            companies.extend(company_list)
        return companies
    
    def get_job_boards(self) -> List[Dict[str, Any]]:
        return self.job_boards
    
    def get_crawl_frequency_hours(self) -> int:
        return self.crawl_settings.get('frequency_hours', 6)
    
    def get_ranking_weights(self) -> Dict[str, float]:
        return self.ranking_weights

config = Config()
